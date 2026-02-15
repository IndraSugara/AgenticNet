"""
Health & Monitoring Routes

Endpoints for system health checks, metrics, and network monitoring.
"""
from fastapi import APIRouter
import asyncio
import time
import httpx

from config import config
from modules.monitoring import monitoring
from modules.security import security
from tools.network_tools import network_tools
from web.websocket_manager import ws_manager

router = APIRouter()

# Global state for cached health status
_health_cache = {
    "status": "unknown",
    "ollama_connected": False,
    "model": config.OLLAMA_MODEL,
    "last_check": 0,
    "monitoring": {}
}


async def update_health_cache():
    """Update the health cache asynchronously"""
    global _health_cache
    try:
        ollama_ok = await _check_ollama_connection()
        _health_cache.update({
            "status": "healthy" if ollama_ok else "degraded",
            "ollama_connected": ollama_ok,
            "model": config.OLLAMA_MODEL,
            "last_check": time.time(),
            "monitoring": monitoring.get_health_summary()
        })
    except Exception as e:
        _health_cache.update({
            "status": "error",
            "ollama_connected": False,
            "error": str(e),
            "last_check": time.time()
        })


async def _check_ollama_connection() -> bool:
    """Check if Ollama is running by pinging /api/tags"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


def get_health_cache():
    """Get reference to health cache for other modules"""
    return _health_cache


async def health_check_background_task():
    """Background task to periodically check health"""
    while True:
        await update_health_cache()
        await asyncio.sleep(30)


async def network_monitor_task():
    """Background task to monitor network latency and bandwidth"""
    while True:
        try:
            latency_data = await asyncio.to_thread(network_tools.measure_latency)
            monitoring.update_network_metrics(latency=latency_data.get("latencies", []))
            
            bandwidth_data = await asyncio.to_thread(network_tools.get_bandwidth_stats)
            monitoring.update_network_metrics(bandwidth={
                "upload_rate_kbps": bandwidth_data.get("upload_rate_kbps", 0),
                "download_rate_kbps": bandwidth_data.get("download_rate_kbps", 0)
            })
        except Exception as e:
            print(f"⚠️ Network monitor error: {e}")
        await asyncio.sleep(10)


async def metrics_broadcast_task():
    """Background task to broadcast metrics via WebSocket every 5 seconds"""
    while True:
        try:
            if ws_manager.get_connection_count("metrics") > 0:
                metrics = monitoring.get_current_metrics()
                if metrics:
                    metrics_data = metrics.to_dict()
                    net_metrics = monitoring.get_network_metrics()
                    metrics_data["latency"] = net_metrics.get("latency", [])
                    metrics_data["bandwidth"] = net_metrics.get("bandwidth", {})
                    await ws_manager.broadcast_metrics(metrics_data)
        except Exception as e:
            print(f"⚠️ Metrics broadcast error: {e}")
        await asyncio.sleep(5)


# --- Health Endpoints ---

@router.get("/health")
async def health_check():
    """Check system health (non-blocking, uses cached status)"""
    if time.time() - _health_cache["last_check"] < 5:
        return _health_cache
    await update_health_cache()
    return _health_cache


@router.get("/monitoring/status")
async def get_monitoring_status():
    """Get current monitoring status"""
    return monitoring.get_health_summary()


@router.get("/monitoring/metrics")
async def get_system_metrics():
    """Get real-time system metrics (CPU, RAM, Disk, Network)"""
    metrics = await asyncio.to_thread(monitoring.collect_system_metrics)
    if metrics:
        return {"success": True, "metrics": metrics.to_dict()}
    return {"success": False, "error": "Could not collect system metrics. Is psutil installed?"}


@router.get("/monitoring/trends/{metric_name}")
async def get_metric_trend(metric_name: str, window: int = 10):
    """Get trend analysis for a specific metric"""
    return monitoring.analyze_trend(metric_name, window)


@router.get("/monitoring/metrics/detailed")
async def get_detailed_metrics():
    """Get detailed system metrics including per-interface data"""
    metrics = await asyncio.to_thread(monitoring.get_current_metrics)
    if metrics:
        return {"success": True, "metrics": metrics.to_dict()}
    return {"success": False, "error": "Could not collect detailed metrics. Is psutil installed?"}


@router.get("/monitoring/interfaces/{interface_name}")
async def get_interface_details(interface_name: str):
    """Get detailed statistics for a specific network interface"""
    details = await asyncio.to_thread(monitoring.get_interface_details, interface_name)
    if details:
        return {"success": True, "interface": details}
    return {"success": False, "error": f"Interface '{interface_name}' not found"}


@router.get("/monitoring/interfaces/{interface_name}/history")
async def get_interface_history_endpoint(interface_name: str, hours: int = 1):
    """Get historical data for a specific interface"""
    history = await asyncio.to_thread(monitoring.get_interface_history, interface_name, hours)
    return {"success": True, "interface_name": interface_name, "hours": hours, "data": history}


@router.get("/monitoring/history/{metric_name}")
async def get_metric_history_endpoint(metric_name: str, hours: int = 1):
    """Get historical data for a specific metric"""
    history = await asyncio.to_thread(monitoring.get_metric_history, metric_name, hours)
    return {"success": True, "metric_name": metric_name, "hours": hours, "data": history}


# --- Network Endpoints ---

@router.get("/network/interfaces")
async def get_network_interfaces():
    """Get all network interfaces with status and statistics"""
    return await asyncio.to_thread(network_tools.get_interfaces)


@router.get("/network/connections")
async def get_network_connections():
    """Get active network connections"""
    return await asyncio.to_thread(network_tools.get_connections)


@router.get("/network/latency")
async def get_network_latency():
    """Measure latency to common hosts (Google DNS, Cloudflare, Google)"""
    return await asyncio.to_thread(network_tools.measure_latency)


@router.get("/network/bandwidth")
async def get_network_bandwidth():
    """Get current bandwidth statistics (requires ~1 second)"""
    return await asyncio.to_thread(network_tools.get_bandwidth_stats)


# --- Security Endpoints ---

@router.get("/security/status")
async def get_security_status():
    """Get security findings summary"""
    return security.get_risk_summary()


@router.post("/security/analyze")
async def analyze_config(config_text: str, device_type: str = "generic"):
    """Analyze network device configuration"""
    findings = await asyncio.to_thread(security.analyze_config, config_text, device_type)
    return {
        "findings_count": len(findings),
        "findings": [f.to_dict() for f in findings]
    }


# --- LLM Info ---

@router.get("/llm/info")
async def get_llm_info():
    """Get current LLM provider information"""
    return {
        "provider": "ollama",
        "model": config.OLLAMA_MODEL,
        "host": config.OLLAMA_HOST,
        "connected": _health_cache.get("ollama_connected", False)
    }
