"""
LangChain Tools for Network Diagnostics

Converts network_tools to LangChain tool format for use with LangGraph agents.
"""
import asyncio
from typing import List, Optional
from langchain_core.tools import tool
from tools.network_tools import network_tools
from tools.pending_actions import pending_store


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


# ============= HIGH-RISK INTERFACE MANAGEMENT TOOLS =============

@tool
def disable_local_interface(interface_name: str) -> str:
    """
    ⚠️ HIGH-RISK: Disable (shutdown) a local network interface.
    This action requires confirmation before execution.
    Requires administrator privileges.
    
    Args:
        interface_name: Name of the interface to disable (e.g., 'Wi-Fi', 'Ethernet')
    
    Returns:
        Confirmation request or execution result
    """
    action = pending_store.add(
        tool_name="disable_interface",
        params={"interface_name": interface_name},
        description=f"Mematikan interface jaringan lokal '{interface_name}'",
        risk_reason="Mematikan interface dapat memutus koneksi jaringan"
    )
    return (
        f"⚠️ KONFIRMASI DIPERLUKAN\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Aksi      : Mematikan interface '{interface_name}'\n"
        f"Risiko    : TINGGI - Koneksi jaringan akan terputus\n"
        f"Action ID : {action.action_id}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Untuk melanjutkan, gunakan confirm_action dengan action_id '{action.action_id}'"
    )


@tool
def enable_local_interface(interface_name: str) -> str:
    """
    ⚠️ HIGH-RISK: Enable (activate) a local network interface.
    This action requires confirmation before execution.
    Requires administrator privileges.
    
    Args:
        interface_name: Name of the interface to enable (e.g., 'Wi-Fi', 'Ethernet')
    
    Returns:
        Confirmation request or execution result
    """
    action = pending_store.add(
        tool_name="enable_interface",
        params={"interface_name": interface_name},
        description=f"Mengaktifkan interface jaringan lokal '{interface_name}'",
        risk_reason="Mengubah status interface dapat mempengaruhi koneksi jaringan"
    )
    return (
        f"⚠️ KONFIRMASI DIPERLUKAN\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Aksi      : Mengaktifkan interface '{interface_name}'\n"
        f"Risiko    : TINGGI - Konfigurasi jaringan akan berubah\n"
        f"Action ID : {action.action_id}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Untuk melanjutkan, gunakan confirm_action dengan action_id '{action.action_id}'"
    )


@tool
def shutdown_remote_interface(device_ip: str, interface: str) -> str:
    """
    ⚠️ HIGH-RISK: Shutdown an interface on a remote network device via SSH.
    This action requires confirmation before execution.
    
    Args:
        device_ip: IP address of the remote device
        interface: Interface name on the device (e.g., 'GigabitEthernet0/1', 'ether1')
    
    Returns:
        Confirmation request or execution result
    """
    action = pending_store.add(
        tool_name="shutdown_remote_interface",
        params={"device_ip": device_ip, "interface": interface},
        description=f"Mematikan interface '{interface}' pada device {device_ip}",
        risk_reason="Mematikan interface remote dapat memutus koneksi ke device atau segmen jaringan"
    )
    return (
        f"⚠️ KONFIRMASI DIPERLUKAN\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Aksi      : Shutdown interface '{interface}' di {device_ip}\n"
        f"Risiko    : TINGGI - Bisa memutus segmen jaringan\n"
        f"Action ID : {action.action_id}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Untuk melanjutkan, gunakan confirm_action dengan action_id '{action.action_id}'"
    )


@tool
def enable_remote_interface(device_ip: str, interface: str) -> str:
    """
    ⚠️ HIGH-RISK: Enable (no shutdown) an interface on a remote network device via SSH.
    This action requires confirmation before execution.
    
    Args:
        device_ip: IP address of the remote device
        interface: Interface name on the device (e.g., 'GigabitEthernet0/1', 'ether1')
    
    Returns:
        Confirmation request or execution result
    """
    action = pending_store.add(
        tool_name="enable_remote_interface",
        params={"device_ip": device_ip, "interface": interface},
        description=f"Mengaktifkan interface '{interface}' pada device {device_ip}",
        risk_reason="Mengaktifkan interface remote dapat mengubah topologi jaringan"
    )
    return (
        f"⚠️ KONFIRMASI DIPERLUKAN\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Aksi      : Mengaktifkan interface '{interface}' di {device_ip}\n"
        f"Risiko    : TINGGI - Topologi jaringan akan berubah\n"
        f"Action ID : {action.action_id}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Untuk melanjutkan, gunakan confirm_action dengan action_id '{action.action_id}'"
    )

@tool
def execute_cli(device_ip: str, command: str) -> str:
    """
    ⚠️ HIGH-RISK: Execute a CLI command on a remote network device via SSH.
    This action requires confirmation before execution.
    Use for show/read-only commands (e.g., 'show ip route', 'display interface', '/ip address print').
    
    Args:
        device_ip: IP address of the target device (must be registered in inventory)
        command: CLI command to execute (e.g., 'show running-config', 'display version')
    
    Returns:
        Confirmation request or command output
    """
    from modules.inventory import inventory
    device = inventory.get_device(device_ip)
    device_name = device.name if device else device_ip
    
    action = pending_store.add(
        tool_name="execute_cli",
        params={"device_ip": device_ip, "command": command},
        description=f"Menjalankan perintah CLI '{command}' pada device {device_name} ({device_ip})",
        risk_reason="Eksekusi perintah CLI pada perangkat jaringan dapat mempengaruhi operasi jaringan"
    )
    return (
        f"⚠️ KONFIRMASI DIPERLUKAN\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Aksi      : Execute CLI pada {device_name} ({device_ip})\n"
        f"Perintah  : {command}\n"
        f"Risiko    : TINGGI - Perintah akan dieksekusi langsung pada perangkat\n"
        f"Action ID : {action.action_id}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Untuk melanjutkan, gunakan confirm_action dengan action_id '{action.action_id}'"
    )


@tool
def execute_cli_config(device_ip: str, commands: str) -> str:
    """
    ⚠️ HIGH-RISK: Execute configuration commands on a remote network device via SSH.
    This enters config mode and applies changes. Requires confirmation before execution.
    Multiple commands separated by semicolon (;).
    
    Args:
        device_ip: IP address of the target device (must be registered in inventory)
        commands: Config commands separated by semicolon (e.g., 'interface GigabitEthernet0/1; ip address 10.0.0.1 255.255.255.0; no shutdown')
    
    Returns:
        Confirmation request or execution result
    """
    from modules.inventory import inventory
    device = inventory.get_device(device_ip)
    device_name = device.name if device else device_ip
    
    cmd_list = [c.strip() for c in commands.split(";") if c.strip()]
    cmd_display = "\n".join([f"    {i+1}. {c}" for i, c in enumerate(cmd_list)])
    
    action = pending_store.add(
        tool_name="execute_cli_config",
        params={"device_ip": device_ip, "commands": commands},
        description=f"Menjalankan {len(cmd_list)} perintah konfigurasi pada device {device_name} ({device_ip})",
        risk_reason="Perintah konfigurasi akan MENGUBAH konfigurasi perangkat jaringan"
    )
    return (
        f"⚠️ KONFIRMASI DIPERLUKAN\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Aksi      : Execute Config pada {device_name} ({device_ip})\n"
        f"Perintah  :\n{cmd_display}\n"
        f"Risiko    : TINGGI - Konfigurasi perangkat akan DIUBAH\n"
        f"Action ID : {action.action_id}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Untuk melanjutkan, gunakan confirm_action dengan action_id '{action.action_id}'"
    )


@tool
def confirm_action(action_id: str) -> str:
    """
    Confirm and execute a pending high-risk action.
    Use this after the user explicitly confirms they want to proceed.
    
    Args:
        action_id: The action ID from the confirmation request
    
    Returns:
        Execution result of the confirmed action
    """
    action = pending_store.get(action_id)
    if not action:
        return f"❌ Action '{action_id}' tidak ditemukan atau sudah expired (5 menit)"
    
    if action.confirmed:
        return f"❌ Action '{action_id}' sudah dieksekusi sebelumnya"
    
    if action.cancelled:
        return f"❌ Action '{action_id}' sudah dibatalkan"
    
    # Execute based on tool name
    action.confirmed = True
    
    try:
        if action.tool_name == "disable_interface":
            result = network_tools.disable_interface(**action.params)
            return result.output if result.success else f"❌ {result.error}"
        
        elif action.tool_name == "enable_interface":
            result = network_tools.enable_interface(**action.params)
            return result.output if result.success else f"❌ {result.error}"
        
        elif action.tool_name in ("shutdown_remote_interface", "enable_remote_interface"):
            from tools.unified_commands import unified_commands
            if action.tool_name == "shutdown_remote_interface":
                coro = unified_commands.shutdown_interface(**action.params)
            else:
                coro = unified_commands.no_shutdown_interface(**action.params)
            
            # Run async function
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = loop.run_in_executor(pool, lambda: asyncio.run(coro))
            except RuntimeError:
                result = asyncio.run(coro)
            
            if hasattr(result, 'success'):
                if result.success:
                    return f"✅ {action.description} berhasil dilakukan"
                return f"❌ Gagal: {result.error}"
            return f"✅ {action.description} berhasil dilakukan"
        
        elif action.tool_name == "execute_cli":
            from tools.vendor_drivers import connection_manager
            coro = connection_manager.execute_raw(
                action.params["device_ip"], 
                action.params["command"]
            )
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = loop.run_in_executor(pool, lambda: asyncio.run(coro))
            except RuntimeError:
                result = asyncio.run(coro)
            
            if hasattr(result, 'success'):
                if result.success:
                    return f"✅ Perintah berhasil dijalankan pada {action.params['device_ip']}:\n\n```\n{result.output}\n```"
                return f"❌ Gagal: {result.error}"
            return str(result)
        
        elif action.tool_name == "execute_cli_config":
            from tools.vendor_drivers import connection_manager
            from modules.inventory import inventory
            device_ip = action.params["device_ip"]
            commands_str = action.params["commands"]
            cmd_list = [c.strip() for c in commands_str.split(";") if c.strip()]
            
            device = inventory.get_device(device_ip)
            if not device:
                return f"❌ Device {device_ip} tidak ditemukan di inventory"
            
            conn = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            
            async def _exec_config():
                c = await connection_manager.get_connection(device)
                if not c:
                    return None
                return await asyncio.to_thread(c.execute_config, cmd_list)
            
            try:
                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = loop.run_in_executor(pool, lambda: asyncio.run(_exec_config()))
                else:
                    result = asyncio.run(_exec_config())
            except RuntimeError:
                result = asyncio.run(_exec_config())
            
            if result is None:
                return f"❌ Gagal konek ke device {device_ip}"
            if hasattr(result, 'success'):
                if result.success:
                    return f"✅ Konfigurasi berhasil diterapkan pada {device_ip}:\n\n```\n{result.output}\n```"
                return f"❌ Gagal: {result.error}"
            return str(result)
        
        else:
            return f"❌ Executor untuk tool '{action.tool_name}' tidak ditemukan"
    
    except Exception as e:
        return f"❌ Error saat eksekusi: {str(e)}"


@tool
def cancel_action(action_id: str) -> str:
    """
    Cancel a pending high-risk action.
    Use this when the user declines/rejects the confirmation.
    
    Args:
        action_id: The action ID to cancel
    
    Returns:
        Cancellation status
    """
    result = pending_store.cancel(action_id)
    if result.get("success"):
        return f"✅ Action '{action_id}' berhasil dibatalkan"
    return f"❌ {result.get('error', 'Gagal membatalkan action')}"


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
    
    # Add log watch tools
    try:
        from agent.langchain_logwatch_tools import get_logwatch_tools
        tools.extend(get_logwatch_tools())
    except ImportError:
        pass
    
    # Add remediation tools
    try:
        from agent.langchain_remediation_tools import get_remediation_tools
        tools.extend(get_remediation_tools())
    except ImportError:
        pass
    
    # Add network intelligence tools
    try:
        from agent.langchain_intelligence_tools import get_intelligence_tools
        tools.extend(get_intelligence_tools())
    except ImportError:
        pass
    
    # Add high-risk interface management tools
    tools.extend([
        disable_local_interface,
        enable_local_interface,
        shutdown_remote_interface,
        enable_remote_interface,
        execute_cli,
        execute_cli_config,
        confirm_action,
        cancel_action,
    ])
    
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
        "Interface Management (High-Risk)": ["disable_local_interface", "enable_local_interface", "shutdown_remote_interface", "enable_remote_interface", "confirm_action", "cancel_action"],
        "CLI Execution (High-Risk)": ["execute_cli", "execute_cli_config"],
        "Log Monitoring": ["start_log_watch", "stop_log_watch", "get_log_watch_status", "get_device_logs", "get_recent_anomalies", "add_anomaly_pattern"],
    }
    
    for category, tool_names in categories.items():
        category_tools = [t for t in tools if t.name in tool_names]
        if category_tools:
            desc += f"\n## {category}\n"
            for t in category_tools:
                desc += f"• {t.name}: {t.description.split('.')[0]}.\n"
    
    return desc
