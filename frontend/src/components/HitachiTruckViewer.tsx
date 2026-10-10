import { Suspense } from 'react'
import { Canvas, useLoader } from '@react-three/fiber'
import { Center, Html, OrbitControls, useProgress } from '@react-three/drei'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import * as THREE from 'three'
import { ErrorBoundary } from './ErrorBoundary'
import { assetUrl } from '../services/staticDemo'

function ModelLoading() {
  const { progress } = useProgress()
  return <Html center><div className="model-loading"><span className="loader-ring"/><b>Loading EH4000 model</b><small>{Math.round(progress)}%</small></div></Html>
}

function EH4000Model() {
  const gltf = useLoader(GLTFLoader, assetUrl('hitachi_eh4000_fs25.glb'))
  const scene = gltf.scene.clone(true)
  scene.traverse((object) => {
    if (object instanceof THREE.Mesh) {
      object.castShadow = true
      object.receiveShadow = true
    }
  })

  return <Center><primitive object={scene}/></Center>
}

export function HitachiTruckViewer() {
  return <div className="hitachi-truck-viewer">
    <ErrorBoundary fallback={<div className="viewer-error" role="alert"><b>3D preview unavailable</b><span>The converted EH4000 model could not be loaded.</span></div>}>
      <Canvas shadows dpr={[1,1.5]} camera={{position:[15,10,18],fov:42}} onCreated={({gl})=>{gl.setClearColor('#f2f5f7');gl.toneMapping=THREE.ACESFilmicToneMapping}}>
        <ambientLight intensity={1.25}/>
        <hemisphereLight args={['#fff8ed','#64778a',1.1]}/>
        <directionalLight position={[8,14,10]} intensity={2.1} castShadow shadow-mapSize-width={1024} shadow-mapSize-height={1024}/>
        <directionalLight position={[-8,6,-7]} intensity={0.9}/>
        <Suspense fallback={<ModelLoading/>}>
          <EH4000Model/>
          <gridHelper args={[28,28,'#d6dce1','#e5e9ed']} position={[0,-3.72,0]}/>
        </Suspense>
        <OrbitControls makeDefault enableDamping dampingFactor={.08} minDistance={9} maxDistance={50} target={[0,0,0]}/>
      </Canvas>
    </ErrorBoundary>
  </div>
}
