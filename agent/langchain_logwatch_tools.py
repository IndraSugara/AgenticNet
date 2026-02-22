"""
LangChain Log Watch Tools

Agent tools for managing automated log monitoring:
- Start/stop log watching
- Get status and anomalies
- Fetch device logs on-demand
- Add custom anomaly patterns
"""
import asyncio
from typing import Optional
from langchain_core.tools import tool

from agent.log_watcher import log_watcher


@tool
def start_log_watch(device_ip: str = None, interval: int = 60) -> str:
    """
    Start automated log monitoring for network devices.
    Reads device logs periodically and alerts on anomalies (link down, auth failure, errors, etc.).
    
    Args:
        device_ip: Optional specific device IP to watch. If empty, watches all inventory devices.
        interval: Check interval in seconds (default: 60)
    
    Returns:
        Status message
    """
    if device_ip:
        log_watcher.add_device(device_ip, interval=interval)
    
    if log_watcher.is_running:
        if device_ip:
            return f"✅ Device {device_ip} ditambahkan ke log watcher (interval: {interval}s)"
        return "ℹ️ Log watcher sudah berjalan"
    
    try:
        loop = asyncio.get_running_loop()
        device_ips = [device_ip] if device_ip else None
        loop.create_task(log_watcher.start(device_ips))
    except RuntimeError:
        device_ips = [device_ip] if device_ip else None
        asyncio.run(log_watcher.start(device_ips))
    
    status = log_watcher.get_status()
    return (
        f"✅ Log watcher dimulai!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Device terpantau : {status['devices_watched']}\n"
        f"Interval default : {interval}s\n"
        f"Patterns loaded  : {status['patterns_loaded']}\n"
        f"Auto-trigger     : Aktif\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Sistem akan otomatis membaca log dan mendeteksi anomali."
    )


@tool
def stop_log_watch() -> str:
    """
    Stop the automated log monitoring.
    
    Returns:
        Status message
    """
    if not log_watcher.is_running:
        return "ℹ️ Log watcher tidak sedang berjalan"
    
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(log_watcher.stop())
    except RuntimeError:
        asyncio.run(log_watcher.stop())
    
    return "⏹️ Log watcher dihentikan"


@tool
def get_log_watch_status() -> str:
    """
    Get current status of the log monitoring system.
    Shows which devices are being watched, check intervals, and anomaly count.
    
    Returns:
        Log watcher status details
    """
    status = log_watcher.get_status()
    
    lines = [
        f"📋 Log Watcher Status",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Running          : {'✅ Ya' if status['running'] else '❌ Tidak'}",
        f"Devices watched  : {status['devices_watched']}",
        f"Patterns loaded  : {status['patterns_loaded']}",
        f"Total anomalies  : {status['total_anomalies']}",
        f"Recent (1 jam)   : {status['recent_anomalies']}",
    ]
    
    if status["devices"]:
        lines.append("")
        lines.append("📱 Devices:")
        for ip, info in status["devices"].items():
            enabled = "✅" if info["enabled"] else "❌"
            trigger = "🤖" if info["auto_trigger"] else "—"
            lines.append(f"  {enabled} {ip} | {info['interval']}s | {trigger} | Last: {info['last_check']}")
    
    return "\n".join(lines)


@tool
def get_device_logs(device_ip: str) -> str:
    """
    Fetch current logs from a network device on-demand via SSH.
    Automatically uses the correct command for the device vendor.
    
    Args:
        device_ip: IP address of the device to fetch logs from
    
    Returns:
        Device log output
    """
    try:
        from tools.unified_commands import unified_commands
        
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = loop.run_in_executor(
                    pool, lambda: asyncio.run(unified_commands.get_logs(device_ip))
                )
                # Can't await here in sync context, use asyncio.run
                raise RuntimeError("Use async path")
        except RuntimeError:
            result = asyncio.run(unified_commands.get_logs(device_ip))
        
        if result.success:
            log_output = result.raw_output or "\n".join(result.data.get("logs", []))
            return (
                f"📋 Log dari {result.device_name or device_ip}\n"
                f"Perintah: {result.command}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{log_output}"
            )
        return f"❌ Gagal mengambil log: {result.error}"
    
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def get_recent_anomalies(device_ip: str = None, severity: str = None, limit: int = 10) -> str:
    """
    Get recent anomalies detected by the log watcher.
    
    Args:
        device_ip: Optional filter by device IP
        severity: Optional filter by severity (info, warning, critical)
        limit: Maximum number of anomalies to show (default: 10)
    
    Returns:
        List of detected anomalies
    """
    anomalies = log_watcher.get_anomalies(
        device_ip=device_ip,
        severity=severity,
        limit=limit
    )
    
    if not anomalies:
        return "✅ Tidak ada anomali terdeteksi."
    
    severity_emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
    
    lines = [f"🔍 Anomali Terdeteksi ({len(anomalies)} total):\n"]
    
    for a in anomalies:
        emoji = severity_emoji.get(a["severity"], "❓")
        lines.append(f"{emoji} [{a['severity'].upper()}] {a['device_name']} ({a['device_ip']})")
        lines.append(f"   {a['description']}")
        lines.append(f"   Log: {a['log_line'][:120]}")
        lines.append(f"   Time: {a['timestamp'][:19]} | {'🤖 Investigated' if a['investigated'] else '⏳ Pending'}")
        lines.append("")
    
    return "\n".join(lines)


@tool
def add_anomaly_pattern(name: str, pattern: str, severity: str = "warning", description: str = "") -> str:
    """
    Add a custom anomaly detection pattern to the log watcher.
    
    Args:
        name: Short name for the pattern (e.g., 'high_cpu')
        pattern: Regex pattern to match in log lines (e.g., 'cpu.*usage.*(9[0-9]|100)%')
        severity: Alert severity - info, warning, or critical (default: warning)
        description: Human-readable description of what this pattern detects
    
    Returns:
        Confirmation message
    """
    try:
        log_watcher.add_pattern(name, pattern, severity, description)
        return (
            f"✅ Pattern anomali baru ditambahkan:\n"
            f"  Name    : {name}\n"
            f"  Pattern : {pattern}\n"
            f"  Severity: {severity}\n"
            f"  Desc    : {description or name}"
        )
    except Exception as e:
        return f"❌ Gagal menambahkan pattern: {str(e)}"


# Export all log watch tools
def get_logwatch_tools() -> list:
    """Get all log watch tools"""
    return [
        start_log_watch,
        stop_log_watch,
        get_log_watch_status,
        get_device_logs,
        get_recent_anomalies,
        add_anomaly_pattern,
    ]
