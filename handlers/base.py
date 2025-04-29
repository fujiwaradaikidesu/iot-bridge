from abc import ABC, abstractmethod
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class DeviceHandler(ABC):
    @abstractmethod
    async def handle_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """MQTTメッセージを処理し、APIを呼び出す"""
        pass

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> None:
        """設定を読み込み、ハンドラを初期化"""
        pass 