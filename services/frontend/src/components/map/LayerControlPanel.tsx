/**
 * LayerControlPanel: 지도 레이어 제어 패널
 * - FAB 버튼 (지도 우상단)
 * - 슬라이드 패널로 레이어 on/off 제어
 */

import { useState } from "react";
import { useMapLayerStore } from "@/stores/mapLayerStore";

const PLATFORM_TYPES = [
  { id: "vessel", label: "선박", icon: "▲" },
  { id: "usv", label: "USV", icon: "◆" },
  { id: "rov", label: "ROV", icon: "●" },
  { id: "auv", label: "AUV", icon: "◈" },
  { id: "drone", label: "드론", icon: "✦" },
  { id: "buoy", label: "부이", icon: "◉" },
];

const ZONE_TYPES = [
  { id: "prohibited", label: "금지", color: "#ef4444" },
  { id: "restricted", label: "제한", color: "#f59e0b" },
  { id: "caution", label: "주의", color: "#3b82f6" },
];

interface LayerControlPanelProps {
  visible?: boolean;
}

export default function LayerControlPanel({ visible = true }: LayerControlPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const {
    showSeamark,
    showZones,
    showPlatforms,
    showTrails,
    showNavAids,
    visiblePlatformTypes,
    visibleZoneTypes,
    trailLength,
    toggleLayer,
    togglePlatformType,
    toggleZoneType,
    setTrailLength,
    resetToDefaults,
  } = useMapLayerStore();

  if (!visible) return null;

  return (
    <>
      {/* FAB 버튼 */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-ocean-700 hover:bg-ocean-600 border border-ocean-600 shadow-lg transition-all flex items-center justify-center text-xl"
        title="지도 레이어 설정"
      >
        🗺️
      </button>

      {/* 백드롭 */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/20 z-40" onClick={() => setIsOpen(false)} />
      )}

      {/* 슬라이드 패널 */}
      <div
        className={`fixed bottom-0 right-0 w-80 h-screen bg-ocean-950 border-l border-ocean-700 shadow-2xl overflow-y-auto transition-transform duration-300 z-50 ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="p-5 space-y-6">
          {/* 헤더 */}
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-ocean-100">🗺️ 레이어 설정</h2>
            <button
              onClick={() => setIsOpen(false)}
              className="text-ocean-400 hover:text-ocean-200 text-xl"
            >
              ✕
            </button>
          </div>

          {/* 기본 레이어 */}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ocean-400 mb-3">
              기본 레이어
            </h3>
            <div className="space-y-2">
              <ToggleItem
                label="해도 (OpenSeaMap)"
                active={showSeamark}
                onChange={() => toggleLayer("seamark")}
              />
              <ToggleItem
                label="관제 구역"
                active={showZones}
                onChange={() => toggleLayer("zones")}
              />
              <ToggleItem
                label="플랫폼 (선박·드론)"
                active={showPlatforms}
                onChange={() => toggleLayer("platforms")}
              />
              <ToggleItem
                label="항적 (이동 경로)"
                active={showTrails}
                onChange={() => toggleLayer("trails")}
              />
              <ToggleItem
                label="항법 보조시설 (등대·표지)"
                active={showNavAids}
                onChange={() => toggleLayer("navAids")}
              />
            </div>
          </div>

          {/* 플랫폼 타입 필터 */}
          {showPlatforms && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ocean-400 mb-3">
                플랫폼 타입
              </h3>
              <div className="flex flex-wrap gap-2">
                {PLATFORM_TYPES.map((type) => (
                  <button
                    key={type.id}
                    onClick={() => togglePlatformType(type.id)}
                    className={`px-3 py-1.5 rounded-full border transition-colors text-xs font-medium flex items-center gap-1 ${
                      visiblePlatformTypes[type.id]
                        ? "border-ocean-500 bg-ocean-700 text-ocean-100"
                        : "border-ocean-700 bg-ocean-900 text-ocean-500"
                    }`}
                  >
                    <span>{type.icon}</span>
                    <span>{type.label}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 구역 타입 필터 */}
          {showZones && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ocean-400 mb-3">
                관제 구역 타입
              </h3>
              <div className="space-y-2">
                {ZONE_TYPES.map((type) => (
                  <button
                    key={type.id}
                    onClick={() => toggleZoneType(type.id)}
                    className={`w-full px-3 py-2 rounded border transition-colors text-xs font-medium flex items-center gap-2 ${
                      visibleZoneTypes[type.id]
                        ? "border-current bg-opacity-15"
                        : "border-ocean-700 text-ocean-500"
                    }`}
                    style={{
                      borderColor: visibleZoneTypes[type.id] ? type.color : undefined,
                      backgroundColor: visibleZoneTypes[type.id]
                        ? `${type.color}15`
                        : "transparent",
                      color: visibleZoneTypes[type.id] ? type.color : undefined,
                    }}
                  >
                    <div
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: type.color }}
                    />
                    {type.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 항적 길이 조절 */}
          {showTrails && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ocean-400 mb-3">
                항적 길이
              </h3>
              <div className="space-y-2">
                <input
                  type="range"
                  min="10"
                  max="200"
                  value={trailLength}
                  onChange={(e) => setTrailLength(parseInt(e.target.value))}
                  className="w-full"
                />
                <div className="flex items-center justify-between text-xs text-ocean-400">
                  <span>최근 {trailLength}개 포인트</span>
                  <span className="text-ocean-500">{Math.round((trailLength / 200) * 100)}%</span>
                </div>
              </div>
            </div>
          )}

          {/* 초기화 버튼 */}
          <div className="border-t border-ocean-700 pt-4">
            <button
              onClick={resetToDefaults}
              className="w-full px-3 py-2 rounded border border-ocean-700 hover:border-ocean-600 text-ocean-400 hover:text-ocean-300 text-xs font-medium transition-colors"
            >
              기본값으로 초기화
            </button>
          </div>

          {/* 팁 */}
          <div className="bg-ocean-900/50 rounded p-3 text-[10px] text-ocean-500">
            💡 <span className="ml-1">레이어를 켜고 끄면 지도가 실시간으로 업데이트됩니다</span>
          </div>
        </div>
      </div>
    </>
  );
}

/**
 * ToggleItem: ON/OFF 토글 아이템
 */
function ToggleItem({
  label,
  active,
  onChange,
}: {
  label: string;
  active: boolean;
  onChange: () => void;
}) {
  return (
    <button
      onClick={onChange}
      className="w-full flex items-center gap-2 px-3 py-2 rounded border transition-colors text-sm"
      style={{
        borderColor: active ? "#5aade0" : "#164e8a",
        backgroundColor: active ? "rgba(90,173,224,0.1)" : "rgba(22,78,138,0.1)",
        color: active ? "#5aade0" : "#164e8a",
      }}
    >
      <div
        className={`w-4 h-4 rounded border flex items-center justify-center transition-all ${
          active ? "border-current bg-current" : "border-current"
        }`}
      >
        {active && <span className="text-xs text-ocean-950">✓</span>}
      </div>
      <span className="flex-1 text-left">{label}</span>
      <span className="text-xs opacity-70">{active ? "ON" : "OFF"}</span>
    </button>
  );
}
