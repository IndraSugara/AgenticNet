"""
Application Log Viewer + Loki Network Log Routes

REST API endpoints for:
- Viewing AgenticNet application logs from the dashboard
- Querying Loki for network device syslog data
- Managing the Loki → ChromaDB ingestion pipeline
"""
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import Optional
import asyncio
import os
import time

import httpx

from agent.logging_config import read_log_lines, LOG_FILE

router = APIRouter()


# ─── Application Logs ───────────────────────────────────────────────────────

@router.get("/logs/app")
async def get_app_logs(
    level: Optional[str] = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    search: Optional[str] = Query(None, description="Text search filter"),
    limit: int = Query(100, ge=1, le=500, description="Max entries to return")
):
    """Get application log entries with optional filtering."""
    logs = read_log_lines(level=level, search=search, limit=limit)
    return {
        "logs": logs,
        "total": len(logs),
        "log_file": LOG_FILE
    }


@router.get("/logs/app/stream")
async def stream_app_logs():
    """SSE stream for real-time log tailing."""
    async def event_generator():
        if not os.path.exists(LOG_FILE):
            yield f"data: {{}}\n\n"
            return
        
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            # Seek to end of file
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"
                else:
                    await asyncio.sleep(1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


# ─── Loki Network Device Logs ─────────────────────────────────────────────────

def _get_loki_url() -> str:
    try:
        from config import config
        return getattr(config, "loki_url", None) or "http://loki:3100"
    except Exception:
        return "http://loki:3100"


@router.get("/logs/loki")
async def query_loki(
    q: str = Query('{job="syslog"}', description="LogQL query"),
    since_minutes: int = Query(10, ge=1, le=1440, description="Time range in minutes"),
    limit: int = Query(100, ge=1, le=1000, description="Max log entries")
):
    """
    Query network device logs from Loki using LogQL.
    
    Examples:
    - `{job="syslog"}` — all logs
    - `{job="syslog"} |= "error"` — filter by keyword  
    - `{job="syslog"} |~ "BGP|OSPF"` — routing events
    """
    loki_url = _get_loki_url()
    end_ts = int(time.time())
    start_ts = end_ts - (since_minutes * 60)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{loki_url}/loki/api/v1/query_range",
                params={"query": q, "start": str(start_ts), "end": str(end_ts),
                        "limit": str(limit), "direction": "backward"}
            )
            if resp.status_code != 200:
                return {"error": f"Loki error {resp.status_code}: {resp.text[:300]}", "logs": []}

            data = resp.json()
            results = data.get("data", {}).get("result", [])
            
            entries = []
            for stream in results:
                labels = stream.get("stream", {})
                host = labels.get("host.name", labels.get("hostname", "unknown"))
                for ts_ns, line in stream.get("values", []):
                    entries.append({
                        "timestamp": int(ts_ns) / 1e9,
                        "host": host,
                        "line": line,
                        "labels": labels,
                    })
            
            # Sort by timestamp descending
            entries.sort(key=lambda x: x["timestamp"], reverse=True)
            
            return {"query": q, "count": len(entries), "logs": entries}

    except httpx.ConnectError:
        return {"error": f"Loki tidak tersedia di {loki_url}", "logs": []}
    except Exception as e:
        return {"error": str(e), "logs": []}


@router.get("/logs/loki/recent")
async def get_recent_device_logs(
    since_minutes: int = Query(10, ge=1, le=1440),
    limit: int = Query(50, ge=1, le=500),
    host: Optional[str] = Query(None, description="Filter by hostname/IP")
):
    """Get recent network device log entries from Loki."""
    logql = '{job="syslog"}'
    if host:
        logql = f'{{job="syslog", "host.name"="{host}"}}'
    
    loki_url = _get_loki_url()
    end_ts = int(time.time())
    start_ts = end_ts - (since_minutes * 60)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{loki_url}/loki/api/v1/query_range",
                params={"query": logql, "start": str(start_ts), "end": str(end_ts),
                        "limit": str(limit), "direction": "backward"}
            )
            if resp.status_code != 200:
                return {"available": False, "error": f"Loki {resp.status_code}", "logs": []}

            data = resp.json()
            results = data.get("data", {}).get("result", [])
            entries = []
            for stream in results:
                labels = stream.get("stream", {})
                device_host = labels.get("host.name", labels.get("hostname", "unknown"))
                for ts_ns, line in stream.get("values", []):
                    entries.append({"timestamp": int(ts_ns) / 1e9, "host": device_host, "line": line})
            
            entries.sort(key=lambda x: x["timestamp"], reverse=True)
            return {"available": True, "count": len(entries), "logs": entries[:limit]}

    except httpx.ConnectError:
        return {"available": False, "error": "Loki tidak tersedia", "logs": []}


@router.get("/logs/loki/hosts")
async def get_loki_hosts():
    """List all hosts/devices that have sent logs to Loki."""
    loki_url = _get_loki_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{loki_url}/loki/api/v1/label/host.name/values"
            )
            if resp.status_code == 200:
                values = resp.json().get("data", [])
                return {"available": True, "hosts": values, "count": len(values)}
            return {"available": True, "hosts": [], "count": 0}
    except httpx.ConnectError:
        return {"available": False, "hosts": [], "error": "Loki tidak tersedia"}


# ─── Loki → ChromaDB Ingestion Pipeline ──────────────────────────────────────

@router.post("/logs/loki/ingest/start")
async def start_loki_ingestion(interval_seconds: int = 60):
    """Start the Loki → ChromaDB ingestion pipeline."""
    try:
        from agent.loki_ingester import loki_ingester
        if loki_ingester.is_running:
            return {"success": True, "message": "Ingester already running", 
                    "status": loki_ingester.get_status()}
        await loki_ingester.start(interval_seconds=interval_seconds)
        return {"success": True, "message": "Loki ingester started", 
                "status": loki_ingester.get_status()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/logs/loki/ingest/stop")
async def stop_loki_ingestion():
    """Stop the Loki → ChromaDB ingestion pipeline."""
    try:
        from agent.loki_ingester import loki_ingester
        await loki_ingester.stop()
        return {"success": True, "message": "Loki ingester stopped"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/logs/loki/ingest/status")
async def get_loki_ingestion_status():
    """Get the status of the Loki → ChromaDB ingestion pipeline."""
    try:
        from agent.loki_ingester import loki_ingester
        return {"success": True, **loki_ingester.get_status()}
    except Exception as e:
        return {"success": False, "error": str(e)}

