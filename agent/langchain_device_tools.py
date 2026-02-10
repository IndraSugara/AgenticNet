"""
LangChain Device Management Tools

Tools for managing network devices through LangGraph agent:
- List and search devices
- Add new devices
- Check device status
- Get device details
"""
from langchain_core.tools import tool
from typing import List, Optional
from agent.infrastructure import infrastructure, DeviceType, DeviceStatus


@tool
def list_devices(device_type: str = None, status: str = None) -> str:
    """
    List all registered network devices with optional filtering.
    
    Args:
        device_type: Optional filter by type (router, switch, server, pc, printer, access_point, firewall)
        status: Optional filter by status (online, offline, degraded, unknown)
    
    Returns:
        List of devices with their status
    """
    devices = infrastructure.list_devices(device_type=device_type, status=status)
    
    if not devices:
        return "Tidak ada device yang terdaftar."
    
    lines = [f"📋 Daftar Device ({len(devices)} total):\n"]
    
    for d in devices:
        status_emoji = {
            "online": "✅",
            "offline": "❌", 
            "degraded": "⚠️",
            "unknown": "❓"
        }.get(d.status.value, "❓")
        
        lines.append(f"  {status_emoji} {d.name} ({d.ip})")
        lines.append(f"     Type: {d.type.value} | Location: {d.location or 'N/A'}")
        lines.append(f"     Uptime: {d.uptime_percent:.1f}% | ID: {d.id}")
        lines.append("")
    
    return "\n".join(lines)


@tool
def get_device_details(device_id: str) -> str:
    """
    Get detailed information about a specific device.
    
    Args:
        device_id: Device ID (e.g., 'dev_0001')
    
    Returns:
        Detailed device information
    """
    device = infrastructure.get_device(device_id)
    
    if not device:
        return f"Device dengan ID '{device_id}' tidak ditemukan."
    
    status_emoji = {
        "online": "✅",
        "offline": "❌",
        "degraded": "⚠️", 
        "unknown": "❓"
    }.get(device.status.value, "❓")
    
    lines = [
        f"📱 Detail Device: {device.name}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"ID: {device.id}",
        f"IP: {device.ip}",
        f"Type: {device.type.value}",
        f"Status: {status_emoji} {device.status.value}",
        f"Location: {device.location or 'N/A'}",
        f"Description: {device.description or 'N/A'}",
        f"Uptime: {device.uptime_percent:.1f}%",
        f"Monitored Ports: {device.ports_to_monitor}",
        f"Check Interval: {device.check_interval_seconds}s",
        f"Last Check: {device.last_check or 'Never'}",
        f"Last Online: {device.last_online or 'Unknown'}",
        f"Created: {device.created_at}",
    ]
    
    return "\n".join(lines)


@tool
def add_device(name: str, ip: str, device_type: str, location: str = "", description: str = "") -> str:
    """
    Add a new device to monitoring.
    
    Args:
        name: Device display name (e.g., 'Router Lantai 1')
        ip: IP address (e.g., '192.168.1.1')
        device_type: Type of device - router, switch, server, pc, printer, access_point, firewall
        location: Physical location (e.g., 'Ruang Server')
        description: Additional description
    
    Returns:
        Confirmation with device ID
    """
    try:
        device = infrastructure.add_device(
            name=name,
            ip=ip,
            device_type=device_type,
            location=location,
            description=description
        )
        
        return f"✅ Device berhasil ditambahkan!\n\nID: {device.id}\nName: {device.name}\nIP: {device.ip}\nType: {device.type.value}"
    
    except Exception as e:
        return f"❌ Gagal menambahkan device: {str(e)}"


@tool
def remove_device(device_id: str) -> str:
    """
    Remove a device from monitoring.
    
    Args:
        device_id: Device ID to remove (e.g., 'dev_0001')
    
    Returns:
        Confirmation message
    """
    device = infrastructure.get_device(device_id)
    
    if not device:
        return f"Device dengan ID '{device_id}' tidak ditemukan."
    
    device_name = device.name
    success = infrastructure.remove_device(device_id)
    
    if success:
        return f"✅ Device '{device_name}' (ID: {device_id}) berhasil dihapus dari monitoring."
    else:
        return f"❌ Gagal menghapus device."


@tool 
def get_infrastructure_summary() -> str:
    """
    Get overall infrastructure health summary.
    
    Returns:
        Summary of all devices status and health
    """
    summary = infrastructure.get_status_summary()
    
    if summary["total"] == 0:
        return "📊 Belum ada device yang terdaftar. Gunakan add_device untuk menambahkan."
    
    health_emoji = {
        "healthy": "✅",
        "warning": "⚠️",
        "critical": "❌",
        "unknown": "❓",
        "no_devices": "📭"
    }.get(summary["overall_health"], "❓")
    
    lines = [
        f"📊 Infrastructure Summary",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"Overall Health: {health_emoji} {summary['overall_health'].upper()}",
        f"",
        f"Device Status:",
        f"  ✅ Online: {summary['online']}",
        f"  ❌ Offline: {summary['offline']}",
        f"  ⚠️ Degraded: {summary['degraded']}",
        f"  ❓ Unknown: {summary['unknown']}",
        f"  📱 Total: {summary['total']}",
    ]
    
    if summary.get("by_type"):
        lines.append("")
        lines.append("By Type:")
        for typ, count in summary["by_type"].items():
            lines.append(f"  • {typ}: {count}")
    
    return "\n".join(lines)


@tool
def find_device_by_ip(ip_address: str) -> str:
    """
    Find a device by its IP address.
    
    Args:
        ip_address: IP address to search for
    
    Returns:
        Device details if found
    """
    device = infrastructure.get_device_by_ip(ip_address)
    
    if not device:
        return f"Tidak ada device dengan IP '{ip_address}' yang terdaftar."
    
    return get_device_details.invoke(device.id)


# Export all device tools
def get_device_tools() -> list:
    """Get all device management tools"""
    return [
        list_devices,
        get_device_details,
        add_device,
        remove_device,
        get_infrastructure_summary,
        find_device_by_ip,
    ]
