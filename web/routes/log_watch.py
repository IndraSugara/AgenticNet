"""
Log Watch Routes

REST API endpoints for log monitoring control, anomaly viewing, and investigations.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from agent.log_watcher import log_watcher

router = APIRouter()


class LogWatchStartRequest(BaseModel):
    device_ip: Optional[str] = None
    interval: int = 60


class AnomalyPatternRequest(BaseModel):
    name: str
    pattern: str
    severity: str = "warning"
    description: str = ""


@router.post("/logs/watch/start")
async def start_log_watch(request: LogWatchStartRequest = LogWatchStartRequest()):
    """Start log watching"""
    if request.device_ip:
        log_watcher.add_device(request.device_ip, interval=request.interval)
    
    if not log_watcher.is_running:
        device_ips = [request.device_ip] if request.device_ip else None
        await log_watcher.start(device_ips)
    
    return {"success": True, "status": log_watcher.get_status()}


@router.post("/logs/watch/stop")
async def stop_log_watch():
    """Stop log watching"""
    if log_watcher.is_running:
        await log_watcher.stop()
    return {"success": True, "message": "Log watcher stopped"}


@router.get("/logs/watch/status")
async def get_log_watch_status():
    """Get log watcher status"""
    return log_watcher.get_status()


@router.get("/logs/anomalies")
async def get_anomalies(
    device_ip: str = None, 
    severity: str = None, 
    limit: int = 20
):
    """Get detected anomalies"""
    anomalies = log_watcher.get_anomalies(device_ip=device_ip, severity=severity, limit=limit)
    return {"count": len(anomalies), "anomalies": anomalies}


@router.get("/logs/watch/investigations")
async def get_investigations(unseen_only: bool = True):
    """Get auto-triggered agent investigations.
    
    Frontend polls this to detect new anomaly-triggered chats.
    """
    investigations = log_watcher.get_investigations(unseen_only=unseen_only)
    return {
        "count": len(investigations),
        "investigations": investigations
    }


@router.post("/logs/watch/investigations/{investigation_id}/seen")
async def mark_investigation_seen(investigation_id: str):
    """Mark an investigation as seen (frontend opened the chat)"""
    log_watcher.mark_investigation_seen(investigation_id)
    return {"success": True}


@router.get("/logs/patterns")
async def get_patterns():
    """Get all anomaly patterns"""
    patterns = log_watcher.get_patterns()
    return {"count": len(patterns), "patterns": patterns}


@router.post("/logs/patterns")
async def add_pattern(request: AnomalyPatternRequest):
    """Add a custom anomaly pattern"""
    log_watcher.add_pattern(
        name=request.name,
        pattern=request.pattern,
        severity=request.severity,
        description=request.description
    )
    return {"success": True, "message": f"Pattern '{request.name}' added"}
