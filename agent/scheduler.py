"""
Monitoring Scheduler

Automated scheduled monitoring for infrastructure devices:
- Periodic health checks
- Configurable intervals per device
- Failure detection and alerting
- Background monitoring loop
"""
import asyncio
from typing import Dict, List, Optional, Callable
from datetime import datetime
import time
import socket

from agent.infrastructure import (
    infrastructure, 
    NetworkDevice, 
    DeviceStatus, 
    HealthCheckResult
)


class MonitoringScheduler:
    """
    Scheduled monitoring for network infrastructure
    
    Features:
    - Background monitoring loop
    - Per-device check intervals
    - Health check execution
    - Status change detection
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._alert_callback: Optional[Callable] = None
        self._status_callback: Optional[Callable] = None
        self._check_results: Dict[str, HealthCheckResult] = {}
        self._min_interval = 10  # Minimum check interval
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def set_alert_callback(self, callback: Callable):
        """Set callback for alerts (device down, etc.)"""
        self._alert_callback = callback
    
    def set_status_callback(self, callback: Callable):
        """Set callback for status updates"""
        self._status_callback = callback
    
    async def start(self):
        """Start the monitoring scheduler"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        print("🔄 Monitoring scheduler started")
    
    async def stop(self):
        """Stop the monitoring scheduler"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("⏹️ Monitoring scheduler stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        last_check: Dict[str, float] = {}
        
        while self._running:
            now = time.time()
            
            # Get all enabled devices
            devices = [d for d in infrastructure.list_devices() if d.enabled]
            
            for device in devices:
                last = last_check.get(device.id, 0)
                interval = max(device.check_interval_seconds, self._min_interval)
                
                if now - last >= interval:
                    # Time to check this device
                    asyncio.create_task(self._check_device(device))
                    last_check[device.id] = now
            
            # Sleep for a bit before next iteration
            await asyncio.sleep(5)
    
    async def _check_device(self, device: NetworkDevice):
        """Perform health check on a single device"""
        old_status = device.status
        
        try:
            result = await self._perform_health_check(device)
            device.update_status(result)
            self._check_results[device.id] = result
            
            # Notify status callback
            if self._status_callback:
                try:
                    if asyncio.iscoroutinefunction(self._status_callback):
                        await self._status_callback(device, result)
                    else:
                        self._status_callback(device, result)
                except Exception:
                    pass
            
            # Check for status change - trigger alert
            if old_status != device.status:
                if device.status == DeviceStatus.OFFLINE and self._alert_callback:
                    await self._trigger_alert(
                        device, 
                        "critical",
                        f"Device {device.name} ({device.ip}) is OFFLINE"
                    )
                elif device.status == DeviceStatus.DEGRADED and self._alert_callback:
                    await self._trigger_alert(
                        device,
                        "warning", 
                        f"Device {device.name} ({device.ip}) is DEGRADED - some ports closed"
                    )
                elif device.status == DeviceStatus.ONLINE and old_status == DeviceStatus.OFFLINE:
                    await self._trigger_alert(
                        device,
                        "info",
                        f"Device {device.name} ({device.ip}) is back ONLINE"
                    )
                    
        except Exception as e:
            print(f"❌ Error checking device {device.name}: {e}")
    
    async def _perform_health_check(self, device: NetworkDevice) -> HealthCheckResult:
        """Perform actual health check"""
        timestamp = datetime.now().isoformat()
        
        # Ping check
        ping_ok, latency = await self._ping(device.ip)
        
        # Port checks
        ports_open = []
        ports_closed = []
        
        for port in device.ports_to_monitor:
            is_open = await self._check_port(device.ip, port)
            if is_open:
                ports_open.append(port)
            else:
                ports_closed.append(port)
        
        # Determine status
        if not ping_ok:
            status = DeviceStatus.OFFLINE
        elif ports_closed and device.ports_to_monitor:
            # Some ports are closed
            if len(ports_closed) == len(device.ports_to_monitor):
                status = DeviceStatus.OFFLINE
            else:
                status = DeviceStatus.DEGRADED
        else:
            status = DeviceStatus.ONLINE
        
        return HealthCheckResult(
            device_id=device.id,
            timestamp=timestamp,
            ping_ok=ping_ok,
            ping_latency_ms=latency,
            ports_checked=device.ports_to_monitor,
            ports_open=ports_open,
            ports_closed=ports_closed,
            status=status
        )
    
    async def _ping(self, host: str, timeout: float = 3.0) -> tuple:
        """Simple ping check using socket connection"""
        try:
            start = time.time()
            # Try to connect to port 80 or 443 as ping alternative
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            result = await asyncio.to_thread(
                sock.connect_ex, (host, 80)
            )
            latency = (time.time() - start) * 1000
            sock.close()
            
            if result == 0:
                return True, latency
            
            # Try 443
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = await asyncio.to_thread(
                sock.connect_ex, (host, 443)
            )
            latency = (time.time() - start) * 1000
            sock.close()
            
            if result == 0:
                return True, latency
            
            # Try ICMP-like with any open port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = await asyncio.to_thread(
                sock.connect_ex, (host, 22)
            )
            latency = (time.time() - start) * 1000
            sock.close()
            
            return result == 0, latency if result == 0 else -1
            
        except Exception as e:
            return False, -1
    
    async def _check_port(self, host: str, port: int, timeout: float = 2.0) -> bool:
        """Check if a specific port is open"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = await asyncio.to_thread(
                sock.connect_ex, (host, port)
            )
            sock.close()
            return result == 0
        except Exception:
            return False
    
    async def _trigger_alert(self, device: NetworkDevice, severity: str, message: str):
        """Trigger an alert"""
        if self._alert_callback:
            try:
                if asyncio.iscoroutinefunction(self._alert_callback):
                    await self._alert_callback(device, severity, message)
                else:
                    self._alert_callback(device, severity, message)
            except Exception as e:
                print(f"Alert callback error: {e}")
    
    async def check_now(self, device_id: str) -> Optional[HealthCheckResult]:
        """Immediately check a specific device"""
        device = infrastructure.get_device(device_id)
        if not device:
            return None
        
        result = await self._perform_health_check(device)
        device.update_status(result)
        self._check_results[device_id] = result
        
        return result
    
    async def check_all_now(self) -> Dict[str, HealthCheckResult]:
        """Check all devices immediately"""
        results = {}
        devices = infrastructure.list_devices()
        
        tasks = []
        for device in devices:
            if device.enabled:
                tasks.append(self._check_and_store(device))
        
        await asyncio.gather(*tasks)
        return self._check_results.copy()
    
    async def _check_and_store(self, device: NetworkDevice):
        """Check device and store result"""
        result = await self._perform_health_check(device)
        device.update_status(result)
        self._check_results[device.id] = result
    
    def get_last_result(self, device_id: str) -> Optional[HealthCheckResult]:
        """Get last check result for a device"""
        return self._check_results.get(device_id)
    
    def get_all_results(self) -> Dict[str, HealthCheckResult]:
        """Get all last check results"""
        return self._check_results.copy()


# Singleton instance
scheduler = MonitoringScheduler()
