import { useEffect, useRef, useState, useCallback } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Grid, Text } from '@react-three/drei';
import * as THREE from 'three';
import L from 'leaflet';
import { useMothStream } from '../../hooks/useMothStream';
import { useRegistryPreview } from '../../hooks/useRegistryPreview';
import type { Device } from '../../types';

// ──────────────────────────────────────────
// Constants
// ──────────────────────────────────────────
const BASE_LAT = 35.15;
const BASE_LON = 129.15;
const WORLD_SCALE = 0.001; // lat/lon delta → world units

function latLonToWorld(lat: number, lon: number): [number, number, number] {
  const x = (lon - BASE_LON) * 111320 * Math.cos((BASE_LAT * Math.PI) / 180) * WORLD_SCALE;
  const z = -(lat - BASE_LAT) * 111320 * WORLD_SCALE;
  return [x, 0, z];
}

const DEVICE_COLORS: Record<string, string> = {
  USV: '#5bc0be',
  AUV: '#7dd3fc',
  ROV: '#fb7185',
  DEFAULT: '#94a3b8',
};

// ──────────────────────────────────────────
// Device 3D models
// ──────────────────────────────────────────
function DeviceModel({ device, streamBattery, isSelected, onClick }: {
  device: Device;
  streamBattery?: number | null;
  isSelected: boolean;
  onClick: () => void;
}) {
  const meshRef = useRef<THREE.Group>(null);
  const color = DEVICE_COLORS[device.type?.toUpperCase()] ?? DEVICE_COLORS.DEFAULT;
  const lat = device.latitude ?? (BASE_LAT + (Math.random() - 0.5) * 0.02);
  const lon = device.longitude ?? (BASE_LON + (Math.random() - 0.5) * 0.02);
  const [wx, , wz] = latLonToWorld(lat, lon);
  const wy = device.is_submerged ? -2 : 0.3;

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    meshRef.current.position.y = wy + Math.sin(clock.elapsedTime * 0.8 + wx) * 0.05;
    if (isSelected) {
      meshRef.current.rotation.y = clock.elapsedTime * 0.5;
    }
  });

  const isOffline = device.status === 'OFFLINE';
  const emissiveIntensity = isSelected ? 0.6 : isOffline ? 0.1 : 0.25;

  return (
    <group
      ref={meshRef}
      position={[wx, wy, wz]}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
    >
      {device.type?.toUpperCase() === 'USV' && (
        <>
          <mesh>
            <boxGeometry args={[0.6, 0.15, 1.2]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={emissiveIntensity} />
          </mesh>
          <mesh position={[0, 0.25, 0]}>
            <cylinderGeometry args={[0.04, 0.04, 0.5, 8]} />
            <meshStandardMaterial color="#e2e8f0" />
          </mesh>
        </>
      )}
      {device.type?.toUpperCase() === 'ROV' && (
        <>
          <mesh>
            <boxGeometry args={[0.5, 0.3, 0.7]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={emissiveIntensity} wireframe={isOffline} />
          </mesh>
          <mesh position={[0.3, 0, 0]}><cylinderGeometry args={[0.06, 0.06, 0.3, 8]} /><meshStandardMaterial color="#64748b" /></mesh>
          <mesh position={[-0.3, 0, 0]}><cylinderGeometry args={[0.06, 0.06, 0.3, 8]} /><meshStandardMaterial color="#64748b" /></mesh>
        </>
      )}
      {device.type?.toUpperCase() === 'AUV' && (
        <>
          <mesh>
            <cylinderGeometry args={[0.15, 0.15, 1.0, 16]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={emissiveIntensity} />
          </mesh>
          <mesh position={[0, 0.6, 0]}>
            <sphereGeometry args={[0.15, 16, 16]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={emissiveIntensity} />
          </mesh>
          <mesh position={[0, -0.65, 0]} rotation={[0, 0, Math.PI]}>
            <coneGeometry args={[0.15, 0.2, 16]} />
            <meshStandardMaterial color="#475569" />
          </mesh>
        </>
      )}
      {!['USV', 'ROV', 'AUV'].includes(device.type?.toUpperCase() ?? '') && (
        <mesh>
          <boxGeometry args={[0.4, 0.4, 0.4]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={emissiveIntensity} />
        </mesh>
      )}

      {/* Label */}
      <Text
        position={[0, 0.8, 0]}
        fontSize={0.25}
        color={isSelected ? '#ffffff' : '#94a3b8'}
        anchorX="center"
        anchorY="bottom"
      >
        {device.name}
      </Text>

      {/* Battery ring */}
      {streamBattery !== undefined && streamBattery !== null && (
        <mesh position={[0, 0.6, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.22, 0.28, 32, 1, 0, (streamBattery / 100) * Math.PI * 2]} />
          <meshBasicMaterial
            color={streamBattery > 50 ? '#10b981' : streamBattery > 20 ? '#f59e0b' : '#ef4444'}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}
    </group>
  );
}

// ──────────────────────────────────────────
// Parent-child tether lines
// ──────────────────────────────────────────
function TetherLines({ devices }: { devices: Device[] }) {
  const links = devices
    .filter(d => d.parent_id)
    .map(child => {
      const parent = devices.find(p => p.id === child.parent_id);
      if (!parent) return null;
      const cLat = child.latitude ?? BASE_LAT;
      const cLon = child.longitude ?? BASE_LON;
      const pLat = parent.latitude ?? BASE_LAT;
      const pLon = parent.longitude ?? BASE_LON;
      const cPos = latLonToWorld(cLat, cLon);
      const pPos = latLonToWorld(pLat, pLon);
      return {
        key: `${parent.id}-${child.id}`,
        points: [
          new THREE.Vector3(pPos[0], 0.3, pPos[2]),
          new THREE.Vector3(cPos[0], child.is_submerged ? -2 : 0.3, cPos[2]),
        ] as [THREE.Vector3, THREE.Vector3],
      };
    })
    .filter((l): l is { key: string; points: [THREE.Vector3, THREE.Vector3] } => l !== null);

  return (
    <>
      {links.map(link => (
        <primitive
          key={link.key}
          object={(() => {
            const geo = new THREE.BufferGeometry().setFromPoints(link.points);
            const mat = new THREE.LineDashedMaterial({ color: '#7dd3fc', dashSize: 0.2, gapSize: 0.1, opacity: 0.5, transparent: true });
            const l = new THREE.Line(geo, mat);
            l.computeLineDistances();
            return l;
          })()}
        />
      ))}
    </>
  );
}

// ──────────────────────────────────────────
// Ocean plane + depth grids
// ──────────────────────────────────────────
function OceanBase() {
  const meshRef = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (meshRef.current) {
      (meshRef.current.material as THREE.MeshStandardMaterial).opacity =
        0.5 + Math.sin(clock.elapsedTime * 0.3) * 0.05;
    }
  });
  return (
    <>
      <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <planeGeometry args={[80, 80, 1, 1]} />
        <meshStandardMaterial color="#0c3b5e" transparent opacity={0.5} side={THREE.DoubleSide} />
      </mesh>
      {[-2, -5, -10, -15].map(y => (
        <Grid key={y} position={[0, y, 0]} args={[80, 80]} cellSize={5} cellColor="#1e3a5f" sectionColor="#2d5a8e" fadeDistance={60} fadeStrength={1} />
      ))}
    </>
  );
}

// ──────────────────────────────────────────
// Scene controller (camera modes)
// ──────────────────────────────────────────
function CameraController({ mode, targetPos }: { mode: string; targetPos: THREE.Vector3 | null }) {
  const { camera } = useThree();
  useFrame(() => {
    if (mode === 'follow' && targetPos) {
      camera.position.lerp(new THREE.Vector3(targetPos.x, targetPos.y + 5, targetPos.z + 10), 0.05);
      camera.lookAt(targetPos);
    }
  });
  return null;
}

// ──────────────────────────────────────────
// Leaflet Minimap Component (DOM overlay)
// ──────────────────────────────────────────
function LeafletMinimap({ devices, streamMap }: {
  devices: Device[];
  streamMap: Map<string, { latitude?: number | null; longitude?: number | null; status?: string }>;
}) {
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Map<string, L.CircleMarker>>(new Map());
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [BASE_LAT, BASE_LON],
      zoom: 13,
      zoomControl: false,
      attributionControl: false,
    });
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 18,
    }).addTo(map);
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    devices.forEach(device => {
      const stream = streamMap.get(String(device.id));
      const lat = stream?.latitude ?? device.latitude;
      const lon = stream?.longitude ?? device.longitude;
      if (!lat || !lon) return;

      const color = DEVICE_COLORS[device.type?.toUpperCase()] ?? DEVICE_COLORS.DEFAULT;
      let marker = markersRef.current.get(device.id);
      if (!marker) {
        marker = L.circleMarker([lat, lon], {
          radius: 8, color: '#fff', weight: 1,
          fillColor: color, fillOpacity: 0.9,
        }).bindTooltip(device.name, { permanent: false }).addTo(map);
        markersRef.current.set(device.id, marker);
      } else {
        marker.setLatLng([lat, lon]);
      }
    });
  }, [devices, streamMap]);

  return (
    <div
      style={{
        position: 'absolute', bottom: 16, right: 16,
        width: 180, height: 180,
        borderRadius: '50%', overflow: 'hidden',
        border: '2px solid rgba(93,180,207,0.4)',
        boxShadow: '0 0 20px rgba(93,180,207,0.2)',
        zIndex: 10,
      }}
      ref={containerRef}
    />
  );
}

// ──────────────────────────────────────────
// Main exported component
// ──────────────────────────────────────────
export function SceneCanvas() {
  const [cameraMode, setCameraMode] = useState<'orbit' | 'follow' | 'topdown'>('orbit');
  const [depthFilter, setDepthFilter] = useState(0);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [rightTab, setRightTab] = useState<'list' | 'alerts'>('list');

  const { streamMap, connected } = useMothStream();
  const { data: rawDevices } = useRegistryPreview<Device[]>('/devices', []);
  const devices: Device[] = Array.isArray(rawDevices) ? rawDevices.filter(
    d => d.type && !['SYSTEM', 'OTHER'].includes(d.type.toUpperCase())
  ) : [];
  const { data: rawEvents } = useRegistryPreview('/events', []);
  const recentAlerts = Array.isArray(rawEvents)
    ? (rawEvents as { severity?: string; title?: string; type?: string; event_id?: string }[])
        .filter(e => e.severity === 'WARNING' || e.severity === 'ERROR' || e.severity === 'CRITICAL')
        .slice(0, 5)
    : [];

  const selectedDevice = devices.find(d => d.id === selectedDeviceId) ?? null;
  const targetPos = selectedDevice?.latitude
    ? new THREE.Vector3(...latLonToWorld(selectedDevice.latitude, selectedDevice.longitude ?? BASE_LON))
    : null;

  const getBattery = useCallback((device: Device) => {
    const s = streamMap.get(String(device.id));
    return s?.battery_percent ?? device.battery_percent ?? device.battery;
  }, [streamMap]);

  const getStatus = useCallback((device: Device) => {
    const s = streamMap.get(String(device.id));
    return s?.status ?? device.status;
  }, [streamMap]);

  const onlineCount = devices.filter(d => getStatus(d)?.toUpperCase() === 'ONLINE').length;

  return (
    <div style={{ position: 'relative', height: 480, borderRadius: 20, overflow: 'hidden' }}
      className="border border-white/10 bg-[#07131d]">

      {/* ── 3D Canvas ── */}
      <Canvas
        camera={{ position: [0, 8, 20], fov: 55 }}
        onCreated={(state) => {
          state.gl.canvas.addEventListener('webglcontextlost', (e) => {
            e.preventDefault();
            console.warn('WebGL context lost, attempting recovery...');
          });
        }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 20, 10]} intensity={0.8} color="#fff8e7" />
        <pointLight position={[0, -5, 0]} intensity={0.3} color="#3b82f6" />
        <fog attach="fog" args={['#001e36', 40, 120]} />

        <OceanBase />
        <TetherLines devices={devices} />

        {devices
          .filter(d => (d.is_submerged ? -depthFilter > 0 : depthFilter >= 0))
          .map(device => (
            <DeviceModel
              key={device.id}
              device={device}
              streamBattery={getBattery(device) ?? undefined}
              isSelected={selectedDeviceId === device.id}
              onClick={() => setSelectedDeviceId(prev => prev === device.id ? null : device.id)}
            />
          ))
        }

        <CameraController mode={cameraMode} targetPos={targetPos} />
        {cameraMode === 'orbit' && (
          <OrbitControls enableDamping dampingFactor={0.05} minDistance={3} maxDistance={60} />
        )}
      </Canvas>

      {/* ── Leaflet Minimap ── */}
      <LeafletMinimap devices={devices} streamMap={streamMap} />

      {/* ── Left Panel ── */}
      <div style={{
        position: 'absolute', top: 12, left: 12,
        background: 'rgba(7,19,29,0.85)', backdropFilter: 'blur(8px)',
        border: '1px solid rgba(93,180,207,0.2)', borderRadius: 12,
        padding: '12px 16px', minWidth: 160, zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: connected ? '#10b981' : '#6b7280' }} />
          <span style={{ fontSize: 11, color: '#94a3b8' }}>{connected ? 'Live' : 'Offline'}</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', marginBottom: 12 }}>
          {[
            { label: 'Online', value: onlineCount, color: '#10b981' },
            { label: 'Total', value: devices.length, color: '#94a3b8' },
            { label: 'USV', value: devices.filter(d => d.type?.toUpperCase() === 'USV').length, color: '#5bc0be' },
            { label: 'AUV', value: devices.filter(d => d.type?.toUpperCase() === 'AUV').length, color: '#7dd3fc' },
            { label: 'ROV', value: devices.filter(d => d.type?.toUpperCase() === 'ROV').length, color: '#fb7185' },
            { label: 'Alerts', value: recentAlerts.length, color: recentAlerts.length > 0 ? '#f59e0b' : '#94a3b8' },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <div style={{ fontSize: 10, color: '#64748b' }}>{label}</div>
              <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 10, color: '#64748b', marginBottom: 4 }}>Camera</div>
          <select
            value={cameraMode}
            onChange={e => setCameraMode(e.target.value as typeof cameraMode)}
            style={{ fontSize: 12, color: '#cbd5e1', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, padding: '2px 6px', width: '100%' }}
          >
            <option value="orbit">Orbit</option>
            <option value="follow">Follow</option>
            <option value="topdown">Top-down</option>
          </select>
        </div>

        <div>
          <div style={{ fontSize: 10, color: '#64748b', marginBottom: 4 }}>Depth: {depthFilter}m</div>
          <input
            type="range" min={-30} max={0} value={depthFilter}
            onChange={e => setDepthFilter(Number(e.target.value))}
            style={{ width: '100%', accentColor: '#5bc0be' }}
          />
        </div>
      </div>

      {/* ── Right Panel ── */}
      <div style={{
        position: 'absolute', top: 12, right: 204,
        background: 'rgba(7,19,29,0.85)', backdropFilter: 'blur(8px)',
        border: '1px solid rgba(93,180,207,0.2)', borderRadius: 12,
        padding: 12, width: 200, maxHeight: 340, display: 'flex', flexDirection: 'column', zIndex: 10,
      }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          {(['list', 'alerts'] as const).map(tab => (
            <button key={tab} onClick={() => setRightTab(tab)} style={{
              fontSize: 11, padding: '2px 8px', borderRadius: 4,
              background: rightTab === tab ? 'rgba(93,180,207,0.2)' : 'transparent',
              color: rightTab === tab ? '#5bc0be' : '#64748b',
              border: 'none', cursor: 'pointer',
            }}>
              {tab === 'list' ? 'Devices' : `Alerts (${recentAlerts.length})`}
            </button>
          ))}
        </div>

        <div style={{ overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {rightTab === 'list' && devices.map(device => {
            const battery = getBattery(device);
            const status = getStatus(device);
            const isOnline = status?.toUpperCase() === 'ONLINE';
            return (
              <button
                key={device.id}
                onClick={() => setSelectedDeviceId(prev => prev === device.id ? null : device.id)}
                style={{
                  textAlign: 'left', padding: '6px 8px', borderRadius: 6,
                  background: selectedDeviceId === device.id ? 'rgba(93,180,207,0.15)' : 'rgba(255,255,255,0.03)',
                  border: `1px solid ${selectedDeviceId === device.id ? 'rgba(93,180,207,0.4)' : 'rgba(255,255,255,0.06)'}`,
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>{device.name}</span>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: isOnline ? '#10b981' : '#ef4444', flexShrink: 0 }} />
                </div>
                <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>{device.type}</div>
                {battery !== null && battery !== undefined && (
                  <div style={{ marginTop: 4, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', borderRadius: 2,
                      width: `${battery}%`,
                      background: battery > 50 ? '#10b981' : battery > 20 ? '#f59e0b' : '#ef4444',
                    }} />
                  </div>
                )}
              </button>
            );
          })}

          {rightTab === 'alerts' && (
            recentAlerts.length === 0
              ? <p style={{ fontSize: 11, color: '#64748b' }}>No active alerts</p>
              : recentAlerts.map((alert, i) => (
                <div key={alert.event_id ?? i} style={{
                  padding: '6px 8px', borderRadius: 6,
                  background: alert.severity === 'CRITICAL' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)',
                  border: `1px solid ${alert.severity === 'CRITICAL' ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}`,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: alert.severity === 'CRITICAL' ? '#fca5a5' : '#fcd34d' }}>
                    {alert.severity}
                  </div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{alert.title}</div>
                </div>
              ))
          )}
        </div>
      </div>
    </div>
  );
}
