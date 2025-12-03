import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import ntplib

logger = logging.getLogger(__name__)

DEFAULT_NTP_SERVER = "pool.ntp.org"
SYNC_INTERVAL_SECONDS = 60 * 60  # 1 hour


class TimeSyncService:
    """Simple NTP-based time synchronization helper."""

    def __init__(self, ntp_server: str = DEFAULT_NTP_SERVER, interval: int = SYNC_INTERVAL_SECONDS):
        self.ntp_server = ntp_server
        self.interval = interval
        self._offset = 0.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def now(self) -> datetime:
        """Return current synchronized time in UTC."""
        return datetime.now(timezone.utc) + timedelta(seconds=self._offset)

    def _sync_loop(self):
        while not self._stop_event.is_set():
            self._sync_once()
            self._stop_event.wait(self.interval)

    def _sync_once(self):
        client = ntplib.NTPClient()
        try:
            response = client.request(self.ntp_server)
            self._offset = response.offset
            logger.info("Time synchronized via NTP (offset=%.6fs)", self._offset)
        except Exception as exc:
            logger.warning("Failed to sync time via NTP: %s", exc)


