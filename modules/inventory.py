"""
Device Inventory Module

Source of Truth for network device information with:
- NetBox API integration (when available)
- SQLite fallback for local development
- Credential management from environment variables
- Vendor detection and connection parameter generation
"""
import os
import sqlite3
import asyncio
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime
from pathlib import Path

try:
    import pynetbox
    NETBOX_AVAILABLE = True
except ImportError:
    NETBOX_AVAILABLE = False


class VendorType(Enum):
    """Supported network device vendors"""
    CISCO_IOS = "cisco_ios"
    CISCO_NXOS = "cisco_nxos"
    MIKROTIK = "mikrotik_routeros"
    UBIQUITI_EDGE = "ubiquiti_edgerouter"
    LINUX = "linux"
    UNKNOWN = "unknown"


class DeviceRole(Enum):
    """Device roles in the network"""
    ROUTER = "router"
    SWITCH = "switch"
    FIREWALL = "firewall"
    ACCESS_POINT = "access_point"
    SERVER = "server"
    OTHER = "other"


@dataclass
class DeviceInfo:
    """Network device information"""
    id: str
    name: str
    ip_address: str
    vendor: VendorType
    role: DeviceRole = DeviceRole.OTHER
    model: str = ""
    location: str = ""
    description: str = ""
    ssh_port: int = 22
    credential_id: str = "default"
    enabled: bool = True
    last_seen: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "ip_address": self.ip_address,
            "vendor": self.vendor.value,
            "role": self.role.value,
            "model": self.model,
            "location": self.location,
            "description": self.description,
            "ssh_port": self.ssh_port,
            "credential_id": self.credential_id,
            "enabled": self.enabled,
            "last_seen": self.last_seen
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DeviceInfo":
        return cls(
            id=data["id"],
            name=data["name"],
            ip_address=data["ip_address"],
            vendor=VendorType(data.get("vendor", "unknown")),
            role=DeviceRole(data.get("role", "other")),
            model=data.get("model", ""),
            location=data.get("location", ""),
            description=data.get("description", ""),
            ssh_port=data.get("ssh_port", 22),
            credential_id=data.get("credential_id", "default"),
            enabled=data.get("enabled", True),
            last_seen=data.get("last_seen")
        )


@dataclass
class DeviceCredentials:
    """Device credentials (loaded from environment)"""
    username: str
    password: str
    enable_secret: str = ""
    ssh_key_path: str = ""


class InventoryModule:
    """
    Device Inventory Management
    
    Provides:
    - Device lookup by IP/hostname
    - Vendor detection
    - Connection parameter generation
    - Integration with NetBox or SQLite fallback
    """
    
    # Vendor detection patterns
    VENDOR_PATTERNS = {
        VendorType.CISCO_IOS: ["cisco", "ios"],
        VendorType.CISCO_NXOS: ["nexus", "nxos"],
        VendorType.MIKROTIK: ["mikrotik", "routeros", "routerboard"],
        VendorType.UBIQUITI_EDGE: ["ubiquiti", "edgerouter", "edgemax", "unifi"],
        VendorType.LINUX: ["linux", "ubuntu", "debian", "centos", "rhel"],
    }
    
    # Default SSH ports per vendor
    DEFAULT_PORTS = {
        VendorType.CISCO_IOS: 22,
        VendorType.CISCO_NXOS: 22,
        VendorType.MIKROTIK: 22,
        VendorType.UBIQUITI_EDGE: 22,
        VendorType.LINUX: 22,
        VendorType.UNKNOWN: 22,
    }
    
    def __init__(self, db_path: str = None):
        """Initialize inventory with SQLite or NetBox"""
        self.db_path = db_path or str(Path(__file__).parent.parent / "data" / "inventory.db")
        self.netbox_client = None
        self._cache: Dict[str, DeviceInfo] = {}
        self._credentials_cache: Dict[str, DeviceCredentials] = {}
        
        # Try NetBox first, fallback to SQLite
        if NETBOX_AVAILABLE and os.getenv("NETBOX_URL"):
            self._init_netbox()
        else:
            self._init_sqlite()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection with threading support"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def _init_netbox(self):
        """Initialize NetBox connection"""
        try:
            self.netbox_client = pynetbox.api(
                url=os.getenv("NETBOX_URL"),
                token=os.getenv("NETBOX_TOKEN")
            )
            print("✅ Connected to NetBox for inventory")
        except Exception as e:
            print(f"⚠️ NetBox connection failed: {e}, falling back to SQLite")
            self._init_sqlite()
    
    def _init_sqlite(self):
        """Initialize SQLite database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                ip_address TEXT UNIQUE NOT NULL,
                vendor TEXT DEFAULT 'unknown',
                role TEXT DEFAULT 'other',
                model TEXT DEFAULT '',
                location TEXT DEFAULT '',
                description TEXT DEFAULT '',
                ssh_port INTEGER DEFAULT 22,
                credential_id TEXT DEFAULT 'default',
                enabled INTEGER DEFAULT 1,
                last_seen TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for fast IP lookup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ip_address ON devices(ip_address)
        """)
        
        conn.commit()
        conn.close()
        print(f"✅ SQLite inventory initialized at {self.db_path}")
    
    def detect_vendor(self, device_name: str = "", model: str = "") -> VendorType:
        """Detect vendor from device name or model string"""
        search_text = f"{device_name} {model}".lower()
        
        for vendor, patterns in self.VENDOR_PATTERNS.items():
            if any(pattern in search_text for pattern in patterns):
                return vendor
        
        return VendorType.UNKNOWN
    
    def get_device(self, ip_or_hostname: str) -> Optional[DeviceInfo]:
        """
        Get device info by IP address or hostname
        
        Args:
            ip_or_hostname: IP address or device name
            
        Returns:
            DeviceInfo if found, None otherwise
        """
        # Check cache first
        if ip_or_hostname in self._cache:
            return self._cache[ip_or_hostname]
        
        # Query from backend
        device = None
        if self.netbox_client:
            device = self._get_from_netbox(ip_or_hostname)
        else:
            device = self._get_from_sqlite(ip_or_hostname)
        
        # Update cache
        if device:
            self._cache[ip_or_hostname] = device
            self._cache[device.name] = device
        
        return device
    
    def _get_from_netbox(self, ip_or_hostname: str) -> Optional[DeviceInfo]:
        """Query device from NetBox"""
        try:
            # Try by IP first
            ip_results = self.netbox_client.ipam.ip_addresses.filter(address=ip_or_hostname)
            for ip_obj in ip_results:
                if ip_obj.assigned_object:
                    device = ip_obj.assigned_object.device
                    return self._netbox_to_device(device, ip_or_hostname)
            
            # Try by name
            devices = self.netbox_client.dcim.devices.filter(name=ip_or_hostname)
            for device in devices:
                primary_ip = device.primary_ip4 or device.primary_ip6
                ip_addr = str(primary_ip).split('/')[0] if primary_ip else ""
                return self._netbox_to_device(device, ip_addr)
                
        except Exception as e:
            print(f"⚠️ NetBox query error: {e}")
        
        return None
    
    def _netbox_to_device(self, nb_device, ip_address: str) -> DeviceInfo:
        """Convert NetBox device to DeviceInfo"""
        vendor = self.detect_vendor(
            str(nb_device.device_type.manufacturer) if nb_device.device_type else "",
            str(nb_device.device_type.model) if nb_device.device_type else ""
        )
        
        return DeviceInfo(
            id=str(nb_device.id),
            name=nb_device.name,
            ip_address=ip_address,
            vendor=vendor,
            role=DeviceRole.ROUTER,  # Could map from NetBox role
            model=str(nb_device.device_type.model) if nb_device.device_type else "",
            location=str(nb_device.site) if nb_device.site else "",
            description=nb_device.comments or "",
            ssh_port=self.DEFAULT_PORTS.get(vendor, 22),
            credential_id="default",
            enabled=nb_device.status.value == "active" if nb_device.status else True
        )
    
    def _get_from_sqlite(self, ip_or_hostname: str) -> Optional[DeviceInfo]:
        """Query device from SQLite"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM devices 
            WHERE ip_address = ? OR name = ? OR id = ?
            LIMIT 1
        """, (ip_or_hostname, ip_or_hostname, ip_or_hostname))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return DeviceInfo.from_dict(dict(row))
        return None
    
    def list_devices(
        self, 
        vendor: VendorType = None, 
        role: DeviceRole = None,
        enabled_only: bool = True
    ) -> List[DeviceInfo]:
        """
        List all devices with optional filtering
        
        Args:
            vendor: Filter by vendor type
            role: Filter by device role
            enabled_only: Only return enabled devices
        """
        if self.netbox_client:
            return self._list_from_netbox(vendor, role, enabled_only)
        return self._list_from_sqlite(vendor, role, enabled_only)
    
    def _list_from_sqlite(
        self, 
        vendor: VendorType = None, 
        role: DeviceRole = None,
        enabled_only: bool = True
    ) -> List[DeviceInfo]:
        """List devices from SQLite"""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM devices WHERE 1=1"
        params = []
        
        if enabled_only:
            query += " AND enabled = 1"
        if vendor:
            query += " AND vendor = ?"
            params.append(vendor.value)
        if role:
            query += " AND role = ?"
            params.append(role.value)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [DeviceInfo.from_dict(dict(row)) for row in rows]
    
    def _list_from_netbox(
        self, 
        vendor: VendorType = None, 
        role: DeviceRole = None,
        enabled_only: bool = True
    ) -> List[DeviceInfo]:
        """List devices from NetBox"""
        try:
            filters = {}
            if enabled_only:
                filters["status"] = "active"
            
            devices = self.netbox_client.dcim.devices.filter(**filters)
            results = []
            
            for device in devices:
                primary_ip = device.primary_ip4 or device.primary_ip6
                if not primary_ip:
                    continue
                    
                ip_addr = str(primary_ip).split('/')[0]
                dev_info = self._netbox_to_device(device, ip_addr)
                
                # Apply filters
                if vendor and dev_info.vendor != vendor:
                    continue
                if role and dev_info.role != role:
                    continue
                    
                results.append(dev_info)
            
            return results
        except Exception as e:
            print(f"⚠️ NetBox list error: {e}")
            return []
    
    def add_device(self, device: DeviceInfo) -> bool:
        """Add a new device to inventory"""
        if self.netbox_client:
            # NetBox is read-only for now
            print("⚠️ Adding devices to NetBox not supported yet")
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO devices (id, name, ip_address, vendor, role, model, 
                    location, description, ssh_port, credential_id, enabled, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device.id, device.name, device.ip_address, device.vendor.value,
                device.role.value, device.model, device.location, device.description,
                device.ssh_port, device.credential_id, 1 if device.enabled else 0,
                device.last_seen
            ))
            conn.commit()
            
            # Update cache
            self._cache[device.ip_address] = device
            self._cache[device.name] = device
            
            return True
        except sqlite3.IntegrityError as e:
            print(f"⚠️ Device already exists: {e}")
            return False
        finally:
            conn.close()
    
    def update_device(self, device: DeviceInfo) -> bool:
        """Update existing device in inventory"""
        if self.netbox_client:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE devices SET
                name = ?, vendor = ?, role = ?, model = ?,
                location = ?, description = ?, ssh_port = ?,
                credential_id = ?, enabled = ?, last_seen = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? OR ip_address = ?
        """, (
            device.name, device.vendor.value, device.role.value, device.model,
            device.location, device.description, device.ssh_port,
            device.credential_id, 1 if device.enabled else 0, device.last_seen,
            device.id, device.ip_address
        ))
        
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        # Update cache
        if affected > 0:
            self._cache[device.ip_address] = device
            self._cache[device.name] = device
        
        return affected > 0
    
    def delete_device(self, ip_or_id: str) -> bool:
        """Delete device from inventory"""
        if self.netbox_client:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM devices WHERE id = ? OR ip_address = ?
        """, (ip_or_id, ip_or_id))
        
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        
        # Clear cache
        if ip_or_id in self._cache:
            del self._cache[ip_or_id]
        
        return affected > 0
    
    def get_credentials(self, credential_id: str = "default") -> DeviceCredentials:
        """
        Get credentials from environment variables
        
        Environment variable naming:
        - DEVICE_USERNAME_{credential_id}
        - DEVICE_PASSWORD_{credential_id}
        - DEVICE_ENABLE_{credential_id}
        - DEVICE_SSH_KEY_{credential_id}
        """
        if credential_id in self._credentials_cache:
            return self._credentials_cache[credential_id]
        
        cred_upper = credential_id.upper()
        
        creds = DeviceCredentials(
            username=os.getenv(f"DEVICE_USERNAME_{cred_upper}", 
                             os.getenv("DEVICE_USERNAME", "admin")),
            password=os.getenv(f"DEVICE_PASSWORD_{cred_upper}",
                             os.getenv("DEVICE_PASSWORD", "")),
            enable_secret=os.getenv(f"DEVICE_ENABLE_{cred_upper}",
                                   os.getenv("DEVICE_ENABLE", "")),
            ssh_key_path=os.getenv(f"DEVICE_SSH_KEY_{cred_upper}",
                                  os.getenv("DEVICE_SSH_KEY", ""))
        )
        
        self._credentials_cache[credential_id] = creds
        return creds
    
    def get_connection_params(self, device: DeviceInfo) -> Dict[str, Any]:
        """
        Generate Netmiko connection parameters for a device
        
        Args:
            device: Device information
            
        Returns:
            Dict suitable for netmiko.ConnectHandler()
        """
        creds = self.get_credentials(device.credential_id)
        
        # Map vendor to Netmiko device_type
        device_type_map = {
            VendorType.CISCO_IOS: "cisco_ios",
            VendorType.CISCO_NXOS: "cisco_nxos",
            VendorType.MIKROTIK: "mikrotik_routeros",
            VendorType.UBIQUITI_EDGE: "ubiquiti_edge",
            VendorType.LINUX: "linux",
            VendorType.UNKNOWN: "generic_termserver",
        }
        
        params = {
            "device_type": device_type_map.get(device.vendor, "generic_termserver"),
            "host": device.ip_address,
            "port": device.ssh_port,
            "username": creds.username,
            "password": creds.password,
            "timeout": 30,
            "banner_timeout": 20,
        }
        
        if creds.enable_secret:
            params["secret"] = creds.enable_secret
        
        if creds.ssh_key_path and os.path.exists(creds.ssh_key_path):
            params["use_keys"] = True
            params["key_file"] = creds.ssh_key_path
        
        return params
    
    def format_for_agent(self) -> str:
        """Format inventory summary for agent context"""
        devices = self.list_devices()
        
        if not devices:
            return "📭 Inventory kosong. Belum ada device yang terdaftar."
        
        lines = ["## Device Inventory\n"]
        
        # Group by vendor
        by_vendor: Dict[VendorType, List[DeviceInfo]] = {}
        for d in devices:
            if d.vendor not in by_vendor:
                by_vendor[d.vendor] = []
            by_vendor[d.vendor].append(d)
        
        for vendor, dev_list in by_vendor.items():
            lines.append(f"### {vendor.value.replace('_', ' ').title()} ({len(dev_list)})")
            for d in dev_list[:5]:  # Limit per vendor
                status = "🟢" if d.enabled else "🔴"
                lines.append(f"- {status} **{d.name}** ({d.ip_address}) - {d.role.value}")
            
            if len(dev_list) > 5:
                lines.append(f"  ... dan {len(dev_list) - 5} device lainnya")
        
        return "\n".join(lines)


# Singleton instance
inventory = InventoryModule()
