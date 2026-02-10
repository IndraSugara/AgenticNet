"""
LangChain Network Topology Tools

Tools for network topology discovery and visualization.
"""
import asyncio
from typing import Optional
from langchain_core.tools import tool

from agent.network_topology import network_topology


@tool
def discover_network() -> str:
    """
    Discover devices on the local network using ARP table scanning.
    This is a quick discovery method that finds devices already known to the system.
    
    Returns:
        List of discovered devices
    """
    import subprocess
    import re
    from datetime import datetime
    from agent.network_topology import network_topology, NetworkNode
    
    try:
        # Detect local network info
        network_topology._detect_local_network()
        
        # Synchronous ARP scan
        result = subprocess.run(
            ['arp', '-a'],
            capture_output=True, text=True, timeout=10
        )
        
        nodes = []
        for line in result.stdout.split('\n'):
            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
            
            if ip_match:
                ip = ip_match.group(1)
                mac = mac_match.group(0) if mac_match else None
                
                if ip.endswith('.255') or ip == '255.255.255.255':
                    continue
                
                node_id = f"node_{ip.replace('.', '_')}"
                node = NetworkNode(
                    id=node_id,
                    ip=ip,
                    mac=mac,
                    is_gateway=(ip == network_topology._gateway_ip),
                    last_seen=datetime.now().isoformat()
                )
                
                if mac:
                    node.vendor = network_topology._get_vendor_from_mac(mac)
                node.node_type = network_topology._guess_node_type(node)
                
                nodes.append(node)
                network_topology.nodes[node_id] = node
        
        network_topology.build_links()
        
        if not nodes:
            return "ℹ️ No devices found via ARP."
        
        output = f"## ✅ Network Discovery Complete\n\n"
        output += f"**Found {len(nodes)} devices**\n\n"
        
        for node in nodes[:15]:
            icon = "🌐" if node.is_gateway else "💻"
            output += f"- {icon} **{node.ip}**"
            if node.mac:
                output += f" ({node.mac[:8]}...)"
            if node.vendor:
                output += f" - {node.vendor}"
            output += "\n"
        
        if len(nodes) > 15:
            output += f"\n_...and {len(nodes) - 15} more devices_"
        
        return output
    except Exception as e:
        return f"❌ Discovery error: {str(e)}"


@tool
def scan_network(start_ip: int = 1, end_ip: int = 50) -> str:
    """
    Actively scan the network for devices using ping sweep.
    This takes longer but finds more devices.
    
    Args:
        start_ip: Start of IP range to scan (last octet, default: 1)
        end_ip: End of IP range to scan (last octet, default: 50)
    
    Returns:
        List of discovered devices
    """
    try:
        async def _scan():
            network_topology._detect_local_network()
            nodes = await network_topology.ping_sweep(
                start=start_ip, 
                end=min(end_ip, 254)
            )
            network_topology.build_links()
            return nodes
        
        # Limit range for performance
        if end_ip - start_ip > 100:
            return "⚠️ Range too large. Please scan max 100 IPs at a time."
        
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(_scan())
            return f"""🔍 Ping Sweep Started

**Scanning Range:** {network_topology._subnet}.{start_ip} - {network_topology._subnet}.{end_ip}

This may take 30-60 seconds. Run `get topology` to see results."""
        else:
            nodes = asyncio.run(_scan())
            
            output = f"## Ping Sweep Complete\n\n"
            output += f"**Range:** .{start_ip} - .{end_ip}\n"
            output += f"**Found:** {len(nodes)} responding hosts\n\n"
            
            for node in nodes:
                icon = "🌐" if node.is_gateway else "💻"
                output += f"- {icon} {node.ip}\n"
            
            return output
    except Exception as e:
        return f"❌ Scan error: {str(e)}"


@tool
def get_topology() -> str:
    """
    Get the current network topology as an ASCII diagram.
    Run discover_network first to populate the topology.
    
    Returns:
        ASCII network diagram
    """
    try:
        if not network_topology.nodes:
            return "ℹ️ No topology data. Run `discover network` first."
        
        ascii_diagram = network_topology.generate_ascii()
        summary = network_topology.get_summary()
        
        output = f"```\n{ascii_diagram}\n```\n\n"
        output += "**Legend:** GW=Gateway, RT=Router, SV=Server, PC=Workstation\n"
        
        if summary.get('by_type'):
            output += "\n**Device Types:**\n"
            for t, count in summary['by_type'].items():
                output += f"- {t}: {count}\n"
        
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def get_topology_mermaid() -> str:
    """
    Get the network topology as a Mermaid diagram.
    This can be rendered in Markdown viewers that support Mermaid.
    
    Returns:
        Mermaid diagram code
    """
    try:
        if not network_topology.nodes:
            return "ℹ️ No topology data. Run `discover network` first."
        
        mermaid = network_topology.generate_mermaid()
        
        output = "## Network Topology Diagram\n\n"
        output += "```mermaid\n"
        output += mermaid
        output += "\n```\n\n"
        output += "_Copy the mermaid code to render the diagram_"
        
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool  
def get_topology_summary() -> str:
    """
    Get a summary of the discovered network topology.
    
    Returns:
        Topology statistics
    """
    try:
        summary = network_topology.get_summary()
        
        if summary['total_nodes'] == 0:
            return "ℹ️ No topology data. Run `discover network` first."
        
        output = "## Network Topology Summary\n\n"
        output += f"**Gateway:** {summary.get('gateway_ip', 'Unknown')}\n"
        output += f"**Local IP:** {summary.get('local_ip', 'Unknown')}\n"
        output += f"**Subnet:** {summary.get('subnet', 'Unknown')}.0/24\n\n"
        output += f"**Total Nodes:** {summary['total_nodes']}\n"
        output += f"**Total Links:** {summary['total_links']}\n\n"
        
        if summary.get('by_type'):
            output += "### Device Types\n"
            for node_type, count in summary['by_type'].items():
                icon = {"gateway": "🌐", "router": "📡", "server": "🖥️", "workstation": "💻"}.get(node_type, "❓")
                output += f"- {icon} {node_type.title()}: {count}\n"
        
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def export_topology_json() -> str:
    """
    Export the network topology as JSON data.
    
    Returns:
        JSON representation of topology
    """
    import json
    try:
        if not network_topology.nodes:
            return "ℹ️ No topology data. Run `discover network` first."
        
        data = network_topology.export_json()
        
        output = "## Topology Export\n\n"
        output += "```json\n"
        output += json.dumps(data, indent=2)[:2000]
        if len(json.dumps(data)) > 2000:
            output += "\n... (truncated)"
        output += "\n```"
        
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


@tool
def get_device_neighbors(ip: str) -> str:
    """
    Get devices that are neighbors/connected to a specific IP.
    
    Args:
        ip: IP address to find neighbors for
    
    Returns:
        List of neighboring devices
    """
    try:
        node_id = f"node_{ip.replace('.', '_')}"
        
        if node_id not in network_topology.nodes:
            return f"ℹ️ Device {ip} not found in topology. Run `discover network` first."
        
        node = network_topology.nodes[node_id]
        neighbors = []
        
        # Find all links involving this node
        for link in network_topology.links:
            if link.source_id == node_id:
                target = network_topology.nodes.get(link.target_id)
                if target:
                    neighbors.append(target)
            elif link.target_id == node_id:
                source = network_topology.nodes.get(link.source_id)
                if source:
                    neighbors.append(source)
        
        if not neighbors:
            return f"ℹ️ No neighbors found for {ip}."
        
        output = f"## Neighbors of {ip}\n\n"
        for n in neighbors:
            output += f"- **{n.ip}**"
            if n.hostname:
                output += f" ({n.hostname})"
            if n.vendor:
                output += f" - {n.vendor}"
            output += f" [{n.node_type.value}]\n"
        
        return output
    except Exception as e:
        return f"❌ Error: {str(e)}"


def get_topology_tools() -> list:
    """Get all topology-related tools"""
    return [
        discover_network,
        scan_network,
        get_topology,
        get_topology_mermaid,
        get_topology_summary,
        export_topology_json,
        get_device_neighbors,
    ]
