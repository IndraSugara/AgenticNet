"""
Network Topology Module

Features:
- Auto-discover devices via ARP/ping sweep
- Build network topology map
- Generate Mermaid diagrams
- Device relationship tracking
"""
import asyncio
import socket
import subprocess
import re
import json
from datetime import datetime
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum


class NodeType(Enum):
    """Network node types"""
    GATEWAY = "gateway"
    ROUTER = "router"
    SWITCH = "switch"
    SERVER = "server"
    WORKSTATION = "workstation"
    UNKNOWN = "unknown"


@dataclass
class NetworkNode:
    """A node in the network topology"""
    id: str
    ip: str
    mac: Optional[str] = None
    hostname: Optional[str] = None
    node_type: NodeType = NodeType.UNKNOWN
    vendor: Optional[str] = None
    ports_open: List[int] = field(default_factory=list)
    is_gateway: bool = False
    last_seen: str = ""
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ip": self.ip,
            "mac": self.mac,
            "hostname": self.hostname,
            "node_type": self.node_type.value,
            "vendor": self.vendor,
            "ports_open": self.ports_open,
            "is_gateway": self.is_gateway,
            "last_seen": self.last_seen
        }


@dataclass
class NetworkLink:
    """A link between two nodes"""
    source_id: str
    target_id: str
    link_type: str = "ethernet"  # ethernet, wifi, vpn
    latency_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.link_type,
            "latency_ms": self.latency_ms
        }


class NetworkTopology:
    """
    Network topology discovery and visualization
    
    Features:
    - ARP table scanning
    - Ping sweep discovery
    - Mermaid diagram generation
    - Topology export
    """
    
    def __init__(self):
        self.nodes: Dict[str, NetworkNode] = {}
        self.links: List[NetworkLink] = []
        self._gateway_ip: Optional[str] = None
        self._local_ip: Optional[str] = None
        self._subnet: Optional[str] = None
    
    def _detect_local_network(self):
        """Detect local network information"""
        try:
            # Get local IP first (works on all platforms)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self._local_ip = s.getsockname()[0]
            s.close()
            
            # Determine subnet from local IP
            if self._local_ip:
                parts = self._local_ip.split('.')
                self._subnet = f"{parts[0]}.{parts[1]}.{parts[2]}"
            
            # Try to get gateway - Windows method using ipconfig
            try:
                result = subprocess.run(
                    ['ipconfig'],
                    capture_output=True, text=True, timeout=5
                )
                # Find "Default Gateway" line
                for line in result.stdout.split('\n'):
                    if 'Default Gateway' in line or 'Gateway' in line:
                        match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                        if match:
                            self._gateway_ip = match.group(1)
                            break
            except Exception:
                pass
            
            # Fallback: assume gateway is .1 of subnet
            if not self._gateway_ip and self._subnet:
                self._gateway_ip = f"{self._subnet}.1"
                
        except Exception as e:
            print(f"Error detecting network: {e}")
    
    async def discover_via_arp(self) -> List[NetworkNode]:
        """Discover devices via ARP table"""
        nodes = []
        
        try:
            # Get ARP table
            result = await asyncio.to_thread(
                subprocess.run,
                ['arp', '-a'],
                capture_output=True, text=True, timeout=10
            )
            
            # Parse ARP entries
            for line in result.stdout.split('\n'):
                # Match IP and MAC addresses
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
                
                if ip_match:
                    ip = ip_match.group(1)
                    mac = mac_match.group(0) if mac_match else None
                    
                    # Skip broadcast and special addresses
                    if ip.endswith('.255') or ip == '255.255.255.255':
                        continue
                    
                    node_id = f"node_{ip.replace('.', '_')}"
                    
                    node = NetworkNode(
                        id=node_id,
                        ip=ip,
                        mac=mac,
                        is_gateway=(ip == self._gateway_ip),
                        last_seen=datetime.now().isoformat()
                    )
                    
                    # Detect vendor from MAC
                    if mac:
                        node.vendor = self._get_vendor_from_mac(mac)
                    
                    # Guess node type
                    node.node_type = self._guess_node_type(node)
                    
                    nodes.append(node)
                    self.nodes[node_id] = node
            
        except Exception as e:
            print(f"ARP discovery error: {e}")
        
        return nodes
    
    async def ping_sweep(self, subnet: str = None, start: int = 1, end: int = 254) -> List[NetworkNode]:
        """Discover devices via ping sweep"""
        if not subnet:
            self._detect_local_network()
            subnet = self._subnet
        
        if not subnet:
            return []
        
        discovered = []
        tasks = []
        
        # Create ping tasks (limit concurrency)
        semaphore = asyncio.Semaphore(50)
        
        async def ping_host(ip: str) -> Optional[NetworkNode]:
            async with semaphore:
                try:
                    # Quick ping
                    proc = await asyncio.create_subprocess_exec(
                        'ping', '-n', '1', '-w', '500', ip,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await asyncio.wait_for(proc.wait(), timeout=2)
                    
                    if proc.returncode == 0:
                        node_id = f"node_{ip.replace('.', '_')}"
                        node = NetworkNode(
                            id=node_id,
                            ip=ip,
                            is_gateway=(ip == self._gateway_ip),
                            last_seen=datetime.now().isoformat()
                        )
                        return node
                except Exception:
                    pass
                return None
        
        # Create tasks for range
        for i in range(start, min(end + 1, 255)):
            ip = f"{subnet}.{i}"
            tasks.append(ping_host(ip))
        
        # Execute with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=60
            )
            
            for result in results:
                if isinstance(result, NetworkNode):
                    discovered.append(result)
                    self.nodes[result.id] = result
        except asyncio.TimeoutError:
            print("Ping sweep timed out")
        
        return discovered
    
    def _get_vendor_from_mac(self, mac: str) -> Optional[str]:
        """Get vendor from MAC OUI (simplified)"""
        # Common vendor prefixes
        oui_map = {
            "00:50:56": "VMware",
            "00:0C:29": "VMware",
            "08:00:27": "VirtualBox",
            "52:54:00": "QEMU/KVM",
            "B8:27:EB": "Raspberry Pi",
            "DC:A6:32": "Raspberry Pi",
            "00:1A:2B": "Cisco",
            "00:1B:2B": "Cisco",
            "00:1C:B3": "Cisco",
            "00:22:55": "Cisco",
            "4C:5E:0C": "Mikrotik",
            "6C:3B:6B": "Mikrotik",
            "00:0C:42": "Mikrotik",
            "00:23:CD": "TP-Link",
            "50:C7:BF": "TP-Link",
            "00:1F:A4": "D-Link",
            "00:26:5A": "D-Link",
            "00:1E:58": "Ubiquiti",
            "24:A4:3C": "Ubiquiti",
            "FC:EC:DA": "Ubiquiti",
        }
        
        mac_upper = mac.upper().replace('-', ':')
        prefix = mac_upper[:8]
        
        return oui_map.get(prefix)
    
    def _guess_node_type(self, node: NetworkNode) -> NodeType:
        """Guess node type based on available info"""
        if node.is_gateway:
            return NodeType.GATEWAY
        
        if node.vendor:
            vendor_lower = node.vendor.lower()
            if any(x in vendor_lower for x in ['cisco', 'mikrotik', 'ubiquiti', 'juniper']):
                return NodeType.ROUTER
            if 'vmware' in vendor_lower or 'virtualbox' in vendor_lower:
                return NodeType.SERVER
        
        # Check common server ports
        if node.ports_open:
            if any(p in node.ports_open for p in [22, 80, 443, 3306, 5432]):
                return NodeType.SERVER
        
        return NodeType.UNKNOWN
    
    def build_links(self):
        """Build links between nodes (assumes star topology from gateway)"""
        self.links.clear()
        
        # Find gateway
        gateway = None
        for node in self.nodes.values():
            if node.is_gateway:
                gateway = node
                break
        
        if gateway:
            # Connect all nodes to gateway
            for node in self.nodes.values():
                if node.id != gateway.id:
                    link = NetworkLink(
                        source_id=gateway.id,
                        target_id=node.id,
                        link_type="ethernet"
                    )
                    self.links.append(link)
    
    def generate_mermaid(self) -> str:
        """Generate Mermaid diagram of topology"""
        lines = ["graph TD"]
        
        # Add styling
        lines.append("    classDef gateway fill:#e74c3c,stroke:#c0392b,color:white")
        lines.append("    classDef router fill:#3498db,stroke:#2980b9,color:white")
        lines.append("    classDef server fill:#2ecc71,stroke:#27ae60,color:white")
        lines.append("    classDef workstation fill:#9b59b6,stroke:#8e44ad,color:white")
        lines.append("    classDef unknown fill:#95a5a6,stroke:#7f8c8d,color:white")
        
        # Add nodes
        for node in self.nodes.values():
            label = node.hostname or node.ip
            if node.vendor:
                label += f"\\n({node.vendor})"
            
            # Node shape based on type
            if node.node_type == NodeType.GATEWAY:
                lines.append(f'    {node.id}["{label}"]:::gateway')
            elif node.node_type == NodeType.ROUTER:
                lines.append(f'    {node.id}{{"{label}"}}:::router')
            elif node.node_type == NodeType.SERVER:
                lines.append(f'    {node.id}[("{label}")]:::server')
            else:
                lines.append(f'    {node.id}["{label}"]:::unknown')
        
        # Add links
        for link in self.links:
            lines.append(f"    {link.source_id} --- {link.target_id}")
        
        return "\n".join(lines)
    
    def generate_ascii(self) -> str:
        """Generate ASCII art topology"""
        if not self.nodes:
            return "No nodes discovered"
        
        lines = []
        lines.append("=" * 60)
        lines.append("NETWORK TOPOLOGY")
        lines.append("=" * 60)
        
        # Find gateway
        gateway = None
        other_nodes = []
        for node in self.nodes.values():
            if node.is_gateway:
                gateway = node
            else:
                other_nodes.append(node)
        
        if gateway:
            lines.append("")
            lines.append(f"         [{gateway.ip}]")
            lines.append(f"      ╔══ GATEWAY ══╗")
            if gateway.vendor:
                lines.append(f"      ║ {gateway.vendor:^12} ║")
            lines.append(f"      ╚══════════════╝")
            lines.append("             │")
            
            # Draw connections
            if other_nodes:
                width = min(len(other_nodes), 5)
                lines.append("     " + "────┬" * (width - 1) + "────")
                lines.append("     │   " * width)
                
                # Add nodes in rows
                for i in range(0, len(other_nodes), 5):
                    chunk = other_nodes[i:i+5]
                    row = ""
                    for node in chunk:
                        icon = self._get_type_icon(node.node_type)
                        row += f"[{icon}]  "
                    lines.append("     " + row)
                    
                    row = ""
                    for node in chunk:
                        ip_short = ".".join(node.ip.split(".")[-2:])
                        row += f"{ip_short:^6}"
                    lines.append("     " + row)
                    lines.append("")
        
        lines.append("=" * 60)
        lines.append(f"Total Nodes: {len(self.nodes)}")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def _get_type_icon(self, node_type: NodeType) -> str:
        """Get ASCII icon for node type"""
        icons = {
            NodeType.GATEWAY: "GW",
            NodeType.ROUTER: "RT",
            NodeType.SWITCH: "SW",
            NodeType.SERVER: "SV",
            NodeType.WORKSTATION: "PC",
            NodeType.UNKNOWN: "??"
        }
        return icons.get(node_type, "??")
    
    def export_json(self) -> Dict[str, Any]:
        """Export topology as JSON"""
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "links": [l.to_dict() for l in self.links],
            "gateway_ip": self._gateway_ip,
            "local_ip": self._local_ip,
            "subnet": self._subnet,
            "discovered_at": datetime.now().isoformat()
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get topology summary"""
        type_counts = {}
        for node in self.nodes.values():
            t = node.node_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        
        return {
            "total_nodes": len(self.nodes),
            "total_links": len(self.links),
            "gateway_ip": self._gateway_ip,
            "local_ip": self._local_ip,
            "subnet": self._subnet,
            "by_type": type_counts
        }


# Singleton instance
network_topology = NetworkTopology()
