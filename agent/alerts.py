"""
Alert Manager Module

Handles alert notifications for network monitoring:
- Discord/Telegram webhooks
- Alert history storage
- Alert severity levels
"""
import asyncio
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

import aiohttp


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An alert record"""
    id: str
    timestamp: str
    severity: AlertSeverity
    source: str  # device name or system
    message: str
    acknowledged: bool = False
    ack_time: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "severity": self.severity.value,
            "source": self.source,
            "message": self.message,
            "acknowledged": self.acknowledged,
            "ack_time": self.ack_time,
            "metadata": self.metadata
        }


class AlertManager:
    """
    Manages alerts and notifications
    
    Features:
    - Store alert history
    - Send to Discord/Telegram webhooks
    - Alert acknowledgment
    """
    
    def __init__(self):
        self.alerts: List[Alert] = []
        self._alert_counter = 0
        self._discord_webhook: Optional[str] = os.getenv("DISCORD_WEBHOOK_URL")
        self._telegram_bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
        self._telegram_chat_id: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")
    
    def _generate_id(self) -> str:
        """Generate unique alert ID"""
        self._alert_counter += 1
        return f"alert_{self._alert_counter:06d}"
    
    async def create_alert(
        self,
        severity: str,
        source: str,
        message: str,
        metadata: Dict[str, Any] = None,
        notify: bool = True
    ) -> Alert:
        """
        Create a new alert
        
        Args:
            severity: info, warning, or critical
            source: Source device or system name
            message: Alert message
            metadata: Additional data
            notify: Whether to send notifications
            
        Returns:
            Created Alert
        """
        try:
            sev = AlertSeverity(severity.lower())
        except ValueError:
            sev = AlertSeverity.INFO
        
        alert = Alert(
            id=self._generate_id(),
            timestamp=datetime.now().isoformat(),
            severity=sev,
            source=source,
            message=message,
            metadata=metadata or {}
        )
        
        self.alerts.append(alert)
        
        # Keep only last 500 alerts
        if len(self.alerts) > 500:
            self.alerts = self.alerts[-500:]
        
        # Send notifications
        if notify:
            await self._send_notifications(alert)
        
        return alert
    
    async def _send_notifications(self, alert: Alert):
        """Send notifications to configured channels"""
        tasks = []
        
        if self._discord_webhook:
            tasks.append(self._send_discord(alert))
        
        if self._telegram_bot_token and self._telegram_chat_id:
            tasks.append(self._send_telegram(alert))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_discord(self, alert: Alert):
        """Send alert to Discord webhook"""
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
                    {"name": "Source", "value": alert.source, "inline": True},
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
        emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨"
        }
        
        text = f"""
{emoji[alert.severity]} *{alert.severity.value.upper()} Alert*

*Source:* {alert.source}
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
    
    def acknowledge(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                alert.ack_time = datetime.now().isoformat()
                return True
        return False
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID"""
        for alert in self.alerts:
            if alert.id == alert_id:
                return alert
        return None
    
    def get_alerts(
        self,
        severity: str = None,
        acknowledged: bool = None,
        limit: int = 50
    ) -> List[Alert]:
        """Get alerts with optional filtering"""
        result = self.alerts
        
        if severity:
            try:
                sev = AlertSeverity(severity.lower())
                result = [a for a in result if a.severity == sev]
            except ValueError:
                pass
        
        if acknowledged is not None:
            result = [a for a in result if a.acknowledged == acknowledged]
        
        return result[-limit:]
    
    def get_unacknowledged_count(self) -> int:
        """Get count of unacknowledged alerts"""
        return sum(1 for a in self.alerts if not a.acknowledged)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get alert summary"""
        return {
            "total": len(self.alerts),
            "unacknowledged": self.get_unacknowledged_count(),
            "by_severity": {
                "info": sum(1 for a in self.alerts if a.severity == AlertSeverity.INFO),
                "warning": sum(1 for a in self.alerts if a.severity == AlertSeverity.WARNING),
                "critical": sum(1 for a in self.alerts if a.severity == AlertSeverity.CRITICAL)
            }
        }
    
    def clear_acknowledged(self):
        """Clear all acknowledged alerts"""
        self.alerts = [a for a in self.alerts if not a.acknowledged]
    
    def configure_discord(self, webhook_url: str):
        """Configure Discord webhook"""
        self._discord_webhook = webhook_url
    
    def configure_telegram(self, bot_token: str, chat_id: str):
        """Configure Telegram bot"""
        self._telegram_bot_token = bot_token
        self._telegram_chat_id = chat_id


# Singleton instance
alert_manager = AlertManager()
