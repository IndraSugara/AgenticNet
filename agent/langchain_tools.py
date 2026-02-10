"""
LangChain Tools for Network Diagnostics

Converts network_tools to LangChain tool format for use with LangGraph agents.
"""
from typing import List, Optional
from langchain_core.tools import tool
from tools.network_tools import network_tools


# ============= CONNECTIVITY TOOLS =============

@tool
def ping(host: str, count: int = 4) -> str:
    """
    Ping a host to check network connectivity.
    
    Args:
        host: Target IP address or hostname (e.g., 'google.com', '8.8.8.8')
        count: Number of ping packets to send (default: 4)
    
    Returns:
        Ping results with latency information
    """
    result = network_tools.ping(host, count)
    if result.success:
        return result.output
    return result.error


@tool
def traceroute(host: str) -> str:
    """
    Trace the network path to a host, showing all hops.
    
    Args:
        host: Target IP address or hostname
    
    Returns:
        Network path with hop information and latencies
    """
    result = network_tools.traceroute(host)
    if result.success:
        return result.output
    return result.error


@tool
def check_port(host: str, port: int) -> str:
    """
    Check if a specific port is open on a host.
    
    Args:
        host: Target IP address or hostname
        port: Port number to check (e.g., 80, 443, 22)
    
    Returns:
        Port status (open/closed)
    """
    result = network_tools.check_port(host, port)
    if result.success:
        return result.output
    return result.error


@tool
def port_scan(host: str, ports: Optional[List[int]] = None) -> str:
    """
    Scan common ports on a host to find open services.
    
    Args:
        host: Target IP address or hostname
        ports: Optional list of specific ports to scan
    
    Returns:
        List of open and closed ports
    """
    result = network_tools.port_scan(host, ports)
    if result.success:
        return result.output
    return result.error


# ============= DNS TOOLS =============

@tool
def dns_lookup(hostname: str) -> str:
    """
    Perform DNS lookup to resolve a hostname to IP addresses.
    
    Args:
        hostname: Domain name to resolve (e.g., 'google.com')
    
    Returns:
        IP addresses associated with the hostname
    """
    result = network_tools.dns_lookup(hostname)
    if result.success:
        return result.output
    return result.error


@tool
def nslookup(domain: str) -> str:
    """
    Query DNS server for detailed domain information.
    
    Args:
        domain: Domain name to query
    
    Returns:
        DNS query results including nameservers
    """
    result = network_tools.nslookup(domain)
    if result.success:
        return result.output
    return f"Error: {result.error}"


# ============= INFO TOOLS =============

@tool
def get_network_info() -> str:
    """
    Get local network configuration including hostname and IP addresses.
    
    Returns:
        Local network configuration details
    """
    result = network_tools.get_network_info()
    if result.success:
        return result.output
    return f"Error: {result.error}"


@tool
def get_provider_info() -> str:
    """
    Get ISP/provider information including public IP, ISP name, and location.
    
    Returns:
        ISP details: public IP, ISP name, AS number, country, city, timezone
    """
    result = network_tools.get_provider_info()
    if result.get("success"):
        info = result
        return f"""🌐 Network Provider Information
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Public IP    : {info.get('public_ip', 'N/A')}
ISP          : {info.get('isp', 'Unknown')}
Organization : {info.get('organization', 'N/A')}
AS Number    : {info.get('as_number', 'N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Location     : {info.get('city', '')}, {info.get('region', '')}, {info.get('country', '')}
Timezone     : {info.get('timezone', 'N/A')}"""
    return f"Error: {result.get('error', 'Unknown error')}"


@tool
def get_interfaces() -> str:
    """
    List all network interfaces with their status and statistics.
    
    Returns:
        Network interface list with IP addresses, speed, and traffic stats
    """
    result = network_tools.get_interfaces()
    if result.get("success"):
        interfaces = result.get("interfaces", [])
        output = "Network Interfaces:\n" + "=" * 50 + "\n"
        for iface in interfaces:
            status = "UP" if iface.get("is_up") else "DOWN"
            output += f"\n{iface['name']} [{status}]\n"
            output += f"  Speed: {iface.get('speed', 0)} Mbps\n"
            output += f"  MTU: {iface.get('mtu', 0)}\n"
            output += f"  Sent: {iface.get('bytes_sent', 0):,} bytes\n"
            output += f"  Recv: {iface.get('bytes_recv', 0):,} bytes\n"
            for addr in iface.get("addresses", []):
                output += f"  {addr.get('family')}: {addr.get('address')}\n"
        return output
    return f"Error: {result.get('error', 'Unknown error')}"


# ============= MONITORING TOOLS =============

@tool
def get_connections() -> str:
    """
    List active network connections (TCP/UDP).
    
    Returns:
        Active connections with local/remote addresses and status
    """
    result = network_tools.get_connections()
    if result.get("success"):
        conns = result.get("connections", [])
        output = f"Active Connections: {result.get('total', 0)}\n" + "=" * 60 + "\n"
        for conn in conns[:20]:  # Limit display
            output += f"{conn.get('local_addr', '')} -> {conn.get('remote_addr', '')} [{conn.get('status', '')}]\n"
        if len(conns) > 20:
            output += f"... and {len(conns) - 20} more connections\n"
        return output
    return f"Error: {result.get('error', 'Unknown error')}"


@tool
def measure_latency(hosts: Optional[List[str]] = None) -> str:
    """
    Measure network latency to multiple hosts.
    
    Args:
        hosts: Optional list of hosts to measure (default: Google DNS, Cloudflare, Google)
    
    Returns:
        Latency measurements in milliseconds
    """
    result = network_tools.measure_latency(hosts)
    if result.get("success"):
        latencies = result.get("latencies", [])
        output = "Latency Measurements:\n" + "=" * 40 + "\n"
        for lat in latencies:
            status = "✓" if lat.get("reachable") else "✗"
            ms = lat.get("latency_ms", -1)
            output += f"{status} {lat.get('host', '')} ({lat.get('ip', '')}): {ms:.1f} ms\n"
        return output
    return f"Error: {result.get('error', 'Unknown error')}"


@tool
def get_bandwidth_stats() -> str:
    """
    Get current bandwidth usage statistics.
    
    Returns:
        Upload/download rates in KB/s and total bytes transferred
    """
    result = network_tools.get_bandwidth_stats()
    if result.get("success"):
        return f"""📊 Bandwidth Statistics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Upload Rate  : {result.get('upload_rate_kbps', 0):.2f} KB/s
Download Rate: {result.get('download_rate_kbps', 0):.2f} KB/s
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Sent   : {result.get('total_bytes_sent', 0):,} bytes
Total Recv   : {result.get('total_bytes_recv', 0):,} bytes
Packets Sent : {result.get('total_packets_sent', 0):,}
Packets Recv : {result.get('total_packets_recv', 0):,}
Errors In    : {result.get('errors_in', 0)}
Errors Out   : {result.get('errors_out', 0)}"""
    return f"Error: {result.get('error', 'Unknown error')}"


# ============= TOOL COLLECTION =============

def get_network_tools() -> list:
    """Get core network diagnostic tools"""
    return [
        ping,
        traceroute,
        check_port,
        port_scan,
        dns_lookup,
        nslookup,
        get_network_info,
        get_provider_info,
        get_interfaces,
        get_connections,
        measure_latency,
        get_bandwidth_stats,
    ]


# Module-level cache for tools
_TOOLS_CACHE = None


def get_all_tools() -> list:
    """
    Get all tools for LangGraph agent including:
    - Network diagnostic tools (12)
    - Device management tools (6)
    - RAG/Knowledge base tools (4)
    - Scheduler/Alert tools (9)
    
    Uses caching to avoid repeated dynamic imports.
    """
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE
    
    tools = get_network_tools()
    
    # Add device management tools
    try:
        from agent.langchain_device_tools import get_device_tools
        tools.extend(get_device_tools())
    except ImportError:
        pass
    
    # Add RAG/knowledge tools
    try:
        from agent.langchain_rag_tools import get_rag_tools
        tools.extend(get_rag_tools())
    except ImportError:
        pass
    
    # Add scheduler/alert tools
    try:
        from agent.langchain_scheduler_tools import get_scheduler_tools
        tools.extend(get_scheduler_tools())
    except ImportError:
        pass
    
    # Add config backup tools
    try:
        from agent.langchain_backup_tools import get_backup_tools
        tools.extend(get_backup_tools())
    except ImportError:
        pass
    
    # Add memory tools
    try:
        from agent.langchain_memory_tools import get_memory_tools
        tools.extend(get_memory_tools())
    except ImportError:
        pass
    
    # Add topology tools
    try:
        from agent.langchain_topology_tools import get_topology_tools
        tools.extend(get_topology_tools())
    except ImportError:
        pass
    
    # Add report tools
    try:
        from agent.langchain_report_tools import get_report_tools
        tools.extend(get_report_tools())
    except ImportError:
        pass
    
    # Cache the tools list
    _TOOLS_CACHE = tools
    return tools


def get_tools_description() -> str:
    """Get human-readable description of all tools"""
    tools = get_all_tools()
    desc = f"Available Tools ({len(tools)} total):\n" + "=" * 50 + "\n\n"
    
    # Group by category
    categories = {
        "Network Diagnostics": ["ping", "traceroute", "check_port", "port_scan"],
        "DNS": ["dns_lookup", "nslookup"],
        "Network Info": ["get_network_info", "get_provider_info", "get_interfaces"],
        "Monitoring": ["get_connections", "measure_latency", "get_bandwidth_stats"],
        "Device Management": ["list_devices", "get_device_details", "add_device", "remove_device", "get_infrastructure_summary", "find_device_by_ip"],
        "Knowledge Base": ["search_knowledge", "add_knowledge", "get_knowledge_stats", "initialize_knowledge_base"],
    }
    
    for category, tool_names in categories.items():
        category_tools = [t for t in tools if t.name in tool_names]
        if category_tools:
            desc += f"\n## {category}\n"
            for t in category_tools:
                desc += f"• {t.name}: {t.description.split('.')[0]}.\n"
    
    return desc
