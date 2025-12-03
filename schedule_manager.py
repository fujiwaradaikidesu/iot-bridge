import json
import logging
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_STORAGE = "schedules.json"


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        logger.warning("Invalid date format: %s", value)
        return None


class ScheduleManager:
    def __init__(self, storage_path: str = DEFAULT_STORAGE, timezone_offset_minutes: int = 0):
        self.storage_path = storage_path
        self.timezone_offset = timedelta(minutes=timezone_offset_minutes)
        self.schedules: List[Dict[str, Any]] = []
        self._load()

    def list_schedules(self) -> List[Dict[str, Any]]:
        return self.schedules

    def upsert_schedule(self, schedule: Dict[str, Any]) -> Dict[str, Any]:
        schedule_id = schedule.get("id") or f"schedule_{uuid.uuid4().hex[:8]}"
        schedule["id"] = schedule_id
        schedule.setdefault("enabled", True)
        schedule.setdefault("fan_speed", 3)
        schedule.setdefault("mode", "cool")
        schedule.setdefault("temperature", 23)
        schedule.setdefault("topic", "aircon/control")
        schedule.setdefault("repeat", {"type": "daily"})

        existing_index = next((i for i, s in enumerate(self.schedules) if s["id"] == schedule_id), None)
        if existing_index is not None:
            self.schedules[existing_index] = schedule
        else:
            self.schedules.append(schedule)
        self._save()
        return schedule

    def delete_schedule(self, schedule_id: str) -> bool:
        initial_len = len(self.schedules)
        self.schedules = [s for s in self.schedules if s["id"] != schedule_id]
        deleted = len(self.schedules) != initial_len
        if deleted:
            self._save()
        return deleted

    def due_schedules(self, current_utc: datetime) -> List[Dict[str, Any]]:
        local_time = current_utc + self.timezone_offset
        current_slot = local_time.strftime("%Y-%m-%dT%H:%M")
        current_time = local_time.strftime("%H:%M")
        current_date = local_time.date()
        weekday = local_time.weekday()

        due: List[Dict[str, Any]] = []
        changed = False

        for schedule in self.schedules:
            if not schedule.get("enabled", True):
                continue

            if schedule.get("time") != current_time:
                continue

            if not self._is_within_date_range(schedule, current_date):
                continue

            if not self._matches_repeat(schedule, weekday):
                continue

            last_slot = schedule.get("last_executed_slot")
            if last_slot == current_slot:
                continue

            schedule["last_executed_slot"] = current_slot
            due.append(schedule)
            changed = True

        if changed:
            self._save()

        return due

    def _is_within_date_range(self, schedule: Dict[str, Any], current_date: date) -> bool:
        start_date = _parse_date(schedule.get("start_date"))
        end_date = _parse_date(schedule.get("end_date"))

        if start_date and current_date < start_date:
            return False
        if end_date and current_date > end_date:
            return False
        return True

    def _matches_repeat(self, schedule: Dict[str, Any], weekday: int) -> bool:
        repeat = schedule.get("repeat", {"type": "daily"})
        repeat_type = repeat.get("type", "daily")

        if repeat_type == "daily":
            return True
        if repeat_type == "weekdays":
            return weekday < 5
        if repeat_type == "weekends":
            return weekday >= 5
        if repeat_type == "custom":
            days = repeat.get("days", [])
            return weekday in days
        return False

    def _load(self):
        if not os.path.exists(self.storage_path):
            self.schedules = []
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self.schedules = json.load(f)
        except Exception as exc:
            logger.error("Failed to load schedules: %s", exc)
            self.schedules = []

    def _save(self):
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self.schedules, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("Failed to save schedules: %s", exc)


