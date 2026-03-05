"""
Loki Ingester — Background Pipeline: Loki → ChromaDB

Periodically polls Loki for new network device logs and embeds them
into ChromaDB for semantic search. Acts as the bridge between:
  - Loki  (fast keyword query, operational view)
  - ChromaDB (semantic search, RAG for agent investigation)

Also acts as the entry point that feeds new log lines into LogWatcher
for real-time anomaly detection.
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from agent.logging_config import get_logger

logger = get_logger("loki_ingester")


class LokiIngester:
    """
    Background service that bridges Loki ↔ ChromaDB.

    Flow:
        Loki (receives Syslog from OTel) ──poll──▶ LokiIngester
            ├── embed log lines ──▶ ChromaDB (semantic RAG)
            └── check anomaly ──────▶ LogWatcher.process_log_line()
    """

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_ingested_ts: int = 0   # nanosecond timestamp (Loki format)
        self._total_ingested: int = 0
        self._interval_seconds: int = 60  # default poll interval

    # ─── Lifecycle ──────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self, interval_seconds: int = None):
        """Start the ingestion loop."""
        if self._running:
            return

        if interval_seconds:
            self._interval_seconds = interval_seconds

        # Initialize last_ingested_ts to now (don't re-ingest old logs)
        if self._last_ingested_ts == 0:
            self._last_ingested_ts = int(time.time() * 1e9)

        self._running = True
        self._task = asyncio.create_task(self._ingest_loop())
        logger.info(
            f"🔄 Loki ingester started — polling every {self._interval_seconds}s"
        )

    async def stop(self):
        """Stop the ingestion loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️ Loki ingester stopped")

    # ─── Core Loop ──────────────────────────────────────────────────────────────

    async def _ingest_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                await self._fetch_and_process()
            except Exception as e:
                logger.error(f"Loki ingestion error: {e}")
            await asyncio.sleep(self._interval_seconds)

    async def _fetch_and_process(self):
        """Fetch new logs from Loki and route them to ChromaDB + LogWatcher."""
        from config import config

        loki_url = getattr(config, "loki_url", None) or "http://loki:3100"

        start_ns = self._last_ingested_ts
        end_ns = int(time.time() * 1e9)

        if end_ns <= start_ns:
            return

        query = '{job="syslog"}'
        params = {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": "1000",
            "direction": "forward",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{loki_url}/loki/api/v1/query_range",
                    params=params,
                )
                if resp.status_code != 200:
                    logger.warning(f"Loki returned {resp.status_code}: {resp.text[:200]}")
                    return

                data = resp.json()
        except httpx.ConnectError:
            logger.debug("Loki not reachable — skipping ingestion cycle")
            return
        except Exception as e:
            logger.error(f"Error querying Loki: {e}")
            return

        results = data.get("data", {}).get("result", [])
        new_lines = []

        for stream in results:
            labels = stream.get("stream", {})
            host = labels.get("host.name", labels.get("hostname", "unknown"))
            for ts_ns, log_line in stream.get("values", []):
                new_lines.append((host, log_line, int(ts_ns)))

        if not new_lines:
            self._last_ingested_ts = end_ns
            return

        logger.info(f"📥 Ingesting {len(new_lines)} new log lines from Loki")

        await self._embed_to_chroma(new_lines)
        await self._route_to_log_watcher(new_lines)

        self._total_ingested += len(new_lines)
        self._last_ingested_ts = end_ns

    # ─── ChromaDB Embedding ──────────────────────────────────────────────────────

    async def _embed_to_chroma(self, lines: list):
        """Embed new log lines into ChromaDB for semantic search."""
        try:
            from agent.rag_knowledge import get_knowledge_base
            kb = get_knowledge_base()

            # Batch into groups of 20 to avoid large embedding calls
            batch_size = 20
            for i in range(0, len(lines), batch_size):
                batch = lines[i:i + batch_size]
                for host, line, ts_ns in batch:
                    ts_human = datetime.fromtimestamp(
                        ts_ns / 1e9, tz=timezone.utc
                    ).isoformat()
                    content = (
                        f"Host: {host}\n"
                        f"Time: {ts_human}\n"
                        f"Log: {line}"
                    )
                    kb.add_document(
                        title=f"Network log — {host}",
                        content=content,
                        category="network_log",
                        tags=[host, "syslog", "loki"]
                    )

        except Exception as e:
            logger.debug(f"ChromaDB embedding skipped: {e}")

    # ─── LogWatcher Routing ──────────────────────────────────────────────────────

    async def _route_to_log_watcher(self, lines: list):
        """Pass new log lines to LogWatcher for anomaly detection."""
        try:
            from agent.log_watcher import log_watcher
            for host, line, _ in lines:
                await log_watcher.process_log_line(host=host, line=line)
        except Exception as e:
            logger.debug(f"LogWatcher routing skipped: {e}")

    # ─── Status ─────────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "interval_seconds": self._interval_seconds,
            "total_ingested": self._total_ingested,
            "last_ingested_at": (
                datetime.fromtimestamp(
                    self._last_ingested_ts / 1e9, tz=timezone.utc
                ).isoformat()
                if self._last_ingested_ts > 0 else "never"
            ),
        }


# Singleton
loki_ingester = LokiIngester()
