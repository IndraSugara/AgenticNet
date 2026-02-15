"""
Alert Manager

Alert handling and notification system:
- Multiple alert channels (dashboard, webhook, email)
- Alert severity levels
- Alert history
- Alert acknowledgment
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import asyncio
import json
import os

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """Alert notification channels"""
    DASHBOARD = "dashboard"
    WEBHOOK = "webhook"
    EMAIL = "email"
    DISCORD = "discord"
    TELEGRAM = "telegram"


@dataclass
class Alert:
    """Alert record"""
    id: str
    device_id: str
    device_name: str
    device_ip: str
    severity: AlertSeverity
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_ip": self.device_ip,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at,
            "acknowledged_by": self.acknowledged_by,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at
        }


class AlertManager:
    """
    Manages alerts and notifications
    
    Features:
    - Alert creation and storage
    - Multiple notification channels
    - Alert acknowledgment
    - Alert history
    """
    
    def __init__(self):
        self.alerts: List[Alert] = []
        self._alert_counter = 0
        self._webhook_url: Optional[str] = None
        self._email_config: Dict[str, str] = {}
        self._dashboard_callback: Optional[Callable] = None
        self._discord_webhook: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")
        self._telegram_bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
        self._telegram_chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
        self._channels: List[AlertChannel] = [AlertChannel.DASHBOARD]
    
    def _generate_id(self) -> str:
        """Generate unique alert ID"""
        self._alert_counter += 1
        return f"alert_{self._alert_counter:06d}"
    
    def configure_webhook(self, url: str):
        """Configure webhook URL for alerts"""
        self._webhook_url = url
        if AlertChannel.WEBHOOK not in self._channels:
            self._channels.append(AlertChannel.WEBHOOK)
    
    def configure_email(self, smtp_host: str, smtp_port: int, 
                       username: str, password: str, recipients: List[str]):
        """Configure email for alerts"""
        self._email_config = {
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "username": username,
            "password": password,
            "recipients": recipients
        }
        if AlertChannel.EMAIL not in self._channels:
            self._channels.append(AlertChannel.EMAIL)
    
    def set_dashboard_callback(self, callback: Callable):
        """Set callback for dashboard notifications"""
        self._dashboard_callback = callback
    
    async def create_alert(
        self,
        device_id: str,
        device_name: str,
        device_ip: str,
        severity: str,
        message: str
    ) -> Alert:
        """
        Create a new alert and send notifications
        
        Args:
            device_id: Device ID
            device_name: Device name
            device_ip: Device IP address
            severity: Alert severity (info, warning, critical)
            message: Alert message
            
        Returns:
            Created Alert object
        """
        # Parse severity
        try:
            sev = AlertSeverity(severity.lower())
        except ValueError:
            sev = AlertSeverity.INFO
        
        alert = Alert(
            id=self._generate_id(),
            device_id=device_id,
            device_name=device_name,
            device_ip=device_ip,
            severity=sev,
            message=message
        )
        
        self.alerts.append(alert)
        
        # Keep only last 500 alerts
        if len(self.alerts) > 500:
            self.alerts = self.alerts[-500:]
        
        # Send notifications
        await self._send_notifications(alert)
        
        return alert
    
    async def _send_notifications(self, alert: Alert):
        """Send alert to all configured channels"""
        tasks = []
        
        for channel in self._channels:
            if channel == AlertChannel.DASHBOARD:
                tasks.append(self._send_dashboard(alert))
            elif channel == AlertChannel.WEBHOOK:
                tasks.append(self._send_webhook(alert))
            elif channel == AlertChannel.EMAIL:
                tasks.append(self._send_email(alert))
            elif channel == AlertChannel.DISCORD:
                tasks.append(self._send_discord(alert))
            elif channel == AlertChannel.TELEGRAM:
                tasks.append(self._send_telegram(alert))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_dashboard(self, alert: Alert):
        """Send alert to dashboard"""
        if self._dashboard_callback:
            try:
                if asyncio.iscoroutinefunction(self._dashboard_callback):
                    await self._dashboard_callback(alert)
                else:
                    self._dashboard_callback(alert)
            except Exception as e:
                print(f"Dashboard callback error: {e}")
    
    async def _send_webhook(self, alert: Alert):
        """Send alert to webhook"""
        if not self._webhook_url or not AIOHTTP_AVAILABLE:
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": f"🚨 [{alert.severity.value.upper()}] {alert.message}",
                    "alert": alert.to_dict()
                }
                await session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                )
        except Exception as e:
            print(f"Webhook error: {e}")
    
    async def _send_email(self, alert: Alert):
        """Send alert via email"""
        # Email implementation would go here
        # Skipping actual email sending for now
        pass
    
    def acknowledge(self, alert_id: str, by: str = "system") -> bool:
        """Acknowledge an alert"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_at = datetime.now().isoformat()
                alert.acknowledged_by = by
                return True
        return False
    
    def resolve(self, alert_id: str) -> bool:
        """Mark alert as resolved"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now().isoformat()
                return True
        return False
    
    def resolve_by_device(self, device_id: str):
        """Resolve all alerts for a device"""
        now = datetime.now().isoformat()
        for alert in self.alerts:
            if alert.device_id == device_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = now
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all unresolved alerts"""
        return [a for a in self.alerts if not a.resolved]
    
    def get_alerts(
        self, 
        severity: str = None,
        device_id: str = None,
        unresolved_only: bool = False,
        limit: int = 50
    ) -> List[Alert]:
        """Get alerts with optional filtering"""
        result = self.alerts.copy()
        
        if severity:
            try:
                sev = AlertSeverity(severity.lower())
                result = [a for a in result if a.severity == sev]
            except ValueError:
                pass
        
        if device_id:
            result = [a for a in result if a.device_id == device_id]
        
        if unresolved_only:
            result = [a for a in result if not a.resolved]
        
        return result[-limit:]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get alert summary"""
        active = [a for a in self.alerts if not a.resolved]
        
        return {
            "total": len(self.alerts),
            "active": len(active),
            "critical": sum(1 for a in active if a.severity == AlertSeverity.CRITICAL),
            "warning": sum(1 for a in active if a.severity == AlertSeverity.WARNING),
            "info": sum(1 for a in active if a.severity == AlertSeverity.INFO),
            "acknowledged": sum(1 for a in active if a.acknowledged),
            "channels": [c.value for c in self._channels]
        }
    
    def clear_resolved(self):
        """Clear all resolved alerts"""
        self.alerts = [a for a in self.alerts if not a.resolved]
    
    async def _send_discord(self, alert: Alert):
        """Send alert to Discord webhook"""
        if not self._discord_webhook or not AIOHTTP_AVAILABLE:
            return
        
        colors = {
            AlertSeverity.INFO: 0x3498db,     # Blue
            AlertSeverity.WARNING: 0xf39c12,  # Orange
            AlertSeverity.CRITICAL: 0xe74c3c  # Red
        }
        
        emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨"
        }
        
        payload = {
            "embeds": [{
                "title": f"{emoji[alert.severity]} {alert.severity.value.upper()} Alert",
                "description": alert.message,
                "color": colors[alert.severity],
                "fields": [
                    {"name": "Device", "value": alert.device_name, "inline": True},
                    {"name": "IP", "value": alert.device_ip, "inline": True},
                    {"name": "Time", "value": alert.timestamp[:19], "inline": True}
                ],
                "footer": {"text": f"Alert ID: {alert.id}"}
            }]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._discord_webhook,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 204:
                        print(f"Discord webhook failed: {response.status}")
        except Exception as e:
            print(f"Discord notification error: {e}")
    
    async def _send_telegram(self, alert: Alert):
        """Send alert to Telegram"""
        if not self._telegram_bot_token or not self._telegram_chat_id or not AIOHTTP_AVAILABLE:
            return
        
        emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨"
        }
        
        text = f"""
{emoji[alert.severity]} *{alert.severity.value.upper()} Alert*

*Device:* {alert.device_name}
*IP:* {alert.device_ip}
*Message:* {alert.message}
*Time:* {alert.timestamp[:19]}
*ID:* `{alert.id}`
"""
        
        url = f"https://api.telegram.org/bot{self._telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self._telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        print(f"Telegram failed: {response.status}")
        except Exception as e:
            print(f"Telegram notification error: {e}")
    
    def configure_discord(self, webhook_url: str):
        """Configure Discord webhook"""
        self._discord_webhook = webhook_url
        if AlertChannel.DISCORD not in self._channels:
            self._channels.append(AlertChannel.DISCORD)
    
    def configure_telegram(self, bot_token: str, chat_id: str):
        """Configure Telegram bot"""
        self._telegram_bot_token = bot_token
        self._telegram_chat_id = chat_id
        if AlertChannel.TELEGRAM not in self._channels:
            self._channels.append(AlertChannel.TELEGRAM)


# Singleton instance
alert_manager = AlertManager()


# Convenience function for scheduler integration
async def handle_device_alert(device, severity: str, message: str):
    """Handle alert from scheduler"""
    await alert_manager.create_alert(
        device_id=device.id,
        device_name=device.name,
        device_ip=device.ip,
        severity=severity,
        message=message
    )
