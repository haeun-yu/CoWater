from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4
from dataclasses import asdict

from src.core.models import MissionRecord, normalize_mission_status, normalize_task_status
from src.db.connection import DatabaseConnection, get_db
from src.db.schema import init_schema

logger = logging.getLogger(__name__)


class MissionRegistry:
    """Mission lifecycle tracking registry with optional SQLite persistence"""
    
    def __init__(self, use_db: bool = False, db_path: str = None) -> None:
        """
        Initialize Mission Registry
        
        Args:
            use_db: Whether to use SQLite persistence (default: False for backward compatibility)
            db_path: Path to SQLite database file
        """
        self.use_db = use_db
        self.db: Optional[DatabaseConnection] = None
        
        # In-memory fallback
        self._missions: Dict[str, MissionRecord] = {}
        self._response_to_mission: Dict[str, str] = {}
        
        if self.use_db:
            try:
                self.db = get_db(db_path)
                init_schema(self.db.get_connection())
                logger.info("✅ MissionRegistry using SQLite persistence")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize SQLite, falling back to memory: {e}")
                self.use_db = False
    
    def create_mission(
        self,
        response_id: str,
        alert_id: str,
        event_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MissionRecord:
        """새 Mission 생성"""
        mission_id = f"mission-{uuid4()}"
        mission = MissionRecord(
            mission_id=mission_id,
            response_id=response_id,
            alert_id=alert_id,
            event_id=event_id,
            status="READY",
            metadata=metadata or {},
        )
        
        if self.use_db and self.db:
            self._save_mission_to_db(mission)
        else:
            self._missions[mission_id] = mission
            self._response_to_mission[response_id] = mission_id
        
        return mission
    
    def get_mission(self, mission_id: str) -> MissionRecord:
        """Mission 조회"""
        if self.use_db and self.db:
            mission = self._load_mission_from_db(mission_id)
            if mission is None:
                raise KeyError(f"Mission not found: {mission_id}")
            return mission
        else:
            mission = self._missions.get(mission_id)
            if mission is None:
                raise KeyError(f"Mission not found: {mission_id}")
            return mission
    
    def get_mission_by_response(self, response_id: str) -> Optional[MissionRecord]:
        """Response로부터 관련 Mission 조회"""
        if self.use_db and self.db:
            cursor = self.db.execute(
                "SELECT mission_id FROM missions WHERE response_id = ?",
                (response_id,)
            )
            result = cursor.fetchone()
            if result:
                mission_id = result[0]
                return self._load_mission_from_db(mission_id)
            return None
        else:
            mission_id = self._response_to_mission.get(response_id)
            if mission_id is None:
                return None
            return self._missions.get(mission_id)
    
    def list_missions(self) -> List[MissionRecord]:
        """모든 Mission 목록 반환"""
        if self.use_db and self.db:
            cursor = self.db.execute("SELECT mission_id FROM missions ORDER BY mission_id")
            results = cursor.fetchall()
            missions = []
            for row in results:
                mission = self._load_mission_from_db(row[0])
                if mission:
                    missions.append(mission)
            return missions
        else:
            return [self._missions[mission_id] for mission_id in sorted(self._missions)]
    
    def list_missions_by_status(self, status: str) -> List[MissionRecord]:
        """특정 상태의 Mission 목록 반환"""
        normalized_status = normalize_mission_status(status)
        if self.use_db and self.db:
            cursor = self.db.execute(
                "SELECT mission_id FROM missions WHERE status = ? ORDER BY mission_id",
                (normalized_status,)
            )
            results = cursor.fetchall()
            missions = []
            for row in results:
                mission = self._load_mission_from_db(row[0])
                if mission:
                    missions.append(mission)
            return missions
        else:
            return [m for m in self._missions.values() if normalize_mission_status(m.status) == normalized_status]
    
    def update_mission_status(self, mission_id: str, status: str) -> MissionRecord:
        """Mission 상태 업데이트"""
        mission = self.get_mission(mission_id)
        mission.touch(status)
        
        if self.use_db and self.db:
            self._save_mission_to_db(mission)
        else:
            self._missions[mission_id] = mission
        
        return mission

    def record_step_execution(
        self,
        mission_id: str,
        step_id: str,
        execution_result: Dict[str, Any],
    ) -> MissionRecord:
        """Step 실행 결과 기록"""
        mission = self.get_mission(mission_id)
        
        # Find or create step state
        step_state = None
        for state in mission.step_states:
            if state.get("step_id") == step_id:
                step_state = state
                break
        
        if step_state is None:
            step_state = {
                "step_id": step_id,
                "status": normalize_task_status(execution_result.get("status")),
                "tasks": execution_result.get("tasks", []),
                "execution_results": [],
            }
            mission.step_states.append(step_state)
        else:
            step_state["status"] = normalize_task_status(execution_result.get("status", step_state.get("status")))
            if "tasks" in execution_result:
                step_state["tasks"] = execution_result["tasks"]
        
        # Append execution results
        if "execution_results" in execution_result:
            step_state["execution_results"].extend(execution_result["execution_results"])
        
        mission.touch()
        
        if self.use_db and self.db:
            self._save_mission_to_db(mission)
        else:
            self._missions[mission_id] = mission
        
        return mission

    def complete_mission(
        self,
        mission_id: str,
        completion_report: Dict[str, Any],
    ) -> MissionRecord:
        """Mission 완료 및 보고서 저장"""
        mission = self.get_mission(mission_id)
        mission.completion_report = completion_report
        mission.touch("COMPLETED")
        
        if self.use_db and self.db:
            self._save_mission_to_db(mission)
        else:
            self._missions[mission_id] = mission
        
        return mission

    def abort_mission(
        self,
        mission_id: str,
        reason: str,
    ) -> MissionRecord:
        """Mission abort (실패)"""
        mission = self.get_mission(mission_id)
        mission.completion_report = {
            "status": "FAILED",
            "reason": reason,
            "timestamp": mission.updated_at,
        }
        mission.touch("FAILED")
        
        if self.use_db and self.db:
            self._save_mission_to_db(mission)
        else:
            self._missions[mission_id] = mission
        
        return mission

    def get_mission_stats(self) -> Dict[str, Any]:
        """Mission 통계 반환"""
        all_missions = self.list_missions()
        return {
            "total": len(all_missions),
            "ready": len([m for m in all_missions if normalize_mission_status(m.status) == "READY"]),
            "in_progress": len([m for m in all_missions if normalize_mission_status(m.status) == "IN_PROGRESS"]),
            "completed": len([m for m in all_missions if normalize_mission_status(m.status) == "COMPLETED"]),
            "failed": len([m for m in all_missions if normalize_mission_status(m.status) == "FAILED"]),
            "cancelled": len([m for m in all_missions if normalize_mission_status(m.status) == "CANCELLED"]),
        }

    def reset(self) -> None:
        """모든 Mission 초기화"""
        if self.use_db and self.db:
            cursor = self.db.execute("DELETE FROM missions")
            self.db.commit()
            logger.info("✅ Cleared all missions from SQLite")
        else:
            self._missions.clear()
            self._response_to_mission.clear()
            logger.info("✅ Cleared all missions from memory")
    
    # ======================== Private DB Methods ========================
    
    def _save_mission_to_db(self, mission: MissionRecord) -> None:
        """Save mission to SQLite database"""
        if not self.db:
            return
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Convert complex types to JSON strings
            step_states_json = json.dumps([asdict(s) if hasattr(s, '__dataclass_fields__') else s for s in mission.step_states])
            completion_report_json = json.dumps(mission.completion_report)
            metadata_json = json.dumps(mission.metadata)
            
            cursor.execute("""
                INSERT OR REPLACE INTO missions 
                (mission_id, response_id, alert_id, event_id, status, step_states, 
                 completion_report, metadata, created_at, started_at, completed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mission.mission_id,
                mission.response_id,
                mission.alert_id,
                mission.event_id,
                mission.status,
                step_states_json,
                completion_report_json,
                metadata_json,
                mission.created_at,
                mission.started_at,
                mission.completed_at,
                mission.updated_at,
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to save mission to DB: {e}")
            if self.db:
                self.db.rollback()
    
    def _load_mission_from_db(self, mission_id: str) -> Optional[MissionRecord]:
        """Load mission from SQLite database"""
        if not self.db:
            return None
        
        try:
            cursor = self.db.execute(
                "SELECT * FROM missions WHERE mission_id = ?",
                (mission_id,)
            )
            row = cursor.fetchone()
            
            if row:
                # Convert row to dict
                mission_dict = dict(row)
                
                # Parse JSON fields
                mission_dict["step_states"] = json.loads(mission_dict["step_states"])
                mission_dict["completion_report"] = json.loads(mission_dict["completion_report"])
                mission_dict["metadata"] = json.loads(mission_dict["metadata"])
                
                return MissionRecord(**mission_dict)
            
            return None
        except Exception as e:
            logger.error(f"❌ Failed to load mission from DB: {e}")
            return None
