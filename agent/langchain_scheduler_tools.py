"""
LangChain Scheduler Tools

Tools for managing scheduled tasks and alerts via the agent.
"""
from typing import Optional
from langchain_core.tools import tool

from agent.scheduler import scheduler
from agent.alerts import alert_manager


@tool
def create_scheduled_task(
    name: str,
    interval_minutes: int,
    task_type: str = "health_check",
    target_host: str = None
) -> str:
    """
    Create a scheduled monitoring task.
    
    Args:
        name: Name for the task (e.g., "Check Router")
        interval_minutes: How often to run (in minutes)
        task_type: Type of check - health_check, ping, port_scan, or bandwidth_check
        target_host: Target host/IP for ping or port_scan (optional)
    
    Returns:
        Task creation result
    """
    try:
        # Note: The existing scheduler uses per-device monitoring
        # For custom tasks, we'll use the interval format
        schedule = f"{interval_minutes}m"
        
        # For now, provide guidance since scheduler uses device-based monitoring
        if task_type == "health_check":
            return f"""✅ Scheduled task guidance:

**Health Check Monitoring:**
The system automatically monitors all registered devices.
- Use `start monitoring` to begin scheduled health checks
- Each device has its own check interval (default: 60 seconds)

To enable monitoring:
1. Register devices first using `add device`
2. Start the monitoring scheduler

Current monitoring status: {"Running" if scheduler.is_running else "Stopped"}
Registered devices: {len(list(scheduler._check_results.keys()))} with results"""
        
        elif task_type == "ping":
            host = target_host or "8.8.8.8"
            return f"""✅ To schedule ping checks:

1. Register the host as a device:
   `add device {host} with IP {host}`

2. Start monitoring:
   `start monitoring`

The system will automatically ping all registered devices based on their check interval."""
        
        else:
            return f"""✅ Task type '{task_type}' noted.

Use the infrastructure monitoring system:
1. Add devices to monitor
2. Start the scheduler
3. View results with `check status` or `list devices`"""
            
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def start_monitoring() -> str:
    """
    Start the automated monitoring scheduler.
    This will begin health checks on all registered devices.
    
    Returns:
        Status message
    """
    import asyncio
    try:
        if scheduler.is_running:
            return "ℹ️ Monitoring is already running."
        
        # Start the scheduler
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(scheduler.start())
        else:
            asyncio.run(scheduler.start())
        
        return """✅ Monitoring scheduler started!

**Active Features:**
- Automatic health checks for all registered devices
- Status change detection (Online/Offline/Degraded)
- Alert generation for failures

Check status with `get monitoring status`"""
    except Exception as e:
        return f"❌ Failed to start monitoring: {str(e)}"


@tool
def stop_monitoring() -> str:
    """
    Stop the automated monitoring scheduler.
    
    Returns:
        Status message
    """
    import asyncio
    try:
        if not scheduler.is_running:
            return "ℹ️ Monitoring is not running."
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(scheduler.stop())
        else:
            asyncio.run(scheduler.stop())
        
        return "⏹️ Monitoring scheduler stopped."
    except Exception as e:
        return f"❌ Failed to stop monitoring: {str(e)}"


@tool
def get_monitoring_status() -> str:
    """
    Get the current status of the monitoring scheduler.
    
    Returns:
        Monitoring status and recent results
    """
    try:
        results = scheduler.get_all_results()
        
        status_text = "🟢 Running" if scheduler.is_running else "🔴 Stopped"
        
        output = f"""## Monitoring Status: {status_text}

### Recent Check Results:
"""
        if not results:
            output += "No check results yet. Add devices and start monitoring.\n"
        else:
            for device_id, result in results.items():
                status_emoji = "✅" if result.ping_ok else "❌"
                output += f"- {status_emoji} Device {device_id}: {result.status.value}"
                if result.ping_ok:
                    output += f" (latency: {result.ping_latency_ms:.1f}ms)"
                output += "\n"
        
        return output
    except Exception as e:
        return f"❌ Error getting status: {str(e)}"


@tool
def get_alerts(limit: int = 10, severity: str = None) -> str:
    """
    Get recent alerts from the monitoring system.
    
    Args:
        limit: Maximum number of alerts to return (default: 10)
        severity: Filter by severity (info, warning, critical) - optional
    
    Returns:
        List of alerts
    """
    try:
        alerts = alert_manager.get_alerts(severity=severity, limit=limit)
        
        if not alerts:
            return "✅ No alerts found. System is healthy!"
        
        output = f"## Recent Alerts ({len(alerts)})\n\n"
        
        for alert in reversed(alerts):
            emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(
                alert.severity.value, "📢"
            )
            ack = "✓" if alert.acknowledged else ""
            output += f"- {emoji} **{alert.severity.value.upper()}** {ack}\n"
            output += f"  Source: {alert.source}\n"
            output += f"  Message: {alert.message}\n"
            output += f"  Time: {alert.timestamp[:19]}\n\n"
        
        summary = alert_manager.get_summary()
        output += f"\n**Summary:** {summary['unacknowledged']} unacknowledged alerts"
        
        return output
    except Exception as e:
        return f"❌ Error getting alerts: {str(e)}"


@tool
def acknowledge_alert(alert_id: str) -> str:
    """
    Acknowledge an alert to mark it as reviewed.
    
    Args:
        alert_id: The alert ID to acknowledge
    
    Returns:
        Acknowledgment result
    """
    try:
        if alert_manager.acknowledge(alert_id):
            return f"✅ Alert {alert_id} acknowledged."
        else:
            return f"❌ Alert {alert_id} not found."
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def configure_discord_alerts(webhook_url: str) -> str:
    """
    Configure Discord webhook for alert notifications.
    
    Args:
        webhook_url: Discord webhook URL
    
    Returns:
        Configuration result
    """
    try:
        alert_manager.configure_discord(webhook_url)
        return "✅ Discord webhook configured. Alerts will be sent to Discord."
    except Exception as e:
        return f"❌ Error configuring Discord: {str(e)}"


@tool
def configure_telegram_alerts(bot_token: str, chat_id: str) -> str:
    """
    Configure Telegram bot for alert notifications.
    
    Args:
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
    
    Returns:
        Configuration result
    """
    try:
        alert_manager.configure_telegram(bot_token, chat_id)
        return "✅ Telegram bot configured. Alerts will be sent to Telegram."
    except Exception as e:
        return f"❌ Error configuring Telegram: {str(e)}"


@tool
def create_test_alert(severity: str = "info", message: str = "Test alert") -> str:
    """
    Create a test alert to verify notification setup.
    
    Args:
        severity: Alert severity (info, warning, critical)
        message: Alert message
    
    Returns:
        Test result
    """
    import asyncio
    try:
        async def _create():
            return await alert_manager.create_alert(
                severity=severity,
                source="Test",
                message=message,
                notify=True
            )
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.ensure_future(_create())
            # Can't await in sync context, but task is scheduled
            return f"✅ Test alert created with severity '{severity}'.\nCheck your configured notification channels."
        else:
            alert = asyncio.run(_create())
            return f"✅ Test alert created: {alert.id}\nSeverity: {severity}\nMessage: {message}"
    except Exception as e:
        return f"❌ Error creating test alert: {str(e)}"


def get_scheduler_tools() -> list:
    """Get all scheduler-related tools"""
    return [
        create_scheduled_task,
        start_monitoring,
        stop_monitoring,
        get_monitoring_status,
        get_alerts,
        acknowledge_alert,
        configure_discord_alerts,
        configure_telegram_alerts,
        create_test_alert,
    ]
