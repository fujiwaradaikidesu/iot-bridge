import asyncio
import json
import logging
import yaml
import paho.mqtt.client as mqtt
from typing import Dict, Any
import importlib
import os
from dotenv import load_dotenv
import queue

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
        self.setup_mqtt()

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
                logger.info(f"Subscribed to topic: {topic}")
        else:
            logger.error(f"Connection failed with code {rc}")

    def on_message(self, client, userdata, message):
        try:
            topic = message.topic
            payload = json.loads(message.payload.decode())
            logger.info(f"Received message on topic {topic}: {payload}")

            # メッセージをキューに追加し、メインスレッドで処理
            self.message_queue.put((topic, payload))
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def initialize_handlers(self):
        for device_name, device_config in self.config["devices"].items():
            try:
                # ハンドラクラスを動的にインポート
                module = importlib.import_module(f"handlers.{device_name.lower()}")
                handler_class = getattr(module, device_config["handler"])
                handler = handler_class()
                await handler.initialize(device_config)
                self.handlers[device_config["handler"]] = handler
                logger.info(f"Initialized handler for {device_name}")
            except Exception as e:
                logger.error(f"Failed to initialize handler for {device_name}: {e}")

    async def process_messages(self):
        """キューからメッセージを取り出して処理する"""
        while True:
            try:
                topic, payload = self.message_queue.get_nowait()
                # トピックに対応するハンドラを探す
                for device_config in self.config["devices"].values():
                    if topic in device_config["topics"]:
                        handler = self.handlers.get(device_config["handler"])
                        if handler:
                            await handler.handle_message(topic, payload)
                        else:
                            logger.warning(f"No handler found for topic: {topic}")
                        break
                self.message_queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error processing queued message: {e}")

    def start(self):
        mqtt_config = self.config["mqtt"]
        self.client.connect(mqtt_config["broker"], mqtt_config["port"], 60)
        self.client.loop_start()

async def main():
    # 設定ファイルの読み込み
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    # ブリッジの初期化と開始
    bridge = MQTTBridge(config)
    await bridge.initialize_handlers()
    bridge.start()

    # メインループ
    try:
        while True:
            await bridge.process_messages()
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        bridge.client.loop_stop()
        bridge.client.disconnect()

if __name__ == "__main__":
    asyncio.run(main()) 