import asyncio
import json
import logging
import queue
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import importlib

import paho.mqtt.client as mqtt
import yaml
from dotenv import load_dotenv

from schedule_manager import ScheduleManager
from time_sync import DEFAULT_NTP_SERVER, SYNC_INTERVAL_SECONDS, TimeSyncService

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
load_dotenv()


class MQTTBridge:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.handlers: Dict[str, Any] = {}
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.message_queue = queue.Queue()

        self.schedule_manager: Optional[ScheduleManager] = None
        self.time_sync: Optional[TimeSyncService] = None
        self.scheduler_topics: Dict[str, str] = {}
        self.scheduler_response_topic: Optional[str] = None
        self.schedule_tick_interval = 30
        self._next_schedule_check = time.monotonic()

        self._setup_scheduler()
        self.setup_mqtt()

    def _setup_scheduler(self):
        scheduler_config = self.config.get("scheduler", {})
        if not scheduler_config.get("enabled", False):
            return

        timezone_offset = scheduler_config.get("timezone_offset_minutes", 0)
        storage_path = scheduler_config.get("storage_path", "schedules.json")
        self.schedule_manager = ScheduleManager(
            storage_path=storage_path,
            timezone_offset_minutes=timezone_offset,
        )

        ntp_server = scheduler_config.get("ntp_server", DEFAULT_NTP_SERVER)
        sync_interval = scheduler_config.get("sync_interval_seconds", SYNC_INTERVAL_SECONDS)
        self.time_sync = TimeSyncService(ntp_server=ntp_server, interval=sync_interval)
        self.time_sync.start()

        self.scheduler_topics = scheduler_config.get("topics") or {
            "create": "aircon/schedule/create",
            "update": "aircon/schedule/update",
            "delete": "aircon/schedule/delete",
            "list": "aircon/schedule/list",
        }
        self.scheduler_response_topic = scheduler_config.get(
            "response_topic", "aircon/schedule/response"
        )
        self.schedule_tick_interval = scheduler_config.get("tick_interval_seconds", 30)

    def setup_mqtt(self):
        mqtt_config = self.config["mqtt"]
        self.client.username_pw_set(mqtt_config["username"], mqtt_config["password"])
        self.client.tls_set()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("MQTT Connected")
            for topic in self.config["mqtt"]["topics"]:
                client.subscribe(topic)
                logger.info("Subscribed to topic: %s", topic)
            for topic in self.scheduler_topics.values():
                client.subscribe(topic)
                logger.info("Subscribed to scheduler topic: %s", topic)
        else:
            logger.error("Connection failed with code %s", rc)

    def on_message(self, client, userdata, message):
        try:
            topic = message.topic
            payload = json.loads(message.payload.decode())
            logger.info("Received message on topic %s: %s", topic, payload)

            if topic in self.scheduler_topics.values():
                self._handle_scheduler_message(topic, payload)
            else:
                self.message_queue.put((topic, payload))
        except Exception as exc:
            logger.error("Error processing message: %s", exc)

    async def initialize_handlers(self):
        for device_name, device_config in self.config["devices"].items():
            try:
                module = importlib.import_module(f"handlers.{device_name.lower()}")
                handler_class = getattr(module, device_config["handler"])
                handler = handler_class()
                await handler.initialize(device_config)
                self.handlers[device_config["handler"]] = handler
                logger.info("Initialized handler for %s", device_name)
            except Exception as exc:
                logger.error("Failed to initialize handler for %s: %s", device_name, exc)

    async def process_messages(self):
        while True:
            try:
                topic, payload = self.message_queue.get_nowait()
                await self._dispatch_to_device(topic, payload)
                self.message_queue.task_done()
            except queue.Empty:
                break
            except Exception as exc:
                logger.error("Error processing queued message: %s", exc)

    def start(self):
        mqtt_config = self.config["mqtt"]
        self.client.connect(mqtt_config["broker"], mqtt_config["port"], 60)
        self.client.loop_start()

    def shutdown(self):
        if self.time_sync:
            self.time_sync.stop()
        self.client.loop_stop()
        self.client.disconnect()

    async def process_schedules(self):
        if not (self.schedule_manager and self.time_sync):
            return

        current_monotonic = time.monotonic()
        if current_monotonic < self._next_schedule_check:
            return
        self._next_schedule_check = current_monotonic + self.schedule_tick_interval

        current_time = self.time_sync.now()
        due_schedules = self.schedule_manager.due_schedules(current_time)
        for schedule in due_schedules:
            await self._execute_schedule(schedule)

    async def _dispatch_to_device(self, topic: str, payload: Dict[str, Any]) -> bool:
        for device_config in self.config["devices"].values():
            if topic in device_config["topics"]:
                handler = self.handlers.get(device_config["handler"])
                if handler:
                    await handler.handle_message(topic, payload)
                    return True
                logger.warning("No handler instance found for topic: %s", topic)
                return False
        logger.warning("No device handler configured for topic: %s", topic)
        return False

    async def _execute_schedule(self, schedule: Dict[str, Any]):
        topic = schedule.get("topic", "aircon/control")
        payload = schedule.get("payload") or self._build_payload(schedule)

        success = await self._dispatch_to_device(topic, payload)
        status = "success" if success else "error"
        error_message = None if success else "Failed to dispatch schedule command"
        self._publish_schedule_response(
            action="trigger",
            status=status,
            data={"schedule_id": schedule.get("id"), "topic": topic, "payload": payload},
            error=error_message,
        )

    def _build_payload(self, schedule: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "power_on": schedule.get("power_on", True),
            "mode": schedule.get("mode", "cool"),
            "temperature": schedule.get("temperature", 23),
            "fan_speed": schedule.get("fan_speed", 3),
        }

    def _handle_scheduler_message(self, topic: str, payload: Dict[str, Any]):
        if not self.schedule_manager:
            logger.warning("Scheduler message received but scheduler disabled")
            return

        action = next((key for key, value in self.scheduler_topics.items() if value == topic), None)
        request_id = payload.get("request_id")

        try:
            if action in {"create", "update"}:
                schedule_data = payload.get("schedule", payload)
                saved_schedule = self.schedule_manager.upsert_schedule(schedule_data)
                self._publish_schedule_response(
                    action=action,
                    status="success",
                    data={"schedule": saved_schedule},
                    request_id=request_id,
                )
            elif action == "delete":
                schedule_id = payload.get("id") or payload.get("schedule_id")
                if not schedule_id:
                    raise ValueError("schedule id is required for delete action")
                deleted = self.schedule_manager.delete_schedule(schedule_id)
                status = "success" if deleted else "not_found"
                self._publish_schedule_response(
                    action=action,
                    status=status,
                    data={"id": schedule_id, "deleted": deleted},
                    request_id=request_id,
                )
            elif action == "list":
                schedules = self.schedule_manager.list_schedules()
                self._publish_schedule_response(
                    action=action,
                    status="success",
                    data={"schedules": schedules},
                    request_id=request_id,
                )
            else:
                raise ValueError(f"Unsupported scheduler action for topic {topic}")
        except Exception as exc:
            logger.error("Error handling scheduler message: %s", exc)
            self._publish_schedule_response(
                action=action or "unknown",
                status="error",
                error=str(exc),
                request_id=request_id,
            )

    def _publish_schedule_response(
        self,
        action: str,
        status: str,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        if not self.scheduler_response_topic:
            return
        payload = {
            "action": action,
            "status": status,
            "data": data,
            "error": error,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.client.publish(self.scheduler_response_topic, json.dumps(payload))


async def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    bridge = MQTTBridge(config)
    await bridge.initialize_handlers()
    bridge.start()

    try:
        while True:
            await bridge.process_messages()
            await bridge.process_schedules()
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        bridge.shutdown()


if __name__ == "__main__":
    asyncio.run(main())