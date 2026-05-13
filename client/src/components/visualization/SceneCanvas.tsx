import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Stars } from '@react-three/drei';
import { useMemo, useRef } from 'react';
import * as THREE from 'three';

function FleetNode({ position, color }: { position: [number, number, number]; color: string }) {
  const mesh = useRef<THREE.Mesh>(null);

  useFrame(({ clock }) => {
    if (!mesh.current) {
      return;
    }
    mesh.current.rotation.y = clock.elapsedTime * 0.2;
    mesh.current.position.y = position[1] + Math.sin(clock.elapsedTime + position[0]) * 0.08;
  });

  return (
    <mesh ref={mesh} position={position}>
      <sphereGeometry args={[0.28, 32, 32]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.2} />
    </mesh>
  );
}

function ConnectionLines() {
  const points = useMemo(
    () => [
      new THREE.Vector3(-1.7, 0, 0),
      new THREE.Vector3(0, 0.3, 0.8),
      new THREE.Vector3(1.7, -0.1, -0.4),
    ],
    [],
  );

  return (
    <line>
      <bufferGeometry attach="geometry" setFromPoints={points} />
      <lineBasicMaterial color="#7dd3fc" transparent opacity={0.65} />
    </line>
  );
}

export function SceneCanvas() {
  return (
    <div className="h-[380px] overflow-hidden rounded-[20px] border border-white/10 bg-gradient-to-br from-[#07131d] to-[#0b1b27]">
      <Canvas camera={{ position: [0, 1.2, 5], fov: 50 }}>
        <ambientLight intensity={0.8} />
        <directionalLight position={[3, 4, 2]} intensity={1.4} />
        <Stars radius={30} depth={20} count={1600} factor={3} saturation={0} fade speed={0.5} />
        <FleetNode position={[-1.7, 0, 0]} color="#5bc0be" />
        <FleetNode position={[0, 0.3, 0.8]} color="#7dd3fc" />
        <FleetNode position={[1.7, -0.1, -0.4]} color="#fb7185" />
        <ConnectionLines />
        <OrbitControls enablePan={false} enableZoom={false} autoRotate autoRotateSpeed={0.8} />
      </Canvas>
    </div>
  );
}

