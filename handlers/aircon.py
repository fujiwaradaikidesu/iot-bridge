import logging
from typing import Dict, Any
import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed
from .base import DeviceHandler

logger = logging.getLogger(__name__)

class AirconHandler(DeviceHandler):
    def __init__(self):
        self.api_url = None

    async def initialize(self, config: Dict[str, Any]) -> None:
        self.api_url = config["api_url"]
        if self.api_url.startswith("http://"):
            logger.warning(f"Invalid API URL format: {self.api_url}. It contains duplicate 'http://'. Please check config.yaml.")
        logger.info(f"AirconHandler initialized with API URL: {self.api_url}")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def call_api(self, data: Dict[str, Any]) -> None:
        # データを文字列に変換
        converted_data = {k: str(v) for k, v in data.items()}
        logger.info(f"Sending request with query parameters: {converted_data}")
        logger.info(f"Request URL: {self.api_url}/aircon/control")

        #################################################### 
        ## 電源OFFの場合は下記のパラメータを設定する
        if converted_data["power_on"] == "false":
            converted_data["mode"] = "cool"
            converted_data["temperature"] = "23"
        #################################################### 

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(f"{self.api_url}/aircon/control", params=converted_data) as resp:
                    if resp.status != 200:
                        response_text = await resp.text()
                        logger.error(f"API call failed with status {resp.status}: {response_text}")
                        raise Exception(f"API call failed: {resp.status} - {response_text}")
                    logger.info("Aircon control command sent successfully")
            except aiohttp.ClientError as e:
                logger.error(f"Client error during API call: {str(e)}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error during API call: {str(e)}")
                raise

    async def handle_message(self, topic: str, payload: Dict[str, Any]) -> None:
        try:
            logger.info(f"Handling aircon message: {payload}")
            await self.call_api(payload)
        except Exception as e:
            logger.error(f"Error handling aircon message: {e}")
            raise 