"""
Infrastructure & Alert Routes

Endpoints for device management, monitoring control, alerts, and config import/export.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import List
import asyncio
import json

from agent.infrastructure import infrastructure
from agent.scheduler import scheduler
from agent.alerting import alert_manager, handle_device_alert

router = APIRouter()


# --- Request Models ---

class DeviceRequest(BaseModel):
    name: str
    ip: str
    type: str = "other"
    description: str = ""
    location: str = ""
    ports_to_monitor: List[int] = []
    check_interval: int = 60


# --- Device Management ---

@router.get("/infra/devices")
async def list_devices(device_type: str = None, status: str = None):
    """List all registered devices with optional filtering"""
    devices = infrastructure.list_devices(device_type=device_type, status=status)
    return {"count": len(devices), "devices": [d.to_dict() for d in devices]}


@router.post("/infra/devices")
async def add_device(request: DeviceRequest):
    """Add a new device to monitoring"""
    device = infrastructure.add_device(
        name=request.name,
        ip=request.ip,
        device_type=request.type,
        description=request.description,
        location=request.location,
        ports_to_monitor=request.ports_to_monitor,
        check_interval=request.check_interval
    )
    return {"success": True, "message": f"Device '{device.name}' added", "device": device.to_dict()}


@router.get("/infra/devices/{device_id}")
async def get_device(device_id: str):
    """Get device details"""
    device = infrastructure.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device.to_dict()


@router.put("/infra/devices/{device_id}")
async def update_device(device_id: str, request: DeviceRequest):
    """Update device configuration"""
    device = infrastructure.update_device(
        device_id,
        name=request.name,
        ip=request.ip,
        type=request.type,
        description=request.description,
        location=request.location,
        ports_to_monitor=request.ports_to_monitor,
        check_interval_seconds=request.check_interval
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True, "device": device.to_dict()}


@router.delete("/infra/devices/{device_id}")
async def delete_device(device_id: str):
    """Remove a device from monitoring"""
    success = infrastructure.remove_device(device_id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True, "message": "Device removed"}


@router.get("/infra/devices/{device_id}/status")
async def check_device_status(device_id: str):
    """Check device status immediately"""
    result = await scheduler.check_now(device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    device = infrastructure.get_device(device_id)
    return {"device": device.to_dict() if device else None, "last_check": result.to_dict()}


@router.get("/infra/summary")
async def get_infrastructure_summary():
    """Get overall infrastructure status summary"""
    return infrastructure.get_status_summary()


# --- Monitoring Control ---

@router.post("/infra/monitor/start")
async def start_monitoring():
    """Start the automatic monitoring scheduler"""
    if scheduler.is_running:
        return {"success": True, "message": "Monitoring already running"}
    scheduler.set_alert_callback(handle_device_alert)
    await scheduler.start()
    return {
        "success": True,
        "message": "Monitoring started",
        "devices_count": len(infrastructure.list_devices())
    }


@router.post("/infra/monitor/stop")
async def stop_monitoring():
    """Stop the automatic monitoring"""
    if not scheduler.is_running:
        return {"success": True, "message": "Monitoring not running"}
    await scheduler.stop()
    return {"success": True, "message": "Monitoring stopped"}


@router.get("/infra/monitor/status")
async def get_infra_monitoring_status():
    """Get current monitoring status"""
    return {
        "running": scheduler.is_running,
        "devices_monitored": len(infrastructure.list_devices()),
        "last_results": {k: v.to_dict() for k, v in scheduler.get_all_results().items()}
    }


@router.post("/infra/monitor/check-all")
async def check_all_devices():
    """Immediately check all devices"""
    results = await scheduler.check_all_now()
    return {"success": True, "checked": len(results), "results": {k: v.to_dict() for k, v in results.items()}}


# --- Alerts ---

@router.get("/infra/alerts")
async def get_alerts(severity: str = None, device_id: str = None, unresolved_only: bool = True, limit: int = 50):
    """Get alerts with optional filtering"""
    alerts = alert_manager.get_alerts(
        severity=severity,
        device_id=device_id,
        unresolved_only=unresolved_only,
        limit=limit
    )
    return {"count": len(alerts), "alerts": [a.to_dict() for a in alerts]}


@router.get("/infra/alerts/summary")
async def get_alerts_summary():
    """Get alert summary"""
    return alert_manager.get_summary()


@router.post("/infra/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, by: str = "user"):
    """Acknowledge an alert"""
    success = alert_manager.acknowledge(alert_id, by)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True, "message": "Alert acknowledged"}


@router.post("/infra/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Resolve an alert"""
    success = alert_manager.resolve(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True, "message": "Alert resolved"}


# --- Live Status WebSocket ---

@router.websocket("/infra/live")
async def infrastructure_live(websocket: WebSocket):
    """WebSocket for real-time infrastructure status updates"""
    await websocket.accept()
    try:
        await websocket.send_json({
            "type": "initial",
            "summary": infrastructure.get_status_summary(),
            "devices": [d.to_dict() for d in infrastructure.list_devices()],
            "alerts": [a.to_dict() for a in alert_manager.get_active_alerts()[:10]]
        })
        
        while True:
            await asyncio.sleep(5)
            await websocket.send_json({
                "type": "update",
                "summary": infrastructure.get_status_summary(),
                "devices": [d.to_dict() for d in infrastructure.list_devices()],
                "alerts_count": len(alert_manager.get_active_alerts()),
                "monitoring_running": scheduler.is_running
            })
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# --- Config Export/Import ---

@router.get("/infra/config/export")
async def export_config():
    """Export device configuration as JSON"""
    return {"config": infrastructure.export_config()}


@router.post("/infra/config/import")
async def import_config(config: dict):
    """Import device configuration from JSON"""
    try:
        count = infrastructure.import_config(json.dumps(config))
        return {"success": True, "imported": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
