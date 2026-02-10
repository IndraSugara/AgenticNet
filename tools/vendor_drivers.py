"""
Multi-Vendor Network Drivers

Abstraction layer for heterogeneous network device communication:
- Netmiko-based SSH connections
- Vendor-specific command translation
- Connection pooling and management
- Async execution support
"""
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from enum import Enum
import time

try:
    from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
    NETMIKO_AVAILABLE = True
except ImportError:
    NETMIKO_AVAILABLE = False
    print("⚠️ Netmiko not installed. Device connections disabled.")

from modules.inventory import inventory, DeviceInfo, VendorType, DeviceCredentials


@dataclass
class CommandResult:
    """Result from device command execution"""
    success: bool
    output: str
    error: str = ""
    execution_time: float = 0.0
    device_name: str = ""
    command: str = ""
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time": self.execution_time,
            "device_name": self.device_name,
            "command": self.command
        }


class UnifiedCommand(Enum):
    """Unified commands that work across vendors"""
    GET_HOSTNAME = "get_hostname"
    GET_VERSION = "get_version"
    GET_INTERFACES = "get_interfaces"
    GET_INTERFACE_STATUS = "get_interface_status"
    GET_INTERFACE_TRAFFIC = "get_interface_traffic"
    GET_CPU_LOAD = "get_cpu_load"
    GET_MEMORY_USAGE = "get_memory_usage"
    GET_ROUTING_TABLE = "get_routing_table"
    GET_ARP_TABLE = "get_arp_table"
    GET_MAC_TABLE = "get_mac_table"
    GET_RUNNING_CONFIG = "get_running_config"
    GET_LOGS = "get_logs"
    PING = "ping"
    TRACEROUTE = "traceroute"
    
    # Write operations (high risk)
    SHUTDOWN_INTERFACE = "shutdown_interface"
    NO_SHUTDOWN_INTERFACE = "no_shutdown_interface"
    SET_VLAN = "set_vlan"


class CommandTranslator:
    """
    Translates unified commands to vendor-specific syntax
    """
    
    # Command translation mappings per vendor
    TRANSLATIONS: Dict[VendorType, Dict[UnifiedCommand, str]] = {
        VendorType.CISCO_IOS: {
            UnifiedCommand.GET_HOSTNAME: "show running-config | include hostname",
            UnifiedCommand.GET_VERSION: "show version",
            UnifiedCommand.GET_INTERFACES: "show ip interface brief",
            UnifiedCommand.GET_INTERFACE_STATUS: "show interface status",
            UnifiedCommand.GET_INTERFACE_TRAFFIC: "show interface {interface}",
            UnifiedCommand.GET_CPU_LOAD: "show processes cpu",
            UnifiedCommand.GET_MEMORY_USAGE: "show memory statistics",
            UnifiedCommand.GET_ROUTING_TABLE: "show ip route",
            UnifiedCommand.GET_ARP_TABLE: "show ip arp",
            UnifiedCommand.GET_MAC_TABLE: "show mac address-table",
            UnifiedCommand.GET_RUNNING_CONFIG: "show running-config",
            UnifiedCommand.GET_LOGS: "show logging | tail 50",
            UnifiedCommand.PING: "ping {target} repeat 5",
            UnifiedCommand.TRACEROUTE: "traceroute {target}",
            UnifiedCommand.SHUTDOWN_INTERFACE: "interface {interface}\nshutdown",
            UnifiedCommand.NO_SHUTDOWN_INTERFACE: "interface {interface}\nno shutdown",
            UnifiedCommand.SET_VLAN: "interface {interface}\nswitchport access vlan {vlan}",
        },
        VendorType.CISCO_NXOS: {
            UnifiedCommand.GET_HOSTNAME: "show hostname",
            UnifiedCommand.GET_VERSION: "show version",
            UnifiedCommand.GET_INTERFACES: "show ip interface brief",
            UnifiedCommand.GET_INTERFACE_STATUS: "show interface status",
            UnifiedCommand.GET_INTERFACE_TRAFFIC: "show interface {interface}",
            UnifiedCommand.GET_CPU_LOAD: "show system resources",
            UnifiedCommand.GET_MEMORY_USAGE: "show system resources",
            UnifiedCommand.GET_ROUTING_TABLE: "show ip route",
            UnifiedCommand.GET_ARP_TABLE: "show ip arp",
            UnifiedCommand.GET_MAC_TABLE: "show mac address-table",
            UnifiedCommand.GET_RUNNING_CONFIG: "show running-config",
            UnifiedCommand.GET_LOGS: "show logging last 50",
            UnifiedCommand.PING: "ping {target} count 5",
            UnifiedCommand.TRACEROUTE: "traceroute {target}",
        },
        VendorType.MIKROTIK: {
            UnifiedCommand.GET_HOSTNAME: "/system identity print",
            UnifiedCommand.GET_VERSION: "/system resource print",
            UnifiedCommand.GET_INTERFACES: "/interface print",
            UnifiedCommand.GET_INTERFACE_STATUS: "/interface print stats",
            UnifiedCommand.GET_INTERFACE_TRAFFIC: "/interface monitor-traffic {interface} once",
            UnifiedCommand.GET_CPU_LOAD: "/system resource print",
            UnifiedCommand.GET_MEMORY_USAGE: "/system resource print",
            UnifiedCommand.GET_ROUTING_TABLE: "/ip route print",
            UnifiedCommand.GET_ARP_TABLE: "/ip arp print",
            UnifiedCommand.GET_MAC_TABLE: "/interface bridge host print",
            UnifiedCommand.GET_RUNNING_CONFIG: "/export",
            UnifiedCommand.GET_LOGS: "/log print last=50",
            UnifiedCommand.PING: "/ping {target} count=5",
            UnifiedCommand.TRACEROUTE: "/tool traceroute {target}",
            UnifiedCommand.SHUTDOWN_INTERFACE: "/interface disable {interface}",
            UnifiedCommand.NO_SHUTDOWN_INTERFACE: "/interface enable {interface}",
            UnifiedCommand.SET_VLAN: "/interface vlan add interface={interface} vlan-id={vlan}",
        },
        VendorType.UBIQUITI_EDGE: {
            UnifiedCommand.GET_HOSTNAME: "show host name",
            UnifiedCommand.GET_VERSION: "show version",
            UnifiedCommand.GET_INTERFACES: "show interfaces",
            UnifiedCommand.GET_INTERFACE_STATUS: "show interfaces",
            UnifiedCommand.GET_INTERFACE_TRAFFIC: "show interfaces {interface}",
            UnifiedCommand.GET_CPU_LOAD: "show system cpu",
            UnifiedCommand.GET_MEMORY_USAGE: "show system memory",
            UnifiedCommand.GET_ROUTING_TABLE: "show ip route",
            UnifiedCommand.GET_ARP_TABLE: "show arp",
            UnifiedCommand.GET_MAC_TABLE: "show bridge macs",
            UnifiedCommand.GET_RUNNING_CONFIG: "show configuration",
            UnifiedCommand.GET_LOGS: "show log tail 50",
            UnifiedCommand.PING: "ping {target} count 5",
            UnifiedCommand.TRACEROUTE: "traceroute {target}",
        },
        VendorType.LINUX: {
            UnifiedCommand.GET_HOSTNAME: "hostname",
            UnifiedCommand.GET_VERSION: "uname -a && cat /etc/os-release",
            UnifiedCommand.GET_INTERFACES: "ip -br addr show",
            UnifiedCommand.GET_INTERFACE_STATUS: "ip link show",
            UnifiedCommand.GET_INTERFACE_TRAFFIC: "ip -s link show {interface}",
            UnifiedCommand.GET_CPU_LOAD: "top -bn1 | head -5",
            UnifiedCommand.GET_MEMORY_USAGE: "free -h",
            UnifiedCommand.GET_ROUTING_TABLE: "ip route show",
            UnifiedCommand.GET_ARP_TABLE: "ip neigh show",
            UnifiedCommand.GET_MAC_TABLE: "bridge fdb show",
            UnifiedCommand.GET_RUNNING_CONFIG: "ip addr; ip route",
            UnifiedCommand.GET_LOGS: "journalctl --no-pager -n 50",
            UnifiedCommand.PING: "ping -c 5 {target}",
            UnifiedCommand.TRACEROUTE: "traceroute {target}",
        },
    }
    
    @classmethod
    def translate(
        cls, 
        unified_cmd: UnifiedCommand, 
        vendor: VendorType,
        params: Dict[str, str] = None
    ) -> str:
        """
        Translate unified command to vendor-specific syntax
        
        Args:
            unified_cmd: Unified command enum
            vendor: Target vendor type
            params: Parameters to substitute (e.g., interface, target)
            
        Returns:
            Vendor-specific command string
        """
        params = params or {}
        
        # Get vendor translations, fallback to Linux
        vendor_cmds = cls.TRANSLATIONS.get(vendor, cls.TRANSLATIONS[VendorType.LINUX])
        
        # Get specific command
        cmd_template = vendor_cmds.get(unified_cmd, "")
        
        if not cmd_template:
            return ""
        
        # Substitute parameters
        return cmd_template.format(**params)
    
    @classmethod
    def is_write_operation(cls, unified_cmd: UnifiedCommand) -> bool:
        """Check if command modifies device configuration"""
        write_commands = {
            UnifiedCommand.SHUTDOWN_INTERFACE,
            UnifiedCommand.NO_SHUTDOWN_INTERFACE,
            UnifiedCommand.SET_VLAN,
        }
        return unified_cmd in write_commands


class DeviceConnection:
    """
    Manages SSH connection to a single device
    """
    
    def __init__(self, device: DeviceInfo):
        self.device = device
        self.connection = None
        self.connected = False
        self.last_activity = 0
    
    def connect(self) -> bool:
        """Establish SSH connection"""
        if not NETMIKO_AVAILABLE:
            return False
        
        try:
            params = inventory.get_connection_params(self.device)
            self.connection = ConnectHandler(**params)
            self.connected = True
            self.last_activity = time.time()
            return True
        except NetmikoAuthenticationException as e:
            print(f"❌ Authentication failed for {self.device.name}: {e}")
            return False
        except NetmikoTimeoutException as e:
            print(f"❌ Connection timeout for {self.device.name}: {e}")
            return False
        except Exception as e:
            print(f"❌ Connection error for {self.device.name}: {e}")
            return False
    
    def disconnect(self):
        """Close SSH connection"""
        if self.connection:
            try:
                self.connection.disconnect()
            except:
                pass
        self.connected = False
        self.connection = None
    
    def execute(self, command: str, use_textfsm: bool = False) -> CommandResult:
        """
        Execute a command on the device
        
        Args:
            command: Raw command to execute
            use_textfsm: Parse output with TextFSM
            
        Returns:
            CommandResult with output or error
        """
        if not self.connected or not self.connection:
            return CommandResult(
                success=False,
                output="",
                error="Not connected to device",
                device_name=self.device.name,
                command=command
            )
        
        start_time = time.time()
        
        try:
            output = self.connection.send_command(
                command,
                use_textfsm=use_textfsm,
                read_timeout=60
            )
            
            self.last_activity = time.time()
            
            return CommandResult(
                success=True,
                output=output if isinstance(output, str) else str(output),
                execution_time=time.time() - start_time,
                device_name=self.device.name,
                command=command
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                execution_time=time.time() - start_time,
                device_name=self.device.name,
                command=command
            )
    
    def execute_config(self, commands: List[str]) -> CommandResult:
        """
        Execute configuration commands (enters config mode)
        
        Args:
            commands: List of config commands
            
        Returns:
            CommandResult
        """
        if not self.connected or not self.connection:
            return CommandResult(
                success=False,
                output="",
                error="Not connected to device",
                device_name=self.device.name,
                command="; ".join(commands)
            )
        
        start_time = time.time()
        
        try:
            output = self.connection.send_config_set(commands)
            self.last_activity = time.time()
            
            return CommandResult(
                success=True,
                output=output,
                execution_time=time.time() - start_time,
                device_name=self.device.name,
                command="; ".join(commands)
            )
        except Exception as e:
            return CommandResult(
                success=False,
                output="",
                error=str(e),
                execution_time=time.time() - start_time,
                device_name=self.device.name,
                command="; ".join(commands)
            )


class ConnectionManager:
    """
    Manages connections to multiple devices with pooling
    """
    
    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self._pool: Dict[str, DeviceConnection] = {}
        self._lock = asyncio.Lock()
    
    async def get_connection(self, device: DeviceInfo) -> Optional[DeviceConnection]:
        """
        Get or create a connection to a device
        
        Args:
            device: Target device
            
        Returns:
            DeviceConnection if successful
        """
        async with self._lock:
            key = device.ip_address
            
            # Return existing connection if available
            if key in self._pool and self._pool[key].connected:
                return self._pool[key]
            
            # Check pool size
            if len(self._pool) >= self.max_connections:
                # Remove oldest idle connection
                self._cleanup_idle()
            
            # Create new connection
            conn = DeviceConnection(device)
            
            # Connect in thread pool to avoid blocking
            success = await asyncio.to_thread(conn.connect)
            
            if success:
                self._pool[key] = conn
                return conn
            
            return None
    
    def _cleanup_idle(self, max_idle: float = 300):
        """Remove connections idle for more than max_idle seconds"""
        now = time.time()
        to_remove = []
        
        for key, conn in self._pool.items():
            if now - conn.last_activity > max_idle:
                conn.disconnect()
                to_remove.append(key)
        
        for key in to_remove:
            del self._pool[key]
    
    async def execute_on_device(
        self, 
        device_ip: str, 
        unified_cmd: UnifiedCommand,
        params: Dict[str, str] = None
    ) -> CommandResult:
        """
        Execute a unified command on a device
        
        Args:
            device_ip: Device IP address
            unified_cmd: Unified command to execute
            params: Command parameters
            
        Returns:
            CommandResult
        """
        # Get device from inventory
        device = inventory.get_device(device_ip)
        if not device:
            return CommandResult(
                success=False,
                output="",
                error=f"Device {device_ip} not found in inventory",
                device_name=device_ip,
                command=unified_cmd.value
            )
        
        # Translate command
        raw_cmd = CommandTranslator.translate(unified_cmd, device.vendor, params)
        if not raw_cmd:
            return CommandResult(
                success=False,
                output="",
                error=f"Command {unified_cmd.value} not supported for {device.vendor.value}",
                device_name=device.name,
                command=unified_cmd.value
            )
        
        # Get connection
        conn = await self.get_connection(device)
        if not conn:
            return CommandResult(
                success=False,
                output="",
                error=f"Failed to connect to {device.name}",
                device_name=device.name,
                command=raw_cmd
            )
        
        # Execute command
        if CommandTranslator.is_write_operation(unified_cmd):
            # Config commands need special handling
            commands = raw_cmd.split('\n')
            return await asyncio.to_thread(conn.execute_config, commands)
        else:
            return await asyncio.to_thread(conn.execute, raw_cmd)
    
    async def execute_raw(
        self, 
        device_ip: str, 
        raw_command: str
    ) -> CommandResult:
        """
        Execute a raw command on a device (no translation)
        
        Args:
            device_ip: Device IP address
            raw_command: Raw command to execute
            
        Returns:
            CommandResult
        """
        device = inventory.get_device(device_ip)
        if not device:
            return CommandResult(
                success=False,
                output="",
                error=f"Device {device_ip} not found in inventory",
                device_name=device_ip,
                command=raw_command
            )
        
        conn = await self.get_connection(device)
        if not conn:
            return CommandResult(
                success=False,
                output="",
                error=f"Failed to connect to {device.name}",
                device_name=device.name,
                command=raw_command
            )
        
        return await asyncio.to_thread(conn.execute, raw_command)
    
    def close_all(self):
        """Close all connections"""
        for conn in self._pool.values():
            conn.disconnect()
        self._pool.clear()


# Singleton connection manager
connection_manager = ConnectionManager()
