"""
Infrastructure Manager

Device registry and management for office network infrastructure:
- Device registration (router, switch, server, PC, printer)
- Device status tracking
- Health check configuration
- Uptime history
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
from enum import Enum
import json
import asyncio


class DeviceType(Enum):
    """Types of network devices"""
    ROUTER = "router"
    SWITCH = "switch"
    SERVER = "server"
    PC = "pc"
    PRINTER = "printer"
    ACCESS_POINT = "access_point"
    FIREWALL = "firewall"
    OTHER = "other"


class DeviceStatus(Enum):
    """Device health status"""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a device health check"""
    device_id: str
    timestamp: str
    ping_ok: bool
    ping_latency_ms: float
    ports_checked: List[int]
    ports_open: List[int]
    ports_closed: List[int]
    status: DeviceStatus
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "ping_ok": self.ping_ok,
            "ping_latency_ms": self.ping_latency_ms,
            "ports_checked": self.ports_checked,
            "ports_open": self.ports_open,
            "ports_closed": self.ports_closed,
            "status": self.status.value,
            "error": self.error
        }


@dataclass
class NetworkDevice:
    """Network device configuration"""
    id: str
    name: str
    ip: str
    type: DeviceType
    description: str = ""
    location: str = ""
    ports_to_monitor: List[int] = field(default_factory=list)
    check_interval_seconds: int = 60
    enabled: bool = True
    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_check: Optional[str] = None
    last_online: Optional[str] = None
    uptime_percent: float = 100.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Health history
    health_history: List[HealthCheckResult] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "type": self.type.value,
            "description": self.description,
            "location": self.location,
            "ports_to_monitor": self.ports_to_monitor,
            "check_interval_seconds": self.check_interval_seconds,
            "enabled": self.enabled,
            "status": self.status.value,
            "last_check": self.last_check,
            "last_online": self.last_online,
            "uptime_percent": round(self.uptime_percent, 2),
            "created_at": self.created_at
        }
    
    def update_status(self, result: HealthCheckResult):
        """Update device status from health check result"""
        self.status = result.status
        self.last_check = result.timestamp
        
        if result.status == DeviceStatus.ONLINE:
            self.last_online = result.timestamp
        
        # Add to history (keep last 100)
        self.health_history.append(result)
        if len(self.health_history) > 100:
            self.health_history.pop(0)
        
        # Recalculate uptime
        self._calculate_uptime()
    
    def _calculate_uptime(self):
        """Calculate uptime percentage from history"""
        if not self.health_history:
            return
        
        online_count = sum(
            1 for h in self.health_history 
            if h.status == DeviceStatus.ONLINE
        )
        self.uptime_percent = (online_count / len(self.health_history)) * 100


class InfrastructureManager:
    """
    Manages office network infrastructure devices
    
    Features:
    - Device registration and discovery
    - Status tracking
    - Health check configuration
    - Uptime reporting
    """
    
    def __init__(self):
        self.devices: Dict[str, NetworkDevice] = {}
        self._device_counter = 0
        self._status_callbacks: List = []
    
    def _generate_id(self) -> str:
        """Generate unique device ID"""
        self._device_counter += 1
        return f"dev_{self._device_counter:04d}"
    
    def add_device(
        self,
        name: str,
        ip: str,
        device_type: str,
        description: str = "",
        location: str = "",
        ports_to_monitor: List[int] = None,
        check_interval: int = 60
    ) -> NetworkDevice:
        """
        Add a new device to the registry
        
        Args:
            name: Device display name
            ip: IP address
            device_type: Type (router, switch, server, etc.)
            description: Optional description
            location: Physical/logical location
            ports_to_monitor: List of ports to check
            check_interval: Health check interval in seconds
            
        Returns:
            Newly created NetworkDevice
        """
        device_id = self._generate_id()
        
        # Parse device type
        try:
            dev_type = DeviceType(device_type.lower())
        except ValueError:
            dev_type = DeviceType.OTHER
        
        # Default ports based on device type
        if ports_to_monitor is None:
            ports_to_monitor = self._default_ports(dev_type)
        
        device = NetworkDevice(
            id=device_id,
            name=name,
            ip=ip,
            type=dev_type,
            description=description,
            location=location,
            ports_to_monitor=ports_to_monitor,
            check_interval_seconds=check_interval
        )
        
        self.devices[device_id] = device
        return device
    
    def _default_ports(self, device_type: DeviceType) -> List[int]:
        """Get default ports to monitor based on device type"""
        defaults = {
            DeviceType.ROUTER: [22, 23, 80, 443, 161],
            DeviceType.SWITCH: [22, 23, 161],
            DeviceType.SERVER: [22, 80, 443, 3389],
            DeviceType.PC: [3389, 445],
            DeviceType.PRINTER: [9100, 515, 631, 80],
            DeviceType.ACCESS_POINT: [22, 80, 443],
            DeviceType.FIREWALL: [22, 443, 161],
            DeviceType.OTHER: [80, 443]
        }
        return defaults.get(device_type, [80, 443])
    
    def remove_device(self, device_id: str) -> bool:
        """Remove a device from the registry"""
        if device_id in self.devices:
            del self.devices[device_id]
            return True
        return False
    
    def get_device(self, device_id: str) -> Optional[NetworkDevice]:
        """Get device by ID"""
        return self.devices.get(device_id)
    
    def get_device_by_ip(self, ip: str) -> Optional[NetworkDevice]:
        """Get device by IP address"""
        for device in self.devices.values():
            if device.ip == ip:
                return device
        return None
    
    def list_devices(self, device_type: str = None, status: str = None) -> List[NetworkDevice]:
        """List devices with optional filtering"""
        devices = list(self.devices.values())
        
        if device_type:
            try:
                dt = DeviceType(device_type.lower())
                devices = [d for d in devices if d.type == dt]
            except ValueError:
                pass
        
        if status:
            try:
                st = DeviceStatus(status.lower())
                devices = [d for d in devices if d.status == st]
            except ValueError:
                pass
        
        return devices
    
    def update_device(self, device_id: str, **kwargs) -> Optional[NetworkDevice]:
        """Update device properties"""
        device = self.devices.get(device_id)
        if not device:
            return None
        
        for key, value in kwargs.items():
            if hasattr(device, key):
                if key == "type":
                    try:
                        value = DeviceType(value.lower())
                    except ValueError:
                        continue
                setattr(device, key, value)
        
        return device
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get overall infrastructure status summary"""
        devices = list(self.devices.values())
        
        if not devices:
            return {
                "total": 0,
                "online": 0,
                "offline": 0,
                "degraded": 0,
                "unknown": 0,
                "overall_health": "no_devices"
            }
        
        online = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)
        offline = sum(1 for d in devices if d.status == DeviceStatus.OFFLINE)
        degraded = sum(1 for d in devices if d.status == DeviceStatus.DEGRADED)
        unknown = sum(1 for d in devices if d.status == DeviceStatus.UNKNOWN)
        
        # Determine overall health
        if offline > 0:
            overall = "critical"
        elif degraded > 0:
            overall = "warning"
        elif unknown == len(devices):
            overall = "unknown"
        else:
            overall = "healthy"
        
        return {
            "total": len(devices),
            "online": online,
            "offline": offline,
            "degraded": degraded,
            "unknown": unknown,
            "overall_health": overall,
            "by_type": self._count_by_type()
        }
    
    def _count_by_type(self) -> Dict[str, int]:
        """Count devices by type"""
        counts = {}
        for device in self.devices.values():
            type_name = device.type.value
            counts[type_name] = counts.get(type_name, 0) + 1
        return counts
    
    def register_status_callback(self, callback):
        """Register callback for status changes"""
        self._status_callbacks.append(callback)
    
    async def notify_status_change(self, device: NetworkDevice, old_status: DeviceStatus):
        """Notify callbacks of status change"""
        for callback in self._status_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(device, old_status)
                else:
                    callback(device, old_status)
            except Exception:
                pass
    
    def export_config(self) -> str:
        """Export all devices as JSON"""
        return json.dumps({
            "devices": [d.to_dict() for d in self.devices.values()],
            "exported_at": datetime.now().isoformat()
        }, indent=2)
    
    def import_config(self, config_json: str) -> int:
        """Import devices from JSON config"""
        data = json.loads(config_json)
        count = 0
        
        for dev_data in data.get("devices", []):
            self.add_device(
                name=dev_data.get("name", "Unknown"),
                ip=dev_data.get("ip", ""),
                device_type=dev_data.get("type", "other"),
                description=dev_data.get("description", ""),
                location=dev_data.get("location", ""),
                ports_to_monitor=dev_data.get("ports_to_monitor", []),
                check_interval=dev_data.get("check_interval_seconds", 60)
            )
            count += 1
        
        return count


# Singleton instance
infrastructure = InfrastructureManager()
