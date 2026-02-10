"""
Network Diagnostic Tools

Provides tools for network diagnostics that the agent can use.
"""
import subprocess
import platform
import socket
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Result from a network tool"""
    success: bool
    output: str
    error: str = ""
    

class NetworkTools:
    """Collection of network diagnostic tools"""
    
    def __init__(self):
        self.is_windows = platform.system().lower() == "windows"
    
    def ping(self, host: str, count: int = 4) -> ToolResult:
        """
        Ping a host to check connectivity
        
        Args:
            host: Hostname or IP address
            count: Number of pings
        """
        try:
            if self.is_windows:
                cmd = ["ping", "-n", str(count), host]
            else:
                cmd = ["ping", "-c", str(count), host]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            
            return ToolResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", "Ping timeout")
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def traceroute(self, host: str) -> ToolResult:
        """
        Trace route to a host
        
        Args:
            host: Target hostname or IP
        """
        try:
            if self.is_windows:
                cmd = ["tracert", "-d", host]
            else:
                cmd = ["traceroute", "-n", host]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return ToolResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", "Traceroute timeout")
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def dns_lookup(self, hostname: str) -> ToolResult:
        """
        Perform DNS lookup
        
        Args:
            hostname: Domain name to resolve
        """
        try:
            ip_addresses = socket.gethostbyname_ex(hostname)
            output = f"Hostname: {ip_addresses[0]}\nAliases: {ip_addresses[1]}\nIP Addresses: {ip_addresses[2]}"
            return ToolResult(True, output)
        except socket.gaierror as e:
            return ToolResult(False, "", f"DNS lookup failed: {e}")
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def check_port(self, host: str, port: int, timeout: float = 5.0) -> ToolResult:
        """
        Check if a port is open
        
        Args:
            host: Target host
            port: Port number
            timeout: Connection timeout
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                return ToolResult(True, f"Port {port} is OPEN on {host}")
            else:
                return ToolResult(False, f"Port {port} is CLOSED on {host}")
        except socket.timeout:
            return ToolResult(False, "", f"Connection to {host}:{port} timed out")
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def port_scan(self, host: str, ports: List[int] = None) -> ToolResult:
        """
        Scan common ports on a host
        
        Args:
            host: Target host
            ports: List of ports to scan (default: common ports)
        """
        if ports is None:
            ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 993, 995, 3306, 3389, 5432, 8080]
        
        results = []
        open_ports = []
        
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    open_ports.append(port)
                    results.append(f"  [{port}] OPEN")
                else:
                    results.append(f"  [{port}] closed")
            except:
                results.append(f"  [{port}] error")
        
        output = f"Port Scan Results for {host}:\n" + "\n".join(results)
        output += f"\n\nOpen ports: {open_ports}"
        
        return ToolResult(True, output)
    
    def get_network_info(self) -> ToolResult:
        """Get local network configuration"""
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            output = f"Hostname: {hostname}\nLocal IP: {local_ip}"
            
            # Get more info on Windows
            if self.is_windows:
                result = subprocess.run(
                    ["ipconfig", "/all"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                output += f"\n\nFull Network Config:\n{result.stdout}"
            
            return ToolResult(True, output)
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def nslookup(self, domain: str) -> ToolResult:
        """
        Perform nslookup query
        
        Args:
            domain: Domain to query
        """
        try:
            result = subprocess.run(
                ["nslookup", domain],
                capture_output=True,
                text=True,
                timeout=10
            )
            return ToolResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr
            )
        except Exception as e:
            return ToolResult(False, "", str(e))
    
    def get_interfaces(self) -> Dict[str, Any]:
        """Get all network interfaces with their status"""
        try:
            import psutil
            interfaces = []
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            io_counters = psutil.net_io_counters(pernic=True)
            
            for iface, addrs_list in addrs.items():
                stat = stats.get(iface)
                io = io_counters.get(iface)
                
                iface_info = {
                    "name": iface,
                    "is_up": stat.isup if stat else False,
                    "speed": stat.speed if stat else 0,
                    "mtu": stat.mtu if stat else 0,
                    "addresses": [],
                    "bytes_sent": io.bytes_sent if io else 0,
                    "bytes_recv": io.bytes_recv if io else 0,
                    "packets_sent": io.packets_sent if io else 0,
                    "packets_recv": io.packets_recv if io else 0,
                    "errors_in": io.errin if io else 0,
                    "errors_out": io.errout if io else 0
                }
                
                for addr in addrs_list:
                    addr_info = {
                        "family": str(addr.family),
                        "address": addr.address
                    }
                    if addr.netmask:
                        addr_info["netmask"] = addr.netmask
                    iface_info["addresses"].append(addr_info)
                
                interfaces.append(iface_info)
            
            return {"success": True, "interfaces": interfaces}
        except ImportError:
            return {"success": False, "error": "psutil not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_connections(self, kind: str = "inet") -> Dict[str, Any]:
        """Get active network connections"""
        try:
            import psutil
            connections = []
            for conn in psutil.net_connections(kind=kind):
                conn_info = {
                    "family": str(conn.family),
                    "type": str(conn.type),
                    "local_addr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "",
                    "remote_addr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "",
                    "status": conn.status,
                    "pid": conn.pid
                }
                connections.append(conn_info)
            
            return {
                "success": True, 
                "total": len(connections),
                "connections": connections[:50]  # Limit to 50
            }
        except ImportError:
            return {"success": False, "error": "psutil not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def measure_latency(self, hosts: List[str] = None) -> Dict[str, Any]:
        """Measure latency to common hosts"""
        import time
        
        if hosts is None:
            hosts = ["8.8.8.8", "1.1.1.1", "google.com"]
        
        results = []
        for host in hosts:
            try:
                start = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                
                # Try to resolve if hostname
                try:
                    ip = socket.gethostbyname(host)
                except:
                    ip = host
                
                # Connect to port 80 or 443
                result = sock.connect_ex((ip, 443))
                latency = (time.time() - start) * 1000  # ms
                sock.close()
                
                results.append({
                    "host": host,
                    "ip": ip,
                    "latency_ms": round(latency, 2),
                    "reachable": result == 0
                })
            except Exception as e:
                results.append({
                    "host": host,
                    "latency_ms": -1,
                    "reachable": False,
                    "error": str(e)
                })
        
        return {"success": True, "latencies": results}
    
    def get_bandwidth_stats(self) -> Dict[str, Any]:
        """Get current bandwidth statistics"""
        try:
            import psutil
            import time
            
            # Get initial counters
            io1 = psutil.net_io_counters()
            time.sleep(1)
            io2 = psutil.net_io_counters()
            
            # Calculate rate (bytes per second)
            upload_rate = io2.bytes_sent - io1.bytes_sent
            download_rate = io2.bytes_recv - io1.bytes_recv
            
            return {
                "success": True,
                "upload_rate_kbps": round(upload_rate / 1024, 2),
                "download_rate_kbps": round(download_rate / 1024, 2),
                "total_bytes_sent": io2.bytes_sent,
                "total_bytes_recv": io2.bytes_recv,
                "total_packets_sent": io2.packets_sent,
                "total_packets_recv": io2.packets_recv,
                "errors_in": io2.errin,
                "errors_out": io2.errout,
                "drop_in": io2.dropin,
                "drop_out": io2.dropout
            }
        except ImportError:
            return {"success": False, "error": "psutil not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get ISP/Provider information by checking public IP
        
        Returns:
            Dict with provider info: ISP name, IP, country, city, AS number
        """
        import urllib.request
        import json
        
        try:
            # Try ip-api.com (free, no API key needed)
            url = "http://ip-api.com/json/?fields=status,message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,query"
            
            req = urllib.request.Request(url, headers={"User-Agent": "NetworkAgent/1.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            if data.get("status") == "success":
                return {
                    "success": True,
                    "public_ip": data.get("query", ""),
                    "isp": data.get("isp", "Unknown"),
                    "organization": data.get("org", ""),
                    "as_number": data.get("as", ""),
                    "country": data.get("country", ""),
                    "country_code": data.get("countryCode", ""),
                    "region": data.get("regionName", ""),
                    "city": data.get("city", ""),
                    "timezone": data.get("timezone", ""),
                    "latitude": data.get("lat"),
                    "longitude": data.get("lon")
                }
            else:
                return {"success": False, "error": data.get("message", "API error")}
        
        except urllib.error.URLError as e:
            # Fallback: try ipinfo.io
            try:
                url = "https://ipinfo.io/json"
                req = urllib.request.Request(url, headers={"User-Agent": "NetworkAgent/1.0"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = json.loads(response.read().decode())
                
                return {
                    "success": True,
                    "public_ip": data.get("ip", ""),
                    "isp": data.get("org", "Unknown"),
                    "organization": data.get("org", ""),
                    "country": data.get("country", ""),
                    "region": data.get("region", ""),
                    "city": data.get("city", ""),
                    "timezone": data.get("timezone", "")
                }
            except Exception as e2:
                return {"success": False, "error": f"Could not reach IP lookup service: {str(e2)}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_provider_info_formatted(self) -> ToolResult:
        """Get ISP/Provider info as formatted ToolResult"""
        info = self.get_provider_info()
        
        if info.get("success"):
            output = f"""🌐 Network Provider Information
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Public IP    : {info.get('public_ip', 'N/A')}
ISP          : {info.get('isp', 'Unknown')}
Organization : {info.get('organization', 'N/A')}
AS Number    : {info.get('as_number', 'N/A')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Location     : {info.get('city', '')}, {info.get('region', '')}, {info.get('country', '')}
Timezone     : {info.get('timezone', 'N/A')}"""
            return ToolResult(True, output)
        else:
            return ToolResult(False, "", info.get("error", "Unknown error"))


# Singleton instance
network_tools = NetworkTools()

