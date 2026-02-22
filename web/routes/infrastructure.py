"""
Infrastructure & Alert Routes

Endpoints for device management, monitoring control, alerts, and config import/export.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import List
import asyncio
import json

from agent.infrastructure import infrastructure
from agent.scheduler import scheduler
from agent.alerting import alert_manager, handle_device_alert

router = APIRouter()


# --- Request Models ---

class DeviceRequest(BaseModel):
    name: str
    ip: str
    type: str = "other"
    description: str = ""
    location: str = ""
    ports_to_monitor: List[int] = []
    check_interval: int = 60
    connection_protocol: str = "none"  # "ssh", "telnet", or "none"
    ssh_port: int = 22
    ssh_username: str = ""
    ssh_password: str = ""


# --- Device Management ---

@router.get("/infra/devices")
async def list_devices(device_type: str = None, status: str = None):
    """List all registered devices with optional filtering"""
    devices = infrastructure.list_devices(device_type=device_type, status=status)
    return {"count": len(devices), "devices": [d.to_dict() for d in devices]}


@router.post("/infra/devices")
async def add_device(request: DeviceRequest):
    """Add a new device to monitoring"""
    device = infrastructure.add_device(
        name=request.name,
        ip=request.ip,
        device_type=request.type,
        description=request.description,
        location=request.location,
        ports_to_monitor=request.ports_to_monitor,
        check_interval=request.check_interval
    )
    # Set remote access credentials if provided
    if request.ssh_username:
        device.connection_protocol = request.connection_protocol
        device.ssh_username = request.ssh_username
        device.ssh_password = request.ssh_password
        device.ssh_port = request.ssh_port
    return {"success": True, "message": f"Device '{device.name}' added", "device": device.to_dict()}


@router.get("/infra/devices/{device_id}")
async def get_device(device_id: str):
    """Get device details"""
    device = infrastructure.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device.to_dict()


@router.put("/infra/devices/{device_id}")
async def update_device(device_id: str, request: DeviceRequest):
    """Update device configuration"""
    device = infrastructure.update_device(
        device_id,
        name=request.name,
        ip=request.ip,
        type=request.type,
        description=request.description,
        location=request.location,
        ports_to_monitor=request.ports_to_monitor,
        check_interval_seconds=request.check_interval,
        ssh_port=request.ssh_port,
        ssh_username=request.ssh_username,
        ssh_password=request.ssh_password,
        connection_protocol=request.connection_protocol
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True, "device": device.to_dict()}


@router.delete("/infra/devices/{device_id}")
async def delete_device(device_id: str):
    """Remove a device from monitoring"""
    success = infrastructure.remove_device(device_id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True, "message": "Device removed"}


@router.get("/infra/devices/{device_id}/status")
async def check_device_status(device_id: str):
    """Check device status immediately"""
    result = await scheduler.check_now(device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    device = infrastructure.get_device(device_id)
    return {"device": device.to_dict() if device else None, "last_check": result.to_dict()}


@router.get("/infra/summary")
async def get_infrastructure_summary():
    """Get overall infrastructure status summary"""
    return infrastructure.get_status_summary()


# --- Monitoring Control ---

@router.post("/infra/monitor/start")
async def start_monitoring():
    """Start the automatic monitoring scheduler"""
    if scheduler.is_running:
        return {"success": True, "message": "Monitoring already running"}
    scheduler.set_alert_callback(handle_device_alert)
    await scheduler.start()
    return {
        "success": True,
        "message": "Monitoring started",
        "devices_count": len(infrastructure.list_devices())
    }


@router.post("/infra/monitor/stop")
async def stop_monitoring():
    """Stop the automatic monitoring"""
    if not scheduler.is_running:
        return {"success": True, "message": "Monitoring not running"}
    await scheduler.stop()
    return {"success": True, "message": "Monitoring stopped"}


@router.get("/infra/monitor/status")
async def get_infra_monitoring_status():
    """Get current monitoring status"""
    return {
        "running": scheduler.is_running,
        "devices_monitored": len(infrastructure.list_devices()),
        "last_results": {k: v.to_dict() for k, v in scheduler.get_all_results().items()}
    }


@router.post("/infra/monitor/check-all")
async def check_all_devices():
    """Immediately check all devices"""
    results = await scheduler.check_all_now()
    return {"success": True, "checked": len(results), "results": {k: v.to_dict() for k, v in results.items()}}


# --- Alerts ---

@router.get("/infra/alerts")
async def get_alerts(severity: str = None, device_id: str = None, unresolved_only: bool = True, limit: int = 50):
    """Get alerts with optional filtering"""
    alerts = alert_manager.get_alerts(
        severity=severity,
        device_id=device_id,
        unresolved_only=unresolved_only,
        limit=limit
    )
    return {"count": len(alerts), "alerts": [a.to_dict() for a in alerts]}


@router.get("/infra/alerts/summary")
async def get_alerts_summary():
    """Get alert summary"""
    return alert_manager.get_summary()


@router.post("/infra/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, by: str = "user"):
    """Acknowledge an alert"""
    success = alert_manager.acknowledge(alert_id, by)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True, "message": "Alert acknowledged"}


@router.post("/infra/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Resolve an alert"""
    success = alert_manager.resolve(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True, "message": "Alert resolved"}


# --- Device Logs for Terminal Panel ---

@router.get("/infra/devices/{device_id}/logs")
async def get_device_logs(device_id: str, limit: int = 50):
    """Get device health check history as log entries for terminal panel"""
    device = infrastructure.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    logs = []
    for check in reversed(device.health_history[-limit:]):
        # Main status line
        logs.append({
            "time": check.timestamp,
            "type": "success" if check.ping_ok else "error",
            "text": f"PING {'OK' if check.ping_ok else 'FAIL'} — {device.ip} — latency: {check.ping_latency_ms:.1f}ms" if check.ping_ok else f"PING FAIL — {device.ip} — host unreachable"
        })
        
        # Port check lines
        for port in check.ports_open:
            logs.append({"time": check.timestamp, "type": "port", "text": f"  PORT {port} — OPEN"})
        for port in check.ports_closed:
            logs.append({"time": check.timestamp, "type": "warning", "text": f"  PORT {port} — CLOSED"})
        
        # Status result
        status_type = {"online": "success", "offline": "error", "degraded": "warning", "unknown": "info"}
        logs.append({
            "time": check.timestamp,
            "type": status_type.get(check.status.value, "info"),
            "text": f"  STATUS → {check.status.value.upper()}"
        })
    
    return {
        "device_id": device_id,
        "device_name": device.name,
        "device_ip": device.ip,
        "device_status": device.status.value,
        "logs": logs
    }

# --- Terminal Command Execution ---

class TerminalCommand(BaseModel):
    command: str

@router.post("/infra/terminal/exec")
async def execute_terminal_command(request: TerminalCommand):
    """Execute a network command from the terminal panel"""
    from tools.network_tools import network_tools
    
    cmd = request.command.strip()
    if not cmd:
        return {"success": False, "output": "No command provided", "lines": []}
    
    parts = cmd.split(None, 1)
    action = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    lines = []
    
    try:
        if action == "ping":
            if not args:
                return {"success": False, "output": "Usage: ping <host> [count]", "lines": [{"type": "error", "text": "Usage: ping <host> [count]"}]}
            ping_parts = args.split()
            host = ping_parts[0]
            count = int(ping_parts[1]) if len(ping_parts) > 1 else 4
            lines.append({"type": "system", "text": f"$ ping {host} -c {count}"})
            result = network_tools.ping(host, count)
            if result.success:
                for line in result.output.split('\n'):
                    if line.strip():
                        lines.append({"type": "ping", "text": line.strip()})
            else:
                lines.append({"type": "error", "text": result.error or "Ping failed"})
                
        elif action == "traceroute" or action == "tracert":
            if not args:
                return {"success": False, "output": "Usage: traceroute <host>", "lines": [{"type": "error", "text": "Usage: traceroute <host>"}]}
            lines.append({"type": "system", "text": f"$ traceroute {args}"})
            result = network_tools.traceroute(args.split()[0])
            if result.success:
                for line in result.output.split('\n'):
                    if line.strip():
                        lines.append({"type": "info", "text": line.strip()})
            else:
                lines.append({"type": "error", "text": result.error or "Traceroute failed"})
                
        elif action == "port_scan" or action == "portscan" or action == "scan":
            if not args:
                return {"success": False, "output": "Usage: port_scan <host> [ports]", "lines": [{"type": "error", "text": "Usage: port_scan <host> [port1,port2,...]"}]}
            scan_parts = args.split()
            host = scan_parts[0]
            ports = None
            if len(scan_parts) > 1:
                ports = [int(p) for p in scan_parts[1].split(',')]
            lines.append({"type": "system", "text": f"$ port_scan {host}" + (f" [{','.join(map(str, ports))}]" if ports else "")})
            result = network_tools.port_scan(host, ports)
            if result.success:
                for line in result.output.split('\n'):
                    if line.strip():
                        ltype = "success" if "open" in line.lower() else "warning" if "closed" in line.lower() else "port"
                        lines.append({"type": ltype, "text": line.strip()})
            else:
                lines.append({"type": "error", "text": result.error or "Port scan failed"})
                
        elif action == "dns" or action == "nslookup" or action == "dig":
            if not args:
                return {"success": False, "output": "Usage: dns <hostname>", "lines": [{"type": "error", "text": "Usage: dns <hostname>"}]}
            lines.append({"type": "system", "text": f"$ dns {args}"})
            result = network_tools.dns_lookup(args.split()[0])
            if result.success:
                for line in result.output.split('\n'):
                    if line.strip():
                        lines.append({"type": "info", "text": line.strip()})
            else:
                lines.append({"type": "error", "text": result.error or "DNS lookup failed"})

        elif action == "help":
            lines = [
                {"type": "system", "text": "Built-in commands (use AgenticNet tools):"},
                {"type": "info", "text": "  ping <host> [count]     - Ping a host"},
                {"type": "info", "text": "  traceroute <host>       - Trace route to host"},
                {"type": "info", "text": "  port_scan <host> [p,p]  - Scan ports on host"},
                {"type": "info", "text": "  dns <hostname>          - DNS lookup"},
                {"type": "system", "text": ""},
                {"type": "system", "text": "System commands (run directly):"},
                {"type": "info", "text": "  ipconfig, netstat, arp, nslookup, whoami, hostname, etc."},
                {"type": "info", "text": "  Any valid system command will be executed."},
                {"type": "info", "text": "  help                    - Show this help"},
            ]
        else:
            # General system command execution via subprocess
            import subprocess as sp
            try:
                lines.append({"type": "system", "text": f"$ {cmd}"})
                proc = sp.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30,
                    encoding='utf-8', errors='replace'
                )
                output_text = proc.stdout or ""
                error_text = proc.stderr or ""
                
                if output_text.strip():
                    for line in output_text.split('\n'):
                        if line.strip():
                            lines.append({"type": "info", "text": line.rstrip()})
                
                if error_text.strip():
                    for line in error_text.split('\n'):
                        if line.strip():
                            lines.append({"type": "warning", "text": line.rstrip()})
                
                if proc.returncode != 0 and not output_text.strip() and not error_text.strip():
                    lines.append({"type": "error", "text": f"Command exited with code {proc.returncode}"})
                    
                if not output_text.strip() and not error_text.strip() and proc.returncode == 0:
                    lines.append({"type": "success", "text": "Command completed successfully (no output)."})
                    
            except sp.TimeoutExpired:
                lines.append({"type": "error", "text": "Command timed out (30s limit). Use shorter-running commands."})
            except Exception as ex:
                lines.append({"type": "error", "text": f"Failed to execute: {str(ex)}"})
            
    except Exception as e:
        lines.append({"type": "error", "text": f"Error: {str(e)}"})
    
    return {"success": True, "command": cmd, "lines": lines}


# --- SSH Remote Command Execution ---

class SSHCommand(BaseModel):
    command: str

@router.post("/infra/devices/{device_id}/ssh/exec")
async def ssh_execute_command(device_id: str, request: SSHCommand):
    """Execute a command on a remote device via SSH"""
    import paramiko
    
    device = infrastructure.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not device.ssh_username:
        return {
            "success": False,
            "lines": [{"type": "error", "text": f"SSH not configured for {device.name}. Edit device to add SSH credentials."}]
        }
    
    cmd = request.command.strip()
    if not cmd:
        return {"success": False, "lines": [{"type": "error", "text": "No command provided"}]}
    
    lines = []
    
    def _ssh_exec():
        """Run SSH command in thread to avoid blocking event loop"""
        result_lines = []
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            client.connect(
                hostname=device.ip,
                port=device.ssh_port,
                username=device.ssh_username,
                password=device.ssh_password,
                timeout=10,
                allow_agent=False,
                look_for_keys=False
            )
            
            stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
            
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
            exit_code = stdout.channel.recv_exit_status()
            
            if out.strip():
                for line in out.split('\n'):
                    if line.rstrip():
                        result_lines.append({"type": "info", "text": line.rstrip()})
            
            if err.strip():
                for line in err.split('\n'):
                    if line.rstrip():
                        result_lines.append({"type": "warning", "text": line.rstrip()})
            
            if not out.strip() and not err.strip():
                if exit_code == 0:
                    result_lines.append({"type": "success", "text": "Command completed (no output)."})
                else:
                    result_lines.append({"type": "error", "text": f"Command exited with code {exit_code}"})
                    
        except paramiko.AuthenticationException:
            result_lines.append({"type": "error", "text": f"SSH authentication failed for {device.ssh_username}@{device.ip}"})
        except paramiko.SSHException as e:
            result_lines.append({"type": "error", "text": f"SSH error: {str(e)}"})
        except Exception as e:
            result_lines.append({"type": "error", "text": f"Connection failed: {str(e)}"})
        finally:
            client.close()
        
        return result_lines
    
    lines = await asyncio.to_thread(_ssh_exec)
    
    return {"success": True, "command": cmd, "device": device.name, "lines": lines}


# --- Unified Remote Command Execution (auto-routes SSH/Telnet) ---

@router.post("/infra/devices/{device_id}/remote/exec")
async def remote_execute_command(device_id: str, request: SSHCommand):
    """Execute a command on a remote device — auto-routes to SSH or Telnet"""
    device = infrastructure.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not device.ssh_username or device.connection_protocol == "none":
        return {
            "success": False,
            "lines": [{"type": "error", "text": f"Remote access not configured for {device.name}. Edit device to add credentials."}]
        }
    
    if device.connection_protocol == "ssh":
        return await ssh_execute_command(device_id, request)
    elif device.connection_protocol == "telnet":
        return await telnet_execute_command(device_id, request)
    else:
        return {
            "success": False,
            "lines": [{"type": "error", "text": f"Unknown protocol: {device.connection_protocol}"}]
        }


# --- Telnet Remote Command Execution ---

@router.post("/infra/devices/{device_id}/telnet/exec")
async def telnet_execute_command(device_id: str, request: SSHCommand):
    """Execute a command on a remote device via Telnet"""
    import socket
    import time
    
    device = infrastructure.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not device.ssh_username:
        return {
            "success": False,
            "lines": [{"type": "error", "text": f"Telnet not configured for {device.name}. Edit device to add credentials."}]
        }
    
    cmd = request.command.strip()
    if not cmd:
        return {"success": False, "lines": [{"type": "error", "text": "No command provided"}]}
    
    def _telnet_exec():
        """Run Telnet command in thread"""
        result_lines = []
        port = device.ssh_port if device.ssh_port != 22 else 23  # Default telnet port
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((device.ip, port))
            
            def recv_until(expected, timeout=5):
                """Receive data until expected string or timeout"""
                data = b""
                start = time.time()
                while time.time() - start < timeout:
                    try:
                        sock.settimeout(0.5)
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                        if expected.encode() in data.lower():
                            break
                    except socket.timeout:
                        if data:
                            break
                        continue
                return data.decode('utf-8', errors='replace')
            
            # Wait for login prompt
            banner = recv_until("login:", timeout=5)
            if not banner:
                banner = recv_until("username:", timeout=3)
            
            # Send username
            sock.sendall((device.ssh_username + "\n").encode())
            recv_until("password:", timeout=5)
            
            # Send password
            sock.sendall((device.ssh_password + "\n").encode())
            login_result = recv_until(">", timeout=5)
            if not login_result:
                login_result = recv_until("#", timeout=3)
            if not login_result:
                login_result = recv_until("$", timeout=3)
            
            # Check for auth failure
            lower_result = login_result.lower()
            if "incorrect" in lower_result or "failed" in lower_result or "denied" in lower_result:
                result_lines.append({"type": "error", "text": f"Telnet authentication failed for {device.ssh_username}@{device.ip}"})
                sock.close()
                return result_lines
            
            # Send command
            sock.sendall((cmd + "\n").encode())
            time.sleep(1)
            
            # Read output
            output = recv_until("", timeout=5)
            
            if output.strip():
                lines_raw = output.split('\n')
                for line in lines_raw:
                    cleaned = line.strip()
                    # Skip echo of command and prompt lines
                    if cleaned and cleaned != cmd and not cleaned.endswith('>') and not cleaned.endswith('#'):
                        result_lines.append({"type": "info", "text": cleaned})
            
            if not result_lines:
                result_lines.append({"type": "success", "text": "Command completed (no output)."})
                
            sock.close()
            
        except socket.timeout:
            result_lines.append({"type": "error", "text": f"Telnet connection to {device.ip}:{port} timed out"})
        except ConnectionRefusedError:
            result_lines.append({"type": "error", "text": f"Telnet connection refused on {device.ip}:{port}"})
        except Exception as e:
            result_lines.append({"type": "error", "text": f"Telnet error: {str(e)}"})
        
        return result_lines
    
    lines = await asyncio.to_thread(_telnet_exec)
    
    return {"success": True, "command": cmd, "device": device.name, "lines": lines}



@router.websocket("/infra/live")
async def infrastructure_live(websocket: WebSocket):
    """WebSocket for real-time infrastructure status updates"""
    await websocket.accept()
    try:
        await websocket.send_json({
            "type": "initial",
            "summary": infrastructure.get_status_summary(),
            "devices": [d.to_dict() for d in infrastructure.list_devices()],
            "alerts": [a.to_dict() for a in alert_manager.get_active_alerts()[:10]]
        })
        
        while True:
            await asyncio.sleep(5)
            await websocket.send_json({
                "type": "update",
                "summary": infrastructure.get_status_summary(),
                "devices": [d.to_dict() for d in infrastructure.list_devices()],
                "alerts_count": len(alert_manager.get_active_alerts()),
                "monitoring_running": scheduler.is_running
            })
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# --- Config Export/Import ---

@router.get("/infra/config/export")
async def export_config():
    """Export device configuration as JSON"""
    return {"config": infrastructure.export_config()}


@router.post("/infra/config/import")
async def import_config(config: dict):
    """Import device configuration from JSON"""
    try:
        count = infrastructure.import_config(json.dumps(config))
        return {"success": True, "imported": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
