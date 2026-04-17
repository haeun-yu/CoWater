#!/usr/bin/env python3
"""
해양 운영 시스템 시뮬레이터
YAML 시나리오 기반 3D 시각화용 데이터 생성
"""

import json
import math
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import yaml
import time
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socketserver


@dataclass
class Position:
    x: float
    y: float
    z: float


@dataclass
class VesselState:
    id: str
    name: str
    type: str
    position: Position
    heading: float
    speed_knots: float
    status: str
    depth: float = 0.0
    battery_percent: float = 100.0


class NavalSimulator:
    def __init__(self, scenario_file: str):
        self.scenario_file = Path(scenario_file)
        self.scenario = self._load_scenario()
        self.objects: Dict[str, VesselState] = {}
        self.events: List[Dict[str, Any]] = []
        self.current_time = 0
        self.running = False
        self._initialize_objects()

    def _load_scenario(self) -> Dict[str, Any]:
        """YAML 시나리오 로드"""
        with open(self.scenario_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _initialize_objects(self):
        """시나리오에서 객체 초기화"""
        scenario = self.scenario['scenario']
        objects = self.scenario['objects']

        # 통제 센터
        if 'control_centers' in objects:
            for center in objects['control_centers']:
                pos = center['position']
                self.objects[center['id']] = VesselState(
                    id=center['id'],
                    name=center['name'],
                    type=center['type'],
                    position=Position(pos['x'], pos['y'], pos['z']),
                    heading=0,
                    speed_knots=0,
                    status=center.get('status', 'operational')
                )

        # 선박
        if 'surface_vessels' in objects:
            for vessel in objects['surface_vessels']:
                pos = vessel['initial_position']
                self.objects[vessel['id']] = VesselState(
                    id=vessel['id'],
                    name=vessel['name'],
                    type=vessel['type'],
                    position=Position(pos['x'], pos['y'], pos['z']),
                    heading=vessel.get('initial_heading_deg', 0),
                    speed_knots=vessel.get('initial_speed_knots', 0),
                    status=vessel.get('status', 'active')
                )

        # USV/드론
        if 'unmanned_surface_vehicles' in objects:
            for usv in objects['unmanned_surface_vehicles']:
                pos = usv['initial_position']
                self.objects[usv['id']] = VesselState(
                    id=usv['id'],
                    name=usv['name'],
                    type=usv['type'],
                    position=Position(pos['x'], pos['y'], pos['z']),
                    heading=0,
                    speed_knots=usv.get('initial_speed_knots', 0),
                    status='active',
                    battery_percent=usv.get('battery_percent', 100)
                )

        # ROV
        if 'remotely_operated_vehicles' in objects:
            for rov in objects['remotely_operated_vehicles']:
                pos = rov['initial_position']
                self.objects[rov['id']] = VesselState(
                    id=rov['id'],
                    name=rov['name'],
                    type=rov['type'],
                    position=Position(pos['x'], pos['y'], pos['z']),
                    heading=0,
                    speed_knots=0,
                    status=rov.get('operating_status', 'idle'),
                    depth=abs(pos['y']),
                    battery_percent=rov.get('battery_percent', 100)
                )

        # AUV
        if 'autonomous_underwater_vehicles' in objects:
            for auv in objects['autonomous_underwater_vehicles']:
                pos = auv['initial_position']
                self.objects[auv['id']] = VesselState(
                    id=auv['id'],
                    name=auv['name'],
                    type=auv['type'],
                    position=Position(pos['x'], pos['y'], pos['z']),
                    heading=0,
                    speed_knots=auv.get('cruise_speed_knots', 0),
                    status='active',
                    depth=abs(pos['y']),
                    battery_percent=auv.get('battery_percent', 100)
                )

        print(f"✅ {len(self.objects)}개 객체 초기화")

    def _update_positions(self, delta_time: float):
        """위치 업데이트 (경로 따라)"""
        scenario = self.scenario['scenario']
        objects = self.scenario['objects']

        # 선박 경로 업데이트
        if 'surface_vessels' in objects:
            for vessel in objects['surface_vessels']:
                vessel_id = vessel['id']
                if vessel_id not in self.objects:
                    continue

                if 'waypoints' in vessel and len(vessel['waypoints']) > 0:
                    # 가장 가까운 웨이포인트 찾기
                    current = self.objects[vessel_id]
                    for i, wp in enumerate(vessel['waypoints']):
                        if self.current_time >= wp['time_seconds']:
                            target_pos = Position(wp['x'], current.position.y, wp['z'])
                            self._move_towards(vessel_id, target_pos, delta_time)

        # 드론/USV 랜덤 이동
        for obj_id, obj in self.objects.items():
            if obj.type in ['drone', 'aerial_drone', 'usv']:
                # 간단한 원형 패턴
                angle = (self.current_time / 10.0) * 2 * math.pi
                radius = 30
                obj.position.x += math.cos(angle) * radius * 0.01
                obj.position.z += math.sin(angle) * radius * 0.01

            # 배터리 감소
            if obj.type in ['drone', 'aerial_drone', 'usv', 'rov', 'auv']:
                obj.battery_percent = max(0, obj.battery_percent - 0.1)

    def _move_towards(self, obj_id: str, target: Position, delta_time: float):
        """객체를 목표 위치로 이동"""
        obj = self.objects[obj_id]
        dx = target.x - obj.position.x
        dz = target.z - obj.position.z
        distance = math.sqrt(dx**2 + dz**2)

        if distance > 1:  # 도착하지 않았으면
            obj.heading = math.degrees(math.atan2(dz, dx))
            # 속도에 따라 이동
            movement = (obj.speed_knots * 1.852 / 3600) * delta_time  # knots → m/s
            obj.position.x += (dx / distance) * movement
            obj.position.z += (dz / distance) * movement

    def _generate_events(self) -> List[Dict[str, Any]]:
        """현재 시간에 발생할 이벤트 반환"""
        events = []
        if 'events' in self.scenario and self.scenario['events']:
            for event in self.scenario['events']:
                if int(event['time_seconds']) == int(self.current_time):
                    events.append(event)
        return events

    def step(self, delta_time: float = 1.0):
        """시뮬레이션 한 스텝 진행"""
        self.current_time += delta_time
        self._update_positions(delta_time)

        # 이벤트 확인
        events = self._generate_events()
        if events:
            self.events.extend(events)
            for event in events:
                print(f"⚠️  Event at {self.current_time}s: {event['description']}")

    def get_state(self) -> Dict[str, Any]:
        """현재 시뮬레이션 상태 반환 (JSON 직렬화 가능)"""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'simulation_time_s': self.current_time,
            'objects': {
                obj_id: {
                    'id': obj.id,
                    'name': obj.name,
                    'type': obj.type,
                    'position': asdict(obj.position),
                    'heading': round(obj.heading, 2),
                    'speed': round(obj.speed_knots, 2),
                    'status': obj.status,
                    'depth': round(obj.depth, 1),
                    'battery': round(obj.battery_percent, 1)
                }
                for obj_id, obj in self.objects.items()
            },
            'recent_events': self.events[-10:],  # 최근 10개 이벤트
            'total_objects': len(self.objects)
        }

    def export_json(self, output_file: str):
        """현재 상태를 JSON으로 내보내기"""
        with open(output_file, 'w') as f:
            json.dump(self.get_state(), f, indent=2)
        print(f"💾 상태 저장: {output_file}")


class SimulationHTTPHandler(SimpleHTTPRequestHandler):
    """시뮬레이션 상태를 제공하는 HTTP 핸들러"""
    simulator = None

    def do_GET(self):
        if self.path == '/api/state':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            state = self.simulator.get_state()
            self.wfile.write(json.dumps(state).encode())
        elif self.path == '/':
            self.path = '/graphics/ocean-visualization.html'
            super().do_GET()
        else:
            super().do_GET()

    def log_message(self, format, *args):
        # 조용하게
        pass


def run_simulator(scenario_file: str, port: int = 8000, real_time: bool = False):
    """시뮬레이터 실행"""
    print(f"\n🚀 해양 운영 시스템 시뮬레이터 시작")
    print(f"📄 시나리오: {scenario_file}")
    print(f"🌐 서버: http://localhost:{port}")
    print(f"⏱️  모드: {'실시간' if real_time else '고속'}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    simulator = NavalSimulator(scenario_file)
    SimulationHTTPHandler.simulator = simulator

    # HTTP 서버 시작 (별도 스레드)
    handler = SimulationHTTPHandler
    httpd = socketserver.TCPServer(("", port), handler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    # 시뮬레이션 루프
    try:
        step_count = 0
        last_time = time.time()
        total_duration = simulator.scenario['scenario'].get('duration_seconds', 3600)

        while simulator.current_time < total_duration:
            simulator.step(delta_time=1.0)
            step_count += 1

            # 1초마다 상태 출력
            if step_count % 1 == 0:
                state = simulator.get_state()
                elapsed = (time.time() - last_time)
                print(f"⏱️  {simulator.current_time:.0f}s | "
                      f"객체: {state['total_objects']} | "
                      f"배터리: {min(s['battery'] for s in state['objects'].values()):.0f}% | "
                      f"이벤트: {len(state['recent_events'])}", end='\r')

            # 실시간 모드
            if real_time:
                time.sleep(1)
            else:
                # 고속 모드: 가능한 한 빨리
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n\n⛔ 시뮬레이션 종료")
        simulator.export_json('data/simulation_final_state.json')
    finally:
        httpd.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='해양 운영 시스템 시뮬레이터')
    parser.add_argument('--scenario', default='scenarios/naval-ops.yaml',
                       help='시나리오 YAML 파일')
    parser.add_argument('--port', type=int, default=8000,
                       help='HTTP 서버 포트')
    parser.add_argument('--realtime', action='store_true',
                       help='실시간 모드 (1x 속도)')

    args = parser.parse_args()
    run_simulator(args.scenario, args.port, args.realtime)
