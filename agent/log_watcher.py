"""
Log Watcher Service with Autonomous Remediation

Background service that periodically reads logs from network devices,
detects anomalies (errors, interface flaps, auth failures, etc.),
creates alerts, and triggers the agent to investigate AND remediate.

Inspired by OpenClaw's autonomous workflow execution pattern.
"""
import asyncio
import re
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from agent.logging_config import get_logger

logger = get_logger("log_watcher")


# ============= ANOMALY PATTERNS =============

@dataclass
class AnomalyPattern:
    """A pattern to detect anomalies in device logs"""
    name: str
    pattern: str  # regex pattern
    severity: str  # info, warning, critical
    description: str
    compiled: re.Pattern = field(init=False, repr=False)
    
    def __post_init__(self):
        self.compiled = re.compile(self.pattern, re.IGNORECASE)


# Built-in anomaly patterns for common network issues
DEFAULT_PATTERNS = [
    # Link / Interface issues
    AnomalyPattern(
        name="link_down",
        pattern=r"(link.*(down|fail)|interface.*changed state to down|%LINK-\d+-\w*DOWN|line protocol.*down|ether\d+.*link down)",
        severity="critical",
        description="Network interface link down detected"
    ),
    AnomalyPattern(
        name="link_flap",
        pattern=r"(link.*(up.*down|down.*up|flap)|%LINK-\d+-UPDOWN|interface.*flapping)",
        severity="warning",
        description="Interface link flapping detected"
    ),
    # Authentication / Security
    AnomalyPattern(
        name="auth_failure",
        pattern=r"(auth(entication)?\s*(fail|error|denied)|login\s*(fail|invalid|denied)|%SEC-\d+-\w*FAIL|invalid (user|password|credentials)|access.denied)",
        severity="critical",
        description="Authentication failure detected"
    ),
    # System errors
    AnomalyPattern(
        name="system_error",
        pattern=r"(%SYS-\d+-\w*ERROR|system\s*error|kernel\s*panic|segfault|out of memory|critical\s*error)",
        severity="critical",
        description="System error detected"
    ),
    AnomalyPattern(
        name="system_warning",
        pattern=r"(%SYS-\d+-\w*WARNING|high (cpu|memory|temperature)|resource.*(limit|exhaust)|disk.*(full|space))",
        severity="warning",
        description="System warning detected"
    ),
    # Routing
    AnomalyPattern(
        name="routing_change",
        pattern=r"(%OSPF-\d+-ADJCHG|neighbor.*down|bgp.*(down|reset|notification)|routing.*change|adjacency.*lost)",
        severity="warning",
        description="Routing adjacency change detected"
    ),
    # Spanning Tree
    AnomalyPattern(
        name="stp_change",
        pattern=r"(spanning.tree.*(topology change|tcn|root change)|%SPANTREE-\d+|stp.*block)",
        severity="warning",
        description="Spanning tree topology change detected"
    ),
    # Hardware
    AnomalyPattern(
        name="hardware_issue",
        pattern=r"(fan\s*(fail|error)|power\s*supply.*(fail|error)|temperature.*(critical|high|alarm)|%PLATFORM-\d+-\w*(FAIL|ERROR))",
        severity="critical",
        description="Hardware issue detected"
    ),
]


# ============= REMEDIATION RUNBOOKS =============

REMEDIATION_RUNBOOKS = {
    "link_down": {
        "severity_threshold": "critical",
        "prompt": (
            "Interface link down terdeteksi. Lakukan langkah-langkah berikut:\n"
            "1. Ping device untuk memastikan reachability\n"
            "2. Cek status semua interface\n"
            "3. Analisis penyebab (kabel, config, atau hardware)\n"
            "4. Jika interface bisa di-enable kembali, AJUKAN konfirmasi ke user\n"
            "5. Jika hardware issue, buat alert dan rekomendasikan tindakan fisik"
        ),
        "auto_actions": ["ping", "get_interfaces"],
        "requires_confirmation": ["enable_local_interface", "enable_remote_interface"],
    },
    "link_flap": {
        "severity_threshold": "warning",
        "prompt": (
            "Interface flapping terdeteksi (naik-turun berulang). Lakukan:\n"
            "1. Ping device untuk cek stabilitas\n"
            "2. Cek interface statistics (errors, CRC, collisions)\n"
            "3. Cek connections dari/ke device\n"
            "4. Analisis pola flapping dan kemungkinan penyebab\n"
            "5. Jika error count tinggi, rekomendasikan disable/re-enable interface (dengan konfirmasi)"
        ),
        "auto_actions": ["ping", "get_interfaces", "get_connections"],
        "requires_confirmation": ["disable_local_interface", "enable_local_interface"],
    },
    "auth_failure": {
        "severity_threshold": "critical",
        "prompt": (
            "Authentication failure terdeteksi. Lakukan:\n"
            "1. Cek koneksi aktif untuk identifikasi sumber serangan\n"
            "2. Analisis pola: brute force, credential expired, atau misconfiguration\n"
            "3. Rekomendasikan tindakan keamanan (block IP, update credential)\n"
            "4. JANGAN melakukan perubahan keamanan tanpa konfirmasi user"
        ),
        "auto_actions": ["get_connections", "ping"],
        "requires_confirmation": [],
    },
    "system_error": {
        "severity_threshold": "critical",
        "prompt": (
            "System error terdeteksi. Lakukan:\n"
            "1. Ping device untuk cek apakah masih reachable\n"
            "2. Cek interface status\n"
            "3. Jika device unreachable, buat alert critical\n"
            "4. Dokumentasikan error untuk troubleshooting lebih lanjut"
        ),
        "auto_actions": ["ping", "get_interfaces"],
        "requires_confirmation": [],
    },
    "system_warning": {
        "severity_threshold": "warning",
        "prompt": (
            "System warning (high CPU/memory/temperature). Lakukan:\n"
            "1. Cek bandwidth untuk identifikasi traffic spike\n"
            "2. Cek connections untuk identifikasi beban abnormal\n"
            "3. Rekomendasikan langkah optimasi atau restart service"
        ),
        "auto_actions": ["get_bandwidth_stats", "get_connections"],
        "requires_confirmation": [],
    },
    "routing_change": {
        "severity_threshold": "warning",
        "prompt": (
            "Routing adjacency change terdeteksi (OSPF/BGP neighbor down). Lakukan:\n"
            "1. Ping neighbor device\n"
            "2. Traceroute untuk identifikasi path\n"
            "3. Cek interface ke arah neighbor\n"
            "4. Analisis penyebab dan dampak terhadap routing"
        ),
        "auto_actions": ["ping", "get_interfaces"],
        "requires_confirmation": [],
    },
    "hardware_issue": {
        "severity_threshold": "critical",
        "prompt": (
            "Hardware issue terdeteksi (fan/PSU/temperature). Lakukan:\n"
            "1. Ping device untuk cek reachability\n"
            "2. Buat alert critical\n"
            "3. Rekomendasikan pengecekan fisik SEGERA\n"
            "4. JANGAN melakukan shutdown atau restart tanpa konfirmasi"
        ),
        "auto_actions": ["ping"],
        "requires_confirmation": [],
    },
}


@dataclass
class DetectedAnomaly:
    """An anomaly detected in device logs"""
    id: str
    device_ip: str
    device_name: str
    pattern_name: str
    severity: str
    description: str
    log_line: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    investigated: bool = False
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_ip": self.device_ip,
            "device_name": self.device_name,
            "pattern_name": self.pattern_name,
            "severity": self.severity,
            "description": self.description,
            "log_line": self.log_line,
            "timestamp": self.timestamp,
            "investigated": self.investigated,
        }


@dataclass
class DeviceWatchConfig:
    """Per-device log watch configuration"""
    device_ip: str
    enabled: bool = True
    interval_seconds: int = 60
    auto_trigger_agent: bool = True
    auto_remediate: bool = True  # Enable autonomous remediation
    last_check: float = 0.0
    last_log_hash: str = ""
    last_log_lines: List[str] = field(default_factory=list)


# ============= LOG WATCHER SERVICE =============

class LogWatcher:
    """
    Background service for automated device log monitoring.
    
    Features:
    - Periodic log polling via SSH (unified_commands.get_logs)
    - Diff tracking — only processes new log lines
    - Anomaly detection with regex patterns
    - Alert creation via alert_manager
    - Optional agent auto-trigger for investigation
    """
    
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._devices: Dict[str, DeviceWatchConfig] = {}
        self._patterns: List[AnomalyPattern] = list(DEFAULT_PATTERNS)
        self._anomalies: List[DetectedAnomaly] = []
        self._investigations: List[dict] = []  # auto-triggered agent investigations
        self._remediation_history: List[dict] = []  # remediation action history
        self._anomaly_counter = 0
        self._default_interval = 60
        self._auto_trigger = True
        self._agent_callback: Optional[Callable] = None
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def set_agent_callback(self, callback: Callable):
        """Set callback to trigger agent when anomaly is detected.
        
        Callback signature: async def callback(message: str, thread_id: str)
        """
        self._agent_callback = callback
    
    def add_device(self, device_ip: str, interval: int = None, auto_trigger: bool = None):
        """Add or update a device for log watching"""
        if device_ip in self._devices:
            config = self._devices[device_ip]
            if interval is not None:
                config.interval_seconds = interval
            if auto_trigger is not None:
                config.auto_trigger_agent = auto_trigger
            config.enabled = True
        else:
            self._devices[device_ip] = DeviceWatchConfig(
                device_ip=device_ip,
                interval_seconds=interval or self._default_interval,
                auto_trigger_agent=auto_trigger if auto_trigger is not None else self._auto_trigger
            )
    
    def remove_device(self, device_ip: str):
        """Remove a device from log watching"""
        self._devices.pop(device_ip, None)
    
    def add_pattern(self, name: str, pattern: str, severity: str = "warning", description: str = ""):
        """Add a custom anomaly pattern"""
        self._patterns.append(AnomalyPattern(
            name=name,
            pattern=pattern,
            severity=severity,
            description=description or f"Custom pattern: {name}"
        ))
    
    async def start(self, device_ips: List[str] = None):
        """Start the log watcher.
        
        Args:
            device_ips: Optional list of device IPs to watch. 
                        If None, watches all inventory devices.
        """
        if self._running:
            return
        
        # Auto-discover devices from inventory if none specified
        if not self._devices or device_ips:
            try:
                from modules.inventory import inventory
                devices = inventory.list_devices()
                target_ips = device_ips or [d.ip_address for d in devices]
                for ip in target_ips:
                    if ip not in self._devices:
                        self.add_device(ip)
            except Exception as e:
                logger.warning(f"Could not auto-discover devices: {e}")
        
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(f"🔍 Log watcher started — monitoring {len(self._devices)} devices")
    
    async def stop(self):
        """Stop the log watcher"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️ Log watcher stopped")
    
    async def _watch_loop(self):
        """Main log watching loop"""
        while self._running:
            now = time.time()
            
            for ip, config in list(self._devices.items()):
                if not config.enabled:
                    continue
                
                if now - config.last_check >= config.interval_seconds:
                    asyncio.create_task(self._check_device_logs(ip, config))
                    config.last_check = now
            
            # Sleep before next iteration
            await asyncio.sleep(5)
    
    async def _check_device_logs(self, device_ip: str, config: DeviceWatchConfig):
        """Fetch and analyze logs from a single device"""
        try:
            from tools.unified_commands import unified_commands
            
            result = await unified_commands.get_logs(device_ip)
            
            if not result.success:
                logger.debug(f"Failed to get logs from {device_ip}: {result.error}")
                return
            
            # Get log lines
            log_lines = result.data.get("logs", [])
            if not log_lines:
                return
            
            # Diff: only process new lines
            new_lines = self._get_new_lines(config, log_lines)
            if not new_lines:
                return
            
            # Update stored log lines
            config.last_log_lines = log_lines
            
            # Check each new line for anomalies
            device_name = result.device_name or device_ip
            for line in new_lines:
                await self._check_line_for_anomalies(device_ip, device_name, line, config)
                
        except Exception as e:
            logger.error(f"Error checking logs for {device_ip}: {e}")
    
    def _get_new_lines(self, config: DeviceWatchConfig, current_lines: List[str]) -> List[str]:
        """Get lines that are new since last check"""
        if not config.last_log_lines:
            # First run — store all but don't process to avoid false positives
            config.last_log_lines = current_lines
            return []
        
        # Find new lines by comparing with previous
        old_set = set(config.last_log_lines)
        new_lines = [line for line in current_lines if line.strip() and line not in old_set]
        
        return new_lines
    
    async def _check_line_for_anomalies(
        self, device_ip: str, device_name: str, 
        line: str, config: DeviceWatchConfig
    ):
        """Check a single log line against all anomaly patterns"""
        for pattern in self._patterns:
            if pattern.compiled.search(line):
                anomaly = await self._create_anomaly(
                    device_ip=device_ip,
                    device_name=device_name,
                    pattern=pattern,
                    log_line=line
                )
                
                # Trigger agent if configured
                if config.auto_trigger_agent and self._agent_callback:
                    await self._trigger_agent(anomaly)
                
                # Only match first pattern per line
                break
    
    async def _create_anomaly(
        self, device_ip: str, device_name: str,
        pattern: AnomalyPattern, log_line: str
    ) -> DetectedAnomaly:
        """Create an anomaly record and alert"""
        self._anomaly_counter += 1
        anomaly_id = f"anom_{self._anomaly_counter:06d}"
        
        anomaly = DetectedAnomaly(
            id=anomaly_id,
            device_ip=device_ip,
            device_name=device_name,
            pattern_name=pattern.name,
            severity=pattern.severity,
            description=pattern.description,
            log_line=log_line.strip()
        )
        
        self._anomalies.append(anomaly)
        
        # Keep only last 200 anomalies
        if len(self._anomalies) > 200:
            self._anomalies = self._anomalies[-200:]
        
        logger.warning(
            f"🚨 Anomaly [{pattern.severity}] on {device_name} ({device_ip}): "
            f"{pattern.description} — {log_line.strip()[:100]}"
        )
        
        # Create alert
        try:
            from agent.alerting import alert_manager
            await alert_manager.create_alert(
                device_id=device_ip,
                device_name=device_name,
                device_ip=device_ip,
                severity=pattern.severity,
                message=f"[Log Anomaly] {pattern.description}: {log_line.strip()[:200]}"
            )
        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
        
        return anomaly
    
    async def _trigger_agent(self, anomaly: DetectedAnomaly):
        """Trigger the agent to investigate AND remediate an anomaly.
        
        If a remediation runbook exists for the anomaly pattern,
        the agent is given specific instructions to diagnose and fix.
        Low-risk actions are auto-executed; high-risk require user confirmation.
        """
        # Look up remediation runbook
        runbook = REMEDIATION_RUNBOOKS.get(anomaly.pattern_name)
        device_config = self._devices.get(anomaly.device_ip)
        use_remediation = (
            runbook is not None and 
            device_config is not None and 
            device_config.auto_remediate
        )
        
        if use_remediation:
            # Build remediation-aware prompt
            message = (
                f"[AUTO-REMEDIATION] Anomali terdeteksi pada device {anomaly.device_name} ({anomaly.device_ip}).\n"
                f"Severity: {anomaly.severity}\n"
                f"Tipe: {anomaly.description}\n"
                f"Log: {anomaly.log_line}\n\n"
                f"=== RUNBOOK REMEDIASI ===\n"
                f"{runbook['prompt']}\n\n"
                f"Instruksi tambahan:\n"
                f"- Gunakan tools berikut untuk investigasi awal: {', '.join(runbook['auto_actions'])}\n"
            )
            if runbook['requires_confirmation']:
                message += (
                    f"- Aksi yang MEMERLUKAN konfirmasi user: {', '.join(runbook['requires_confirmation'])}\n"
                    f"- JANGAN skip konfirmasi untuk aksi high-risk\n"
                )
            message += (
                f"\nSetelah investigasi dan remediasi, simpan hasilnya ke memory "
                f"dengan save_diagnostic_result jika tool tersedia."
            )
            mode = "remediation"
        else:
            # Investigation-only prompt (original behavior)
            message = (
                f"[AUTO-MONITOR] Anomali terdeteksi pada device {anomaly.device_name} ({anomaly.device_ip}).\n"
                f"Severity: {anomaly.severity}\n"
                f"Tipe: {anomaly.description}\n"
                f"Log: {anomaly.log_line}\n\n"
                f"Lakukan investigasi singkat: cek status device (ping), cek interface, "
                f"dan berikan analisis penyebab serta rekomendasi."
            )
            mode = "investigation"
        
        thread_id = f"logwatch-{int(time.time())}-{anomaly.id}"
        
        try:
            from agent.langgraph_agent import network_agent
            response = await network_agent.ainvoke(message, thread_id)
            anomaly.investigated = True
            
            # Store investigation for frontend polling
            investigation = {
                "id": anomaly.id,
                "thread_id": thread_id,
                "device_ip": anomaly.device_ip,
                "device_name": anomaly.device_name,
                "severity": anomaly.severity,
                "pattern": anomaly.pattern_name,
                "description": anomaly.description,
                "log_line": anomaly.log_line,
                "agent_response": response,
                "timestamp": anomaly.timestamp,
                "mode": mode,  # "investigation" or "remediation"
                "runbook_used": anomaly.pattern_name if use_remediation else None,
                "seen": False,
            }
            self._investigations.append(investigation)
            
            # Record remediation in history
            if use_remediation:
                self._remediation_history.append({
                    "anomaly_id": anomaly.id,
                    "device_ip": anomaly.device_ip,
                    "pattern": anomaly.pattern_name,
                    "runbook": anomaly.pattern_name,
                    "agent_response": response[:500],  # truncate for storage
                    "timestamp": anomaly.timestamp,
                })
                # Keep max 100 remediation records
                if len(self._remediation_history) > 100:
                    self._remediation_history = self._remediation_history[-100:]
            
            # Keep max 50 investigations
            if len(self._investigations) > 50:
                self._investigations = self._investigations[-50:]
            
            logger.info(
                f"🤖 Agent {mode} for anomaly {anomaly.id} in thread {thread_id}"
            )
        except Exception as e:
            logger.error(f"Failed to trigger agent for {anomaly.id}: {e}")
    
    # ============= STATUS & QUERIES =============
    
    def get_status(self) -> dict:
        """Get log watcher status"""
        return {
            "running": self._running,
            "devices_watched": len([d for d in self._devices.values() if d.enabled]),
            "total_devices": len(self._devices),
            "patterns_loaded": len(self._patterns),
            "total_anomalies": len(self._anomalies),
            "recent_anomalies": len([
                a for a in self._anomalies 
                if (datetime.now() - datetime.fromisoformat(a.timestamp)).total_seconds() < 3600
            ]),
            "devices": {
                ip: {
                    "enabled": cfg.enabled,
                    "interval": cfg.interval_seconds,
                    "auto_trigger": cfg.auto_trigger_agent,
                    "last_check": datetime.fromtimestamp(cfg.last_check).isoformat() if cfg.last_check > 0 else "never"
                }
                for ip, cfg in self._devices.items()
            }
        }
    
    def get_anomalies(self, device_ip: str = None, severity: str = None, limit: int = 20) -> List[dict]:
        """Get recent anomalies with optional filtering"""
        results = self._anomalies.copy()
        
        if device_ip:
            results = [a for a in results if a.device_ip == device_ip]
        if severity:
            results = [a for a in results if a.severity == severity]
        
        return [a.to_dict() for a in results[-limit:]]
    
    def get_patterns(self) -> List[dict]:
        """Get all anomaly patterns"""
        return [
            {"name": p.name, "pattern": p.pattern, "severity": p.severity, "description": p.description}
            for p in self._patterns
        ]
    
    def get_investigations(self, unseen_only: bool = False) -> List[dict]:
        """Get agent investigations triggered by anomalies"""
        if unseen_only:
            return [i for i in self._investigations if not i["seen"]]
        return list(self._investigations)
    
    def mark_investigation_seen(self, investigation_id: str):
        """Mark an investigation as seen by the frontend"""
        for inv in self._investigations:
            if inv["id"] == investigation_id:
                inv["seen"] = True
                break


# Singleton instance
log_watcher = LogWatcher()
