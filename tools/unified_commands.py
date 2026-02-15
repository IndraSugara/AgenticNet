"""
Unified Commands Interface

Provides vendor-agnostic commands with:
- JSON-normalized output
- TextFSM/ntc-templates parsing
- Fallback regex parsing
"""
import json
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from enum import Enum

try:
    import textfsm
    TEXTFSM_AVAILABLE = True
except ImportError:
    TEXTFSM_AVAILABLE = False

from tools.vendor_drivers import (
    connection_manager, 
    CommandResult, 
    UnifiedCommand, 
    CommandTranslator
)
from modules.inventory import inventory, VendorType


@dataclass
class NormalizedResult:
    """Normalized command result in JSON format"""
    success: bool
    data: Dict[str, Any]
    error: str = ""
    raw_output: str = ""
    device_name: str = ""
    command: str = ""
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "raw_output": self.raw_output,
            "device_name": self.device_name,
            "command": self.command
        }


class OutputParser:
    """
    Parses CLI output to structured JSON
    Uses TextFSM when available, fallback to regex patterns
    """
    
    # Regex patterns for common outputs
    PATTERNS = {
        "cisco_interfaces": {
            "pattern": r"(\S+)\s+(\d+\.\d+\.\d+\.\d+|unassigned)\s+\S+\s+\S+\s+(up|down|administratively down)\s+(up|down)",
            "groups": ["interface", "ip_address", "status", "protocol"]
        },
        "mikrotik_interfaces": {
            "pattern": r"\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(true|false)\s+(true|false)",
            "groups": ["id", "name", "type", "mtu", "actual_mtu", "running", "disabled"]
        },
        "ping_stats": {
            "pattern": r"(\d+) packets transmitted.*?(\d+) (?:packets )?received.*?(\d+(?:\.\d+)?)% (?:packet )?loss",
            "groups": ["sent", "received", "loss_percent"]
        },
        "cpu_percent": {
            "pattern": r"CPU utilization.*?(\d+(?:\.\d+)?)[%\s]",
            "groups": ["cpu_percent"]
        },
        "memory_percent": {
            "pattern": r"(?:memory|Memory).*?(\d+(?:\.\d+)?)[%\s]",
            "groups": ["memory_percent"]
        }
    }
    
    @classmethod
    def parse(cls, output: str, vendor: VendorType, command_type: str) -> Dict[str, Any]:
        """
        Parse CLI output to structured data
        
        Args:
            output: Raw CLI output
            vendor: Device vendor
            command_type: Type of command for pattern selection
            
        Returns:
            Parsed structured data
        """
        if not output:
            return {}
        
        # Try TextFSM first
        if TEXTFSM_AVAILABLE:
            parsed = cls._parse_with_textfsm(output, vendor, command_type)
            if parsed:
                return parsed
        
        # Fallback to regex
        return cls._parse_with_regex(output, command_type)
    
    @classmethod
    def _parse_with_textfsm(cls, output: str, vendor: VendorType, command_type: str) -> Optional[Dict[str, Any]]:
        """Parse using TextFSM templates (ntc-templates)"""
        # This would use ntc-templates in production
        # For now, return None to use regex fallback
        return None
    
    @classmethod
    def _parse_with_regex(cls, output: str, command_type: str) -> Dict[str, Any]:
        """Parse using regex patterns"""
        result = {"raw_lines": output.split('\n')}
        
        # Apply matching patterns
        for pattern_name, pattern_info in cls.PATTERNS.items():
            if pattern_name in command_type or command_type in pattern_name:
                matches = re.findall(pattern_info["pattern"], output, re.IGNORECASE | re.DOTALL)
                if matches:
                    groups = pattern_info["groups"]
                    if len(matches) == 1 and len(groups) == len(matches[0]):
                        # Single match - return as dict
                        result.update(dict(zip(groups, matches[0])))
                    else:
                        # Multiple matches - return as list
                        result["items"] = [
                            dict(zip(groups, m)) if isinstance(m, tuple) else {groups[0]: m}
                            for m in matches
                        ]
        
        return result
    
    @classmethod
    def parse_interfaces(cls, output: str, vendor: VendorType) -> List[Dict[str, Any]]:
        """Parse interface list output"""
        interfaces = []
        
        if vendor == VendorType.CISCO_IOS:
            # Cisco "show ip interface brief" format
            lines = output.strip().split('\n')
            for line in lines[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 4:
                    interfaces.append({
                        "name": parts[0],
                        "ip_address": parts[1] if parts[1] != "unassigned" else None,
                        "status": parts[-2],
                        "protocol": parts[-1]
                    })
        
        elif vendor == VendorType.MIKROTIK:
            # Mikrotik "/interface print" format
            lines = output.strip().split('\n')
            for line in lines:
                match = re.match(r'\s*(\d+)\s+\S*\s+(\S+)\s+(\S+)\s+(\S+)', line)
                if match:
                    interfaces.append({
                        "id": match.group(1),
                        "name": match.group(2),
                        "type": match.group(3),
                        "status": "up" if "R" in line else "down"
                    })
        
        elif vendor == VendorType.LINUX:
            # Linux "ip -br addr show" format
            lines = output.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    interfaces.append({
                        "name": parts[0],
                        "status": parts[1],
                        "ip_address": parts[2] if len(parts) > 2 else None
                    })
        
        return interfaces
    
    @classmethod
    def parse_cpu_memory(cls, output: str, vendor: VendorType) -> Dict[str, Any]:
        """Parse CPU and memory usage"""
        result = {"cpu_percent": None, "memory_percent": None}
        
        if vendor == VendorType.MIKROTIK:
            # Mikrotik format
            cpu_match = re.search(r'cpu-load:\s*(\d+)%?', output, re.IGNORECASE)
            mem_match = re.search(r'free-memory:\s*(\d+(?:\.\d+)?)\s*(\w+)', output, re.IGNORECASE)
            total_match = re.search(r'total-memory:\s*(\d+(?:\.\d+)?)\s*(\w+)', output, re.IGNORECASE)
            
            if cpu_match:
                result["cpu_percent"] = float(cpu_match.group(1))
            
            if mem_match and total_match:
                free = float(mem_match.group(1))
                total = float(total_match.group(1))
                result["memory_percent"] = round((1 - free/total) * 100, 1)
                result["memory_free_mb"] = free
                result["memory_total_mb"] = total
        
        elif vendor in [VendorType.CISCO_IOS, VendorType.CISCO_NXOS]:
            # Cisco format
            cpu_match = re.search(r'CPU utilization.*?(\d+(?:\.\d+)?)\s*%', output, re.IGNORECASE)
            if cpu_match:
                result["cpu_percent"] = float(cpu_match.group(1))
        
        elif vendor == VendorType.LINUX:
            # Linux top/free format
            cpu_match = re.search(r'%Cpu.*?(\d+(?:\.\d+)?)\s*us', output)
            if cpu_match:
                result["cpu_percent"] = float(cpu_match.group(1))
            
            mem_match = re.search(r'Mem:.*?(\d+\.\d+).*?(\d+\.\d+)', output)
            if mem_match:
                result["memory_total_mb"] = float(mem_match.group(1)) * 1024
                result["memory_used_mb"] = float(mem_match.group(2)) * 1024
        
        return result


class UnifiedCommandExecutor:
    """
    Execute unified commands and return normalized results
    """
    
    async def get_interfaces(self, device_ip: str) -> NormalizedResult:
        """Get all interfaces with status"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, UnifiedCommand.GET_INTERFACES
        )
        
        if result.success:
            interfaces = OutputParser.parse_interfaces(result.output, device.vendor)
            return NormalizedResult(
                success=True,
                data={"interfaces": interfaces, "count": len(interfaces)},
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )
    
    async def get_cpu_memory(self, device_ip: str) -> NormalizedResult:
        """Get CPU and memory usage"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, UnifiedCommand.GET_CPU_LOAD
        )
        
        if result.success:
            parsed = OutputParser.parse_cpu_memory(result.output, device.vendor)
            return NormalizedResult(
                success=True,
                data=parsed,
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )
    
    async def get_interface_traffic(self, device_ip: str, interface: str) -> NormalizedResult:
        """Get traffic statistics for an interface"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, 
            UnifiedCommand.GET_INTERFACE_TRAFFIC,
            {"interface": interface}
        )
        
        if result.success:
            # Parse traffic stats
            data = {"interface": interface, "raw_stats": result.output}
            
            # Try to extract common metrics
            in_bytes = re.search(r'(?:input|rx).*?(\d+)\s*(?:bytes|octets)', result.output, re.I)
            out_bytes = re.search(r'(?:output|tx).*?(\d+)\s*(?:bytes|octets)', result.output, re.I)
            
            if in_bytes:
                data["bytes_in"] = int(in_bytes.group(1))
            if out_bytes:
                data["bytes_out"] = int(out_bytes.group(1))
            
            return NormalizedResult(
                success=True,
                data=data,
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )
    
    async def get_routing_table(self, device_ip: str) -> NormalizedResult:
        """Get routing table"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, UnifiedCommand.GET_ROUTING_TABLE
        )
        
        if result.success:
            # Return raw for now, could add route parsing
            return NormalizedResult(
                success=True,
                data={"routes": result.output.split('\n')},
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )
    
    async def get_arp_table(self, device_ip: str) -> NormalizedResult:
        """Get ARP table"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, UnifiedCommand.GET_ARP_TABLE
        )
        
        if result.success:
            return NormalizedResult(
                success=True,
                data={"entries": result.output.split('\n')},
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )
    
    async def ping(self, device_ip: str, target: str) -> NormalizedResult:
        """Ping from device to target"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, 
            UnifiedCommand.PING,
            {"target": target}
        )
        
        if result.success:
            # Parse ping results
            data = {"target": target}
            
            loss = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:packet\s+)?loss', result.output, re.I)
            if loss:
                data["packet_loss_percent"] = float(loss.group(1))
            
            time_match = re.search(r'(?:avg|average).*?(\d+(?:\.\d+)?)\s*ms', result.output, re.I)
            if time_match:
                data["avg_latency_ms"] = float(time_match.group(1))
            
            return NormalizedResult(
                success=True,
                data=data,
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )
    
    async def get_logs(self, device_ip: str) -> NormalizedResult:
        """Get recent device logs"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, UnifiedCommand.GET_LOGS
        )
        
        if result.success:
            return NormalizedResult(
                success=True,
                data={"logs": result.output.split('\n')},
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )


    async def shutdown_interface(self, device_ip: str, interface: str) -> NormalizedResult:
        """Shutdown (disable) an interface on a remote device"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, 
            UnifiedCommand.SHUTDOWN_INTERFACE,
            {"interface": interface}
        )
        
        if result.success:
            return NormalizedResult(
                success=True,
                data={"interface": interface, "action": "shutdown", "status": "disabled"},
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )
    
    async def no_shutdown_interface(self, device_ip: str, interface: str) -> NormalizedResult:
        """Enable (no shutdown) an interface on a remote device"""
        device = inventory.get_device(device_ip)
        if not device:
            return NormalizedResult(
                success=False, data={}, error=f"Device {device_ip} not found"
            )
        
        result = await connection_manager.execute_on_device(
            device_ip, 
            UnifiedCommand.NO_SHUTDOWN_INTERFACE,
            {"interface": interface}
        )
        
        if result.success:
            return NormalizedResult(
                success=True,
                data={"interface": interface, "action": "no shutdown", "status": "enabled"},
                raw_output=result.output,
                device_name=result.device_name,
                command=result.command
            )
        
        return NormalizedResult(
            success=False,
            data={},
            error=result.error,
            device_name=result.device_name,
            command=result.command
        )


# Singleton executor
unified_commands = UnifiedCommandExecutor()
