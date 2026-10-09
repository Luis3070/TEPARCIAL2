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
type Props = {points:SavedPoint[];selectedPoint:string;onSelect:(code:string)=>void;calibratingPoint?:string|null;onCalibrationSave?:(code:string,position:{x:number;y:number;z:number;nx:number;ny:number;nz:number})=>void;opacity?:number}

function Loading(){const {progress}=useProgress();return <Html center><div className="model-loading"><span className="loader-ring"/><b>Preparando geometría</b><small>{Math.round(progress)}%</small></div></Html>}
function transformHotspot(c:any,center:THREE.Vector3,factor:number){
 if(!c)return null
 // Model display: rotate source CAD Z-up to viewer Y-up, center, then uniformly fit.
 const rotated=new THREE.Vector3(c.x,c.z,-c.y).sub(center).multiplyScalar(factor)
 const normal=new THREE.Vector3(c.normal?.[0]??c.nx??0,c.normal?.[2]??c.nz??1,-(c.normal?.[1]??c.ny??0)).normalize()
 return {position:rotated,normal}
}
function PointMarker({point,selected,onSelect,opacity,center,factor,showLabels,showCones}:{point:SavedPoint;selected:boolean;onSelect:()=>void;opacity:number;center:THREE.Vector3;factor:number;showLabels:boolean;showCones:boolean}){
 const c=transformHotspot(point.calibration, center, factor)
 if(!c)return null
 const p=point.length_mm
 const ratio=p===null?0:Math.max(0,p/(point.danger_mm||1))
 const radius=0.16+Math.min(ratio,1.4)*0.28
 const height=0.32+Math.min(ratio,1.4)*0.8
 const q=new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),c.normal)
 const conePosition=c.position.clone().add(c.normal.clone().multiplyScalar(height*.43))
 const color=conditionColor[point.structural_state]
 return <group position={c.position}>
   {showCones&&p!==null&&p>0&&<mesh position={conePosition.clone().sub(c.position)} quaternion={q}>
     <coneGeometry args={[radius,height,24,1,true]}/><meshStandardMaterial color={color} transparent opacity={opacity} roughness={.34} metalness={.08} side={THREE.DoubleSide} depthWrite={false}/>
   </mesh>}
   <mesh onClick={(e)=>{e.stopPropagation();onSelect()}}>
    <sphereGeometry args={[selected ? .16 : .12,24,24]}/><meshStandardMaterial color={color} emissive={color} emissiveIntensity={selected ? .33 : .12} roughness={.3}/>
   </mesh>
   {showLabels&&<Html distanceFactor={7} position={[0,.22,0]} center><button className={`hotspot-label ${selected?'selected':''}`} onClick={(e)=>{e.stopPropagation();onSelect()}}><i style={{background:color}}/>{point.code}</button></Html>}
 </group>
}
function SuspensionMesh({points,selectedPoint,onSelect,calibratingPoint,onCalibrationSave,opacity,showCones,showLabels,focusPoint,viewMode,resetVersion}:{points:SavedPoint[];selectedPoint:string;onSelect:(code:string)=>void;calibratingPoint?:string|null;onCalibrationSave?:Props['onCalibrationSave'];opacity:number;showCones:boolean;showLabels:boolean;focusPoint:string;viewMode:string;resetVersion:number}){
 const loaded=useLoader(STLLoader,'/assets/EH4000_front_suspension_V7_final.stl')
 const geometry=useMemo(()=>{const g=loaded.clone();g.rotateX(-Math.PI/2);g.computeVertexNormals();return g},[loaded])
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
     <meshStandardMaterial color="#b6bdc2" roughness={.62} metalness={.26} side={THREE.DoubleSide}/>
    </mesh>
   </group>
  </group>
  {points.map(p=><PointMarker key={p.code} point={p} center={center} factor={factor} selected={p.code===selectedPoint} onSelect={()=>onSelect(p.code)} opacity={opacity} showLabels={showLabels} showCones={showCones}/>)}
  <gridHelper args={[10,20,'#d6dce1','#e5e9ed']} position={[0,-2.4,0]}/>
  <Html position={[0,-2.65,0]} center><div className="model-dimensions">Componente STL · {Math.round(bbox.x/factor)} × {Math.round(bbox.z/factor)} × {Math.round(bbox.y/factor)} unidades fuente</div></Html>
 </>
}

export function SuspensionViewer({points,selectedPoint,onSelect,calibratingPoint=null,onCalibrationSave,opacity=.23}:Props){
 const [showCones,setShowCones]=useState(true);const [showLabels,setShowLabels]=useState(true);const [viewMode,setViewMode]=useState('isometric');const [resetVersion,setResetVersion]=useState(0);const [focusPoint,setFocusPoint]=useState('')
 const [calibrationResult,setCalibrationResult]=useState('')
 const [webglSupported,setWebglSupported]=useState<boolean|null>(null)
 useEffect(()=>{try{const canvas=document.createElement('canvas');setWebglSupported(Boolean(window.WebGLRenderingContext&&(canvas.getContext('webgl2')||canvas.getContext('webgl'))))}catch{setWebglSupported(false)}},[])
 const save=(code:string,position:{x:number;y:number;z:number;nx:number;ny:number;nz:number})=>{setCalibrationResult(`${code}: ${position.x.toFixed(1)}, ${position.y.toFixed(1)}, ${position.z.toFixed(1)}`);onCalibrationSave?.(code,position)}
 const selected=points.find(p=>p.code===selectedPoint)
 return <div className="viewer-shell">
  <div className="viewer-topline"><div className="viewer-tabs"><span className="active"><View size={14}/>Suspensión delantera</span><span><Box size={14}/>Componente técnico</span></div><div className="viewer-controls"><button title="Vista isométrica" onClick={()=>setViewMode('isometric')}><View size={15}/></button><button title="Vista superior" onClick={()=>setViewMode('top')}>Top</button><button title="Vista frontal" onClick={()=>setViewMode('front')}>Front</button><button title="Vista lateral" onClick={()=>setViewMode('side')}>Side</button><button title="Restablecer cámara" onClick={()=>setResetVersion(v=>v+1)}><RotateCcw size={15}/></button><button title={showCones?'Ocultar indicadores volumétricos':'Mostrar indicadores volumétricos'} onClick={()=>setShowCones(v=>!v)}>{showCones?<Eye size={15}/>:<EyeOff size={15}/>}</button><button title={showLabels?'Ocultar etiquetas':'Mostrar etiquetas'} onClick={()=>setShowLabels(v=>!v)}><Scan size={15}/></button></div></div>
  <div className={`viewer-canvas ${calibratingPoint?'calibrating':''}`}>
   {webglSupported===false?<div className="viewer-error" role="status"><ShieldAlert size={22}/><b>Visor 3D no disponible en este navegador</b><span>WebGL no está habilitado. El historial, límites, estados y órdenes del dashboard siguen disponibles.</span></div>:webglSupported===null?<div className="viewer-error viewer-checking" role="status">Verificando soporte gráfico…</div>:<ErrorBoundary fallback={<div className="viewer-error" role="alert"><ShieldAlert size={22}/><b>Visor 3D no disponible</b><span>El navegador no pudo inicializar WebGL o cargar el STL. El resto de la inspección sigue disponible.</span></div>}>
    <Canvas shadows dpr={[1,1.7]} camera={{position:[7,5,8],fov:42}} onCreated={({gl})=>{gl.setClearColor('#f2f5f7');gl.toneMapping=THREE.ACESFilmicToneMapping}}>
     <Suspense fallback={<Loading/>}><SuspensionMesh points={points} selectedPoint={selectedPoint} onSelect={(p)=>{onSelect(p);setFocusPoint(p)}} calibratingPoint={calibratingPoint} onCalibrationSave={save} opacity={opacity} showCones={showCones} showLabels={showLabels} focusPoint={focusPoint} viewMode={viewMode} resetVersion={resetVersion}/></Suspense>
    </Canvas>
   </ErrorBoundary>}
   <div className="viewer-badge"><i className="live-dot"/> Condición histórica <b>NO EN VIVO</b></div>
   {calibratingPoint&&<div className="calibration-banner"><Crosshair size={15}/><span>Calibración de <b>{calibratingPoint}</b>: haz clic sobre su ubicación física en la malla</span><small>Posición pendiente de confirmación de ingeniería</small></div>}
   {calibrationResult&&<div className="calibration-result"><Check size={14}/>Posición guardada · {calibrationResult}</div>}
   {!points.some(p=>p.calibration)&&!calibratingPoint&&<div className="uncalibrated-note"><ShieldAlert size={16}/><span>Hotspots sin calibrar. Activa calibración desde Ajustes para ubicar los cuatro puntos sobre el STL.</span></div>}
   <div className="model-state-legend">{(['Normal','Alerta','Crítico','N/I'] as StructuralState[]).map(s=><span key={s}><i style={{background:conditionColor[s]}}/>{s}</span>)}</div>
  </div>
  <div className="viewer-footer"><div><b>{selected?.code||'Seleccione un punto'}</b><span>{selected?.description||'Elija un hotspot calibrado o use la lista de puntos.'}</span></div><div className="cone-disclaimer">Indicador volumétrico visual · no representa propagación de grieta ni análisis FEM</div></div>
 </div>
}
