"""
Device Command & Inventory Routes

Endpoints for unified device commands, inventory management.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from modules.inventory import inventory, DeviceInfo, VendorType, DeviceRole
from tools.vendor_drivers import connection_manager, UnifiedCommand
from tools.unified_commands import unified_commands

router = APIRouter()


# --- Request Models ---

class InventoryDeviceRequest(BaseModel):
    id: str
    name: str
    ip_address: str
    vendor: str = "unknown"
    role: str = "other"
    model: str = ""
    location: str = ""
    description: str = ""
    ssh_port: int = 22
    credential_id: str = "default"


class DeviceCommandRequest(BaseModel):
    device_ip: str
    command: str  # Unified command name
    params: dict = {}


# --- Inventory Endpoints ---

@router.get("/inventory")
async def get_inventory(vendor: str = None, enabled_only: bool = True):
    """Get all devices from inventory (Source of Truth)"""
    vendor_filter = None
    if vendor:
        try:
            vendor_filter = VendorType(vendor)
        except ValueError:
            pass
    
    devices = inventory.list_devices(vendor=vendor_filter, enabled_only=enabled_only)
    return {"count": len(devices), "devices": [d.to_dict() for d in devices]}


@router.get("/inventory/{device_ip}")
async def get_inventory_device(device_ip: str):
    """Get device info from inventory"""
    device = inventory.get_device(device_ip)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found in inventory")
    return device.to_dict()


@router.post("/inventory")
async def add_inventory_device(request: InventoryDeviceRequest):
    """Add device to inventory"""
    vendor_aliases = {
        "mikrotik": "mikrotik_routeros",
        "ubiquiti": "ubiquiti_edgerouter",
        "ubiquiti_edge": "ubiquiti_edgerouter",
        "cisco": "cisco_ios",
        "linux": "linux",
        "cisco_ios": "cisco_ios",
        "cisco_nxos": "cisco_nxos",
        "mikrotik_routeros": "mikrotik_routeros",
    }
    
    vendor_value = vendor_aliases.get(request.vendor.lower(), request.vendor)
    
    try:
        vendor_type = VendorType(vendor_value)
    except ValueError:
        vendor_type = VendorType.UNKNOWN
    
    try:
        device_role = DeviceRole(request.role)
    except ValueError:
        device_role = DeviceRole.OTHER
    
    device = DeviceInfo(
        id=request.id,
        name=request.name,
        ip_address=request.ip_address,
        vendor=vendor_type,
        role=device_role,
        model=request.model,
        location=request.location,
        description=request.description,
        ssh_port=request.ssh_port,
        credential_id=request.credential_id
    )
    success = inventory.add_device(device)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to add device (may already exist)")
    return {"success": True, "device": device.to_dict()}


@router.delete("/inventory/{device_ip}")
async def delete_inventory_device(device_ip: str):
    """Remove device from inventory"""
    success = inventory.delete_device(device_ip)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True}


# --- Unified Device Commands ---

@router.post("/device/command")
async def execute_device_command(request: DeviceCommandRequest):
    """Execute unified command on a device"""
    try:
        cmd = UnifiedCommand(request.command)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown command: {request.command}")
    
    result = await connection_manager.execute_on_device(
        request.device_ip, cmd, request.params
    )
    return result.to_dict()


@router.get("/device/{device_ip}/interfaces")
async def get_device_interfaces(device_ip: str):
    """Get interfaces from network device"""
    result = await unified_commands.get_interfaces(device_ip)
    return result.to_dict()


@router.get("/device/{device_ip}/cpu-memory")
async def get_device_resources(device_ip: str):
    """Get CPU and memory usage from device"""
    result = await unified_commands.get_cpu_memory(device_ip)
    return result.to_dict()


@router.get("/device/{device_ip}/routing")
async def get_device_routing(device_ip: str):
    """Get routing table from device"""
    result = await unified_commands.get_routing_table(device_ip)
    return result.to_dict()


@router.get("/device/{device_ip}/arp")
async def get_device_arp(device_ip: str):
    """Get ARP table from device"""
    result = await unified_commands.get_arp_table(device_ip)
    return result.to_dict()


@router.get("/device/{device_ip}/logs")
async def get_device_logs(device_ip: str):
    """Get recent logs from device"""
    result = await unified_commands.get_logs(device_ip)
    return result.to_dict()


@router.post("/device/{device_ip}/ping")
async def ping_from_device(device_ip: str, target: str):
    """Ping target from device"""
    result = await unified_commands.ping(device_ip, target)
    return result.to_dict()
