import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useLoader } from '@react-three/fiber'
import type { ThreeEvent } from '@react-three/fiber'
import { Html, OrbitControls, PerspectiveCamera, useProgress } from '@react-three/drei'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import * as THREE from 'three'
import { Box, RotateCcw, Scan, View, Eye, EyeOff, Crosshair, Check, ShieldAlert } from 'lucide-react'
import type { Point, StructuralState } from '../types'
import { StatusBadge } from './StatusBadge'
import { ErrorBoundary } from './ErrorBoundary'

const conditionColor:Record<StructuralState,string>={Normal:'#39874d',Alerta:'#d7a322','Crítico':'#c64138','N/I':'#89939d'}
type SavedPoint = Point & {calibration?:any}
type Props = {points:SavedPoint[];selectedPoint:string;onSelect:(code:string)=>void;calibratingPoint?:string|null;onCalibrationSave?:(code:string,position:{x:number;y:number;z:number;nx:number;ny:number;nz:number})=>void}
// Surface locator sizes (source-local STL units), not crack dimensions.
const PATCH_RADIUS_BY_CODE:Record<string,number>={'SD-01':360,'SD-02':360,'SD-03':420,'SD-04':420}
const PATCH_EDGE_WIDTH_BY_CODE:Record<string,number>={'SD-01':80,'SD-02':80,'SD-03':88,'SD-04':88}
type SurfacePath={direction:[number,number,number];length:number;radius:number;edgeWidth:number;sourceZRange?:[number,number]}
const SCISSOR_ARM_SOURCE_Z_RANGE:[number,number]=[280,1100]
// CAD-local paths: scissor plates extend inward; spindle assemblies rise and flare outward.
// These are display footprints over the STL, not measured crack dimensions.
const SURFACE_PATHS_BY_CODE:Record<string,SurfacePath>={
 'SD-01':{direction:[-1,-1,0],length:1600,radius:560,edgeWidth:180,sourceZRange:SCISSOR_ARM_SOURCE_Z_RANGE},
 'SD-02':{direction:[-1,1,0],length:1600,radius:560,edgeWidth:180,sourceZRange:SCISSOR_ARM_SOURCE_Z_RANGE},
 'SD-03':{direction:[-.23,.18,.956],length:2200,radius:650,edgeWidth:200},
 'SD-04':{direction:[-.23,-.18,.956],length:2200,radius:650,edgeWidth:200}
}
const SURFACE_PATH_TAPER_FRACTION=.06

function Loading(){const {progress}=useProgress();return <Html center><div className="model-loading"><span className="loader-ring"/><b>Preparando geometría</b><small>{Math.round(progress)}%</small></div></Html>}
function transformHotspot(c:any,center:THREE.Vector3,factor:number){
 if(!c)return null
 // Model display: rotate source CAD Z-up to viewer Y-up, center, then uniformly fit.
 const rotated=new THREE.Vector3(c.x,c.z,-c.y).sub(center).multiplyScalar(factor)
 const normal=new THREE.Vector3(c.normal?.[0]??c.nx??0,c.normal?.[2]??c.nz??1,-(c.normal?.[1]??c.ny??0)).normalize()
 return {position:rotated,normal}
}
function paintSurfacePatches(geometry:THREE.BufferGeometry,points:SavedPoint[],showPatches:boolean){
 const position=geometry.getAttribute('position') as THREE.BufferAttribute
 let colors=geometry.getAttribute('color') as THREE.BufferAttribute|undefined
 if(!colors||colors.count!==position.count){colors=new THREE.BufferAttribute(new Float32Array(position.count*3),3);geometry.setAttribute('color',colors)}
 const colorArray=colors.array as Float32Array
 const base=new THREE.Color('#b6bdc2')
 const sites=showPatches?points.filter(p=>p.calibration).map(p=>({
  code:p.code,
  x:Number(p.calibration.x),y:Number(p.calibration.y),z:Number(p.calibration.z),
  color:new THREE.Color(conditionColor[p.structural_state]),
  radius:PATCH_RADIUS_BY_CODE[p.code]??420,edgeWidth:PATCH_EDGE_WIDTH_BY_CODE[p.code]??88,
  sourceZRange:p.code==='SD-01'||p.code==='SD-02'?SCISSOR_ARM_SOURCE_Z_RANGE:null
 })).filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&Number.isFinite(p.z)):[]
 const corridors=showPatches?points.flatMap(point=>{
  const path=SURFACE_PATHS_BY_CODE[point.code]
  if(!path||!point.calibration)return []
  const start=new THREE.Vector3(Number(point.calibration.x),Number(point.calibration.y),Number(point.calibration.z))
  const direction=new THREE.Vector3(...path.direction).normalize()
  return [{code:point.code,color:new THREE.Color(conditionColor[point.structural_state]),start,direction,
   length:path.length,totalDistance:path.length,radius:path.radius,edgeWidth:path.edgeWidth,
   sourceZRange:path.sourceZRange??null}]
 }):[]
 const blended=new THREE.Color()
 for(let i=0;i<position.count;i++){
  const x=position.getX(i),y=position.getY(i),z=position.getZ(i)
  // Invert the display-only X -90° transform: source=(display X,-display Z,display Y).
  const sx=x,sy=-z,sz=y
  let nearestDistanceSquared=Infinity
  let nearestSite:typeof sites[number]|undefined
  // Paint each point's intended connected-looking surface region along its CAD-local path.
  // The spindle vectors rise and drift inward toward the upper spindle bodies shown in the review images.
  for(const corridor of corridors){
   if(corridor.sourceZRange&&(sz<corridor.sourceZRange[0]||sz>corridor.sourceZRange[1]))continue
   const dx=sx-corridor.start.x,dy=sy-corridor.start.y,dz=sz-corridor.start.z
   const along=dx*corridor.direction.x+dy*corridor.direction.y+dz*corridor.direction.z
   if(along<0||along>corridor.length)continue
   const taperStart=corridor.length-corridor.totalDistance*SURFACE_PATH_TAPER_FRACTION
   const taper=along<=taperStart?1:Math.max(0,(corridor.length-along)/(corridor.length-taperStart))
   const localRadius=corridor.radius*taper
   const distanceSquared=Math.max(0,dx*dx+dy*dy+dz*dz-along*along)
   if(localRadius>0&&distanceSquared<=localRadius*localRadius&&distanceSquared<nearestDistanceSquared){
    nearestDistanceSquared=distanceSquared
    nearestSite={code:corridor.code,x:0,y:0,z:0,color:corridor.color,radius:localRadius,
     edgeWidth:Math.min(corridor.edgeWidth,localRadius),sourceZRange:corridor.sourceZRange}
   }
  }
  if(!nearestSite){
   for(const site of sites){
    if(site.sourceZRange&&(sz<site.sourceZRange[0]||sz>site.sourceZRange[1]))continue
    const dx=sx-site.x,dy=sy-site.y,dz=sz-site.z,distanceSquared=dx*dx+dy*dy+dz*dz
    if(distanceSquared<=site.radius*site.radius&&distanceSquared<nearestDistanceSquared){nearestDistanceSquared=distanceSquared;nearestSite=site}
   }
  }
  if(nearestSite){
   const innerRadius=nearestSite.radius-nearestSite.edgeWidth
   const edgeFactor=nearestDistanceSquared<=innerRadius*innerRadius?0:(Math.sqrt(nearestDistanceSquared)-innerRadius)/nearestSite.edgeWidth
   blended.copy(base).lerp(nearestSite.color,.84+.16*Math.min(1,edgeFactor))
   colorArray[i*3]=blended.r;colorArray[i*3+1]=blended.g;colorArray[i*3+2]=blended.b
  }else{colorArray[i*3]=base.r;colorArray[i*3+1]=base.g;colorArray[i*3+2]=base.b}
 }
 colors.needsUpdate=true
 geometry.computeBoundingSphere()
}
function PointMarker({point,selected,onSelect,center,factor,showLabels}:{point:SavedPoint;selected:boolean;onSelect:()=>void;center:THREE.Vector3;factor:number;showLabels:boolean}){
 const c=transformHotspot(point.calibration, center, factor)
 if(!c)return null
 const color=conditionColor[point.structural_state]
 return <group position={c.position}>
   <mesh renderOrder={20} position={c.normal.clone().multiplyScalar(.035)} onClick={(e)=>{e.stopPropagation();onSelect()}}>
    <sphereGeometry args={[selected ? .13 : .085,20,20]}/><meshStandardMaterial color={color} emissive={color} emissiveIntensity={selected ? .38 : .16} roughness={.3} depthTest={false} depthWrite={false}/>
   </mesh>
   {showLabels&&<Html distanceFactor={7} zIndexRange={[1000,0]} position={[0,.24,0]} center><button className={`hotspot-label ${selected?'selected':''}`} onClick={(e)=>{e.stopPropagation();onSelect()}}><i style={{background:color}}/>{point.code}</button></Html>}
 </group>
}
function SuspensionMesh({points,selectedPoint,onSelect,calibratingPoint,onCalibrationSave,showPatches,showLabels,focusPoint,viewMode,resetVersion}:{points:SavedPoint[];selectedPoint:string;onSelect:(code:string)=>void;calibratingPoint?:string|null;onCalibrationSave?:Props['onCalibrationSave'];showPatches:boolean;showLabels:boolean;focusPoint:string;viewMode:string;resetVersion:number}){
 const loaded=useLoader(STLLoader,'/assets/EH4000_front_suspension_V7_final.stl')
 const geometry=useMemo(()=>{const g=loaded.clone();g.rotateX(-Math.PI/2);g.computeVertexNormals();return g},[loaded])
 useEffect(()=>{paintSurfacePatches(geometry,points,showPatches)},[geometry,points,showPatches])
 const center=useMemo(()=>{geometry.computeBoundingBox();return geometry.boundingBox!.getCenter(new THREE.Vector3())},[geometry])
 const factor=useMemo(()=>{geometry.computeBoundingBox();const size=geometry.boundingBox!.getSize(new THREE.Vector3());return 5.2/Math.max(size.x,size.y,size.z)},[geometry])
 const controls=useRef<any>(null);const camera=useRef<THREE.PerspectiveCamera>(null)
 const [bbox]=useState(()=>{geometry.computeBoundingBox();return geometry.boundingBox!.getSize(new THREE.Vector3())})
 const calibrationClick=(e:ThreeEvent<PointerEvent>)=>{
   if(!calibratingPoint||!onCalibrationSave)return
   e.stopPropagation()
   const rotated=e.point.clone().divideScalar(factor).add(center)
   const raw={x:rotated.x,y:-rotated.z,z:rotated.y}
   const n=e.face?.normal.clone().normalize()||new THREE.Vector3(0,1,0)
   onCalibrationSave(calibratingPoint,{x:raw.x,y:raw.y,z:raw.z,nx:n.x,ny:-n.z,nz:n.y})
 }
 const setView=(mode:string)=>{
   const c=controls.current;const cam=camera.current;if(!c||!cam)return
   const target=new THREE.Vector3(0,0,0);let offset=new THREE.Vector3(7,5,8)
   if(mode==='top')offset.set(0,9,.001);if(mode==='front')offset.set(0,0,10);if(mode==='side')offset.set(10,0,.001)
   cam.position.copy(target.clone().add(offset));cam.up.set(0,1,0);cam.lookAt(target);c.target.copy(target);c.update()
 }
 const resetCamera=()=>setView('isometric')
 useEffect(()=>{if(!camera.current)return; if(viewMode)setView(viewMode)},[viewMode])
 useEffect(()=>{if(!focusPoint)return;const p=points.find(x=>x.code===focusPoint);const target=transformHotspot(p?.calibration,center,factor);if(target&&controls.current){controls.current.target.copy(target.position);controls.current.update()}},[focusPoint,points,center,factor])
 useEffect(()=>{if(resetVersion)resetCamera()},[resetVersion])
 return <>
  <PerspectiveCamera ref={camera} makeDefault position={[7,5,8]} fov={42}/>
  <OrbitControls ref={controls} makeDefault enableDamping dampingFactor={.08} minDistance={2} maxDistance={15} target={[0,0,0]}/>
  <ambientLight intensity={1.15}/><hemisphereLight args={['#fff8ed','#64778a',1.4]}/>
  <directionalLight position={[5,8,7]} intensity={2.2} castShadow shadow-mapSize-width={1024} shadow-mapSize-height={1024}/>
  <directionalLight position={[-6,2,-4]} intensity={.9}/>
  <group scale={factor} position={[0,0,0]}>
   <group position={[-center.x,-center.y,-center.z]}>
    <mesh geometry={geometry} castShadow receiveShadow onPointerDown={calibrationClick}>
     <meshStandardMaterial vertexColors roughness={.62} metalness={.18} side={THREE.DoubleSide}/>
    </mesh>
   </group>
  </group>
  {points.map(p=><PointMarker key={p.code} point={p} center={center} factor={factor} selected={p.code===selectedPoint} onSelect={()=>onSelect(p.code)} showLabels={showLabels}/>)}
  <gridHelper args={[10,20,'#d6dce1','#e5e9ed']} position={[0,-2.4,0]}/>
  <Html position={[0,-2.65,0]} center><div className="model-dimensions">Componente STL · {Math.round(bbox.x/factor)} × {Math.round(bbox.z/factor)} × {Math.round(bbox.y/factor)} unidades fuente</div></Html>
 </>
}

export function SuspensionViewer({points,selectedPoint,onSelect,calibratingPoint=null,onCalibrationSave}:Props){
 const [showPatches,setShowPatches]=useState(true);const [showLabels,setShowLabels]=useState(true);const [viewMode,setViewMode]=useState('isometric');const [resetVersion,setResetVersion]=useState(0);const [focusPoint,setFocusPoint]=useState(selectedPoint)
 const [calibrationResult,setCalibrationResult]=useState('')
 const [webglSupported,setWebglSupported]=useState<boolean|null>(null)
 useEffect(()=>{try{const canvas=document.createElement('canvas');setWebglSupported(Boolean(window.WebGLRenderingContext&&(canvas.getContext('webgl2')||canvas.getContext('webgl'))))}catch{setWebglSupported(false)}},[])
 useEffect(()=>{if(selectedPoint)setFocusPoint(selectedPoint)},[selectedPoint])
 const save=(code:string,position:{x:number;y:number;z:number;nx:number;ny:number;nz:number})=>{setCalibrationResult(`${code}: ${position.x.toFixed(1)}, ${position.y.toFixed(1)}, ${position.z.toFixed(1)}`);onCalibrationSave?.(code,position)}
 const selected=points.find(p=>p.code===selectedPoint)
 return <div className="viewer-shell">
  <div className="viewer-topline"><div className="viewer-tabs"><span className="active"><View size={14}/>Suspensión delantera</span><span><Box size={14}/>Componente técnico</span></div><div className="viewer-controls"><button title="Vista isométrica" onClick={()=>setViewMode('isometric')}><View size={15}/></button><button title="Vista superior" onClick={()=>setViewMode('top')}>Top</button><button title="Vista frontal" onClick={()=>setViewMode('front')}>Front</button><button title="Vista lateral" onClick={()=>setViewMode('side')}>Side</button><button title="Restablecer cámara" onClick={()=>setResetVersion(v=>v+1)}><RotateCcw size={15}/></button><button title={showPatches?'Ocultar huellas de estado en STL':'Mostrar huellas de estado en STL'} onClick={()=>setShowPatches(v=>!v)}>{showPatches?<Eye size={15}/>:<EyeOff size={15}/>}</button><button title={showLabels?'Ocultar etiquetas':'Mostrar etiquetas'} onClick={()=>setShowLabels(v=>!v)}><Scan size={15}/></button></div></div>
  <div className={`viewer-canvas ${calibratingPoint?'calibrating':''}`}>
   {webglSupported===false?<div className="viewer-error" role="status"><ShieldAlert size={22}/><b>Visor 3D no disponible en este navegador</b><span>WebGL no está habilitado. El historial, límites, estados y órdenes del dashboard siguen disponibles.</span></div>:webglSupported===null?<div className="viewer-error viewer-checking" role="status">Verificando soporte gráfico…</div>:<ErrorBoundary fallback={<div className="viewer-error" role="alert"><ShieldAlert size={22}/><b>Visor 3D no disponible</b><span>El navegador no pudo inicializar WebGL o cargar el STL. El resto de la inspección sigue disponible.</span></div>}>
    <Canvas shadows dpr={[1,1.7]} camera={{position:[7,5,8],fov:42}} onCreated={({gl})=>{gl.setClearColor('#f2f5f7');gl.toneMapping=THREE.ACESFilmicToneMapping}}>
     <Suspense fallback={<Loading/>}><SuspensionMesh points={points} selectedPoint={selectedPoint} onSelect={(p)=>{onSelect(p);setFocusPoint(p)}} calibratingPoint={calibratingPoint} onCalibrationSave={save} showPatches={showPatches} showLabels={showLabels} focusPoint={focusPoint} viewMode={viewMode} resetVersion={resetVersion}/></Suspense>
    </Canvas>
   </ErrorBoundary>}
   <div className="viewer-badge"><i className="live-dot"/> Condición histórica <b>NO EN VIVO</b></div>
   {calibratingPoint&&<div className="calibration-banner"><Crosshair size={15}/><span>Calibración de <b>{calibratingPoint}</b>: haz clic sobre su ubicación física en la malla</span><small>Posición pendiente de confirmación de ingeniería</small></div>}
   {calibrationResult&&<div className="calibration-result"><Check size={14}/>Posición guardada · {calibrationResult}</div>}
   {!points.some(p=>p.calibration)&&!calibratingPoint&&<div className="uncalibrated-note"><ShieldAlert size={16}/><span>Hotspots sin calibrar. Activa calibración desde Ajustes para ubicar los cuatro puntos sobre el STL.</span></div>}
   <div className="model-state-legend">{(['Normal','Alerta','Crítico','N/I'] as StructuralState[]).map(s=><span key={s}><i style={{background:conditionColor[s]}}/>{s}</span>)}</div>
  </div>
  <div className="viewer-footer"><div><b>{selected?.code||'Seleccione un punto'}</b><span>{selected?.description||'Elija un hotspot calibrado o use la lista de puntos.'}</span></div><div className="surface-disclaimer">Huella visual ampliada sobre el STL · refleja el estado del punto, no el alcance de inspección ni la geometría de la grieta.</div></div>
 </div>
}
