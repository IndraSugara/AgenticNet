"""
Monitoring & Observability Module

Features:
- Real-time system metrics collection (CPU, RAM, Disk, Network)
- Telemetry data analysis
- Traffic anomaly detection
- Performance bottleneck identification
- Predictive failure analysis
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import logging
import threading
import time
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger("monitoring")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not installed. System metrics collection disabled.")


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MetricPoint:
    """Single metric data point"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""


@dataclass
class Alert:
    """Alert from monitoring"""
    severity: AlertSeverity
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }


@dataclass
class InterfaceMetrics:
    """Network interface metrics"""
    name: str
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    errin: int = 0
    errout: int = 0
    dropin: int = 0
    dropout: int = 0
    speed: int = 0  # Mbps
    mtu: int = 0
    is_up: bool = False
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "bytes_sent": self.bytes_sent,
            "bytes_recv": self.bytes_recv,
            "bytes_sent_mb": round(self.bytes_sent / (1024 * 1024), 2),
            "bytes_recv_mb": round(self.bytes_recv / (1024 * 1024), 2),
            "packets_sent": self.packets_sent,
            "packets_recv": self.packets_recv,
            "errin": self.errin,
            "errout": self.errout,
            "dropin": self.dropin,
            "dropout": self.dropout,
            "speed": self.speed,
            "mtu": self.mtu,
            "is_up": self.is_up,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class SystemMetrics:
    """Current system metrics snapshot"""
    cpu_percent: float = 0.0
    cpu_count: int = 0
    cpu_per_core: List[float] = field(default_factory=list)
    memory_total_gb: float = 0.0
    memory_used_gb: float = 0.0
    memory_available_gb: float = 0.0
    memory_cached_gb: float = 0.0
    memory_percent: float = 0.0
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_percent: float = 0.0
    disk_read_mb: float = 0.0
    disk_write_mb: float = 0.0
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    boot_time: str = ""
    uptime_hours: float = 0.0
    process_count: int = 0
    load_average: List[float] = field(default_factory=list)
    temperatures: Dict[str, float] = field(default_factory=dict)
    interfaces: List[InterfaceMetrics] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "cpu": {
                "percent": self.cpu_percent,
                "count": self.cpu_count,
                "per_core": self.cpu_per_core
            },
            "memory": {
                "total_gb": round(self.memory_total_gb, 2),
                "used_gb": round(self.memory_used_gb, 2),
                "available_gb": round(self.memory_available_gb, 2),
                "cached_gb": round(self.memory_cached_gb, 2),
                "percent": self.memory_percent
            },
            "disk": {
                "total_gb": round(self.disk_total_gb, 2),
                "used_gb": round(self.disk_used_gb, 2),
                "percent": self.disk_percent,
                "read_mb": round(self.disk_read_mb, 2),
                "write_mb": round(self.disk_write_mb, 2)
            },
            "network": {
                "bytes_sent": self.network_bytes_sent,
                "bytes_recv": self.network_bytes_recv,
                "bytes_sent_mb": round(self.network_bytes_sent / (1024 * 1024), 2),
                "bytes_recv_mb": round(self.network_bytes_recv / (1024 * 1024), 2)
            },
            "uptime_hours": round(self.uptime_hours, 2),
            "process_count": self.process_count,
            "load_average": self.load_average,
            "temperatures": self.temperatures,
            "interfaces": [iface.to_dict() for iface in self.interfaces],
            "timestamp": self.timestamp.isoformat()
        }


class MonitoringModule:
    """
    Monitoring and Observability Module
    
    Capabilities:
    - Collect real-time system metrics
    - Analyze telemetry data
    - Detect anomalies
    - Identify bottlenecks
    - Predict potential failures
    - Distinguish signal from noise
    """
    
    def __init__(self):
        self.metrics_history: List[MetricPoint] = []
        self.alerts: List[Alert] = []
        self.thresholds: Dict[str, Dict[str, float]] = {
            "cpu_usage": {"warning": 70, "critical": 90},
            "memory_usage": {"warning": 80, "critical": 95},
            "disk_usage": {"warning": 80, "critical": 90},
            "latency_ms": {"warning": 100, "critical": 500},
            "packet_loss": {"warning": 1, "critical": 5},
            "error_rate": {"warning": 1, "critical": 5}
        }
        self._current_metrics: Optional[SystemMetrics] = None
        self._current_network_metrics: Dict[str, Any] = {"latency": [], "bandwidth": {}}
        self._collection_running = False
        self._collection_thread: Optional[threading.Thread] = None
        self._collection_interval = 10  # seconds
        self._db_path = "data/metrics.db"
        self._prev_disk_io: Optional[Any] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._db_lock = threading.Lock()
        self._safe_init_database()
        
    def _safe_init_database(self):
        """Initialize database, auto-recreate if corrupted"""
        try:
            self._init_database()
        except Exception as e:
            logger.warning(f"metrics.db error ({e}), recreating...")
            try:
                # Close existing connection if any
                if self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None
                # Remove corrupt file
                db_file = Path(self._db_path)
                if db_file.exists():
                    db_file.unlink()
                    logger.info("Removed corrupt metrics.db")
                # Retry init
                self._init_database()
                logger.info("metrics.db recreated successfully")
            except Exception as e2:
                logger.error(f"Failed to recreate metrics.db: {e2}")

    def update_network_metrics(self, latency=None, bandwidth=None):
        """Update cached network metrics"""
        if latency is not None:
            self._current_network_metrics["latency"] = latency
        if bandwidth is not None:
            self._current_network_metrics["bandwidth"] = bandwidth
            
    def get_network_metrics(self) -> Dict[str, Any]:
        """Get cached network metrics"""
        return self._current_network_metrics
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a shared SQLite connection with WAL mode"""
        os.makedirs("data", exist_ok=True)
        if self._conn is None:
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                timeout=10
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn
    
    def _init_database(self):
        """Initialize SQLite database for metrics storage"""
        with self._db_lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics_raw (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT,
                    labels TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_metric_time
                ON metrics_raw(metric_name, timestamp)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics_5min (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    avg_value REAL NOT NULL,
                    min_value REAL NOT NULL,
                    max_value REAL NOT NULL,
                    unit TEXT,
                    labels TEXT,
                    timestamp DATETIME NOT NULL
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_metric_time_5min
                ON metrics_5min(metric_name, timestamp)
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS interface_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interface_name TEXT NOT NULL,
                    bytes_sent INTEGER,
                    bytes_recv INTEGER,
                    packets_sent INTEGER,
                    packets_recv INTEGER,
                    errors_in INTEGER,
                    errors_out INTEGER,
                    drops_in INTEGER,
                    drops_out INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_interface_time
                ON interface_metrics(interface_name, timestamp)
            """)

            conn.commit()
    
    def collect_system_metrics(self) -> Optional[SystemMetrics]:
        """
        Collect current system metrics using psutil
        
        Returns:
            SystemMetrics object with current values
        """
        if not PSUTIL_AVAILABLE:
            return None
        
        try:
            # CPU - overall and per-core
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            
            # Memory - detailed breakdown
            memory = psutil.virtual_memory()
            memory_total_gb = memory.total / (1024 ** 3)
            memory_used_gb = memory.used / (1024 ** 3)
            memory_available_gb = memory.available / (1024 ** 3)
            memory_percent = memory.percent
            
            # Try to get cached memory (platform specific)
            memory_cached_gb = 0.0
            try:
                if hasattr(memory, 'cached'):
                    memory_cached_gb = memory.cached / (1024 ** 3)
                elif hasattr(memory, 'buffers'):
                    memory_cached_gb = memory.buffers / (1024 ** 3)
            except Exception:
                pass
            
            # Disk - usage and I/O
            disk = psutil.disk_usage('/')
            disk_total_gb = disk.total / (1024 ** 3)
            disk_used_gb = disk.used / (1024 ** 3)
            disk_percent = disk.percent
            
            # Disk I/O
            disk_read_mb = 0.0
            disk_write_mb = 0.0
            try:
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    # Calculate rate if we have previous data
                    if self._prev_disk_io:
                        read_diff = disk_io.read_bytes - self._prev_disk_io.read_bytes
                        write_diff = disk_io.write_bytes - self._prev_disk_io.write_bytes
                        disk_read_mb = read_diff / (1024 * 1024)
                        disk_write_mb = write_diff / (1024 * 1024)
                    self._prev_disk_io = disk_io
            except Exception:
                pass
            
            # Network - total counters
            net_io = psutil.net_io_counters()
            bytes_sent = net_io.bytes_sent
            bytes_recv = net_io.bytes_recv
            
            # Process count
            process_count = len(psutil.pids())
            
            # Load average (Unix-like systems only)
            load_average = []
            try:
                if hasattr(os, 'getloadavg'):
                    load_average = list(os.getloadavg())
            except Exception:
                pass
            
            # Temperature sensors (if available)
            temperatures = {}
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        if entries:
                            avg_temp = sum(e.current for e in entries) / len(entries)
                            temperatures[name] = round(avg_temp, 1)
            except Exception:
                pass
            
            # Per-interface metrics
            interfaces = []
            try:
                net_if_addrs = psutil.net_if_addrs()
                net_if_stats = psutil.net_if_stats()
                net_io_per_if = psutil.net_io_counters(pernic=True)
                
                for iface_name in net_if_addrs.keys():
                    if iface_name in net_io_per_if:
                        io = net_io_per_if[iface_name]
                        stats = net_if_stats.get(iface_name)
                        
                        iface_metrics = InterfaceMetrics(
                            name=iface_name,
                            bytes_sent=io.bytes_sent,
                            bytes_recv=io.bytes_recv,
                            packets_sent=io.packets_sent,
                            packets_recv=io.packets_recv,
                            errin=io.errin,
                            errout=io.errout,
                            dropin=io.dropin,
                            dropout=io.dropout,
                            speed=stats.speed if stats else 0,
                            mtu=stats.mtu if stats else 0,
                            is_up=stats.isup if stats else False,
                            timestamp=datetime.now()
                        )
                        interfaces.append(iface_metrics)
                        
                        # Store interface metrics to database
                        self._store_interface_metrics(iface_metrics)
            except Exception as e:
                logger.warning(f"Could not collect interface metrics: {e}")
            
            # Uptime
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime_hours = (datetime.now() - boot_time).total_seconds() / 3600
            
            metrics = SystemMetrics(
                cpu_percent=cpu_percent,
                cpu_count=cpu_count,
                cpu_per_core=cpu_per_core,
                memory_total_gb=memory_total_gb,
                memory_used_gb=memory_used_gb,
                memory_available_gb=memory_available_gb,
                memory_cached_gb=memory_cached_gb,
                memory_percent=memory_percent,
                disk_total_gb=disk_total_gb,
                disk_used_gb=disk_used_gb,
                disk_percent=disk_percent,
                disk_read_mb=disk_read_mb,
                disk_write_mb=disk_write_mb,
                network_bytes_sent=bytes_sent,
                network_bytes_recv=bytes_recv,
                boot_time=boot_time.isoformat(),
                uptime_hours=uptime_hours,
                process_count=process_count,
                load_average=load_average,
                temperatures=temperatures,
                interfaces=interfaces,
                timestamp=datetime.now()
            )
            
            self._current_metrics = metrics
            
            # Ingest as metric points for trend analysis
            self._ingest_system_metrics(metrics)
            
            # Store to database
            self._store_metrics_to_db(metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return None
    
    def _ingest_system_metrics(self, metrics: SystemMetrics):
        """Ingest system metrics as individual metric points"""
        now = datetime.now()
        
        points = [
            MetricPoint(name="cpu_usage", value=metrics.cpu_percent, timestamp=now, unit="%"),
            MetricPoint(name="memory_usage", value=metrics.memory_percent, timestamp=now, unit="%"),
            MetricPoint(name="disk_usage", value=metrics.disk_percent, timestamp=now, unit="%"),
        ]
        
        for point in points:
            self.ingest_metric(point)
    
    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """Get the most recent system metrics"""
        if self._current_metrics is None:
            self.collect_system_metrics()
        return self._current_metrics
    
    def start_collection(self, interval: int = 10):
        """
        Start background metrics collection
        
        Args:
            interval: Collection interval in seconds
        """
        if self._collection_running:
            return
        
        self._collection_interval = interval
        self._collection_running = True
        
        def collection_loop():
            while self._collection_running:
                self.collect_system_metrics()
                time.sleep(self._collection_interval)
        
        self._collection_thread = threading.Thread(target=collection_loop, daemon=True)
        self._collection_thread.start()
        logger.info(f"Started metrics collection (every {interval}s)")
    
    def stop_collection(self):
        """Stop background metrics collection"""
        self._collection_running = False
        if self._collection_thread:
            self._collection_thread.join(timeout=2)
        logger.info("Stopped metrics collection")
    
    def ingest_metric(self, metric: MetricPoint) -> Optional[Alert]:
        """
        Ingest a metric and check for threshold violations
        """
        self.metrics_history.append(metric)
        
        # Keep only last 1000 metrics to prevent memory bloat
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]
        
        # Check thresholds
        if metric.name in self.thresholds:
            thresholds = self.thresholds[metric.name]
            
            if metric.value >= thresholds.get("critical", float('inf')):
                alert = Alert(
                    severity=AlertSeverity.CRITICAL,
                    message=f"{metric.name} critical: {metric.value:.1f}%",
                    source="threshold_check",
                    details={"metric": metric.name, "value": metric.value}
                )
                self.alerts.append(alert)
                return alert
            
            elif metric.value >= thresholds.get("warning", float('inf')):
                alert = Alert(
                    severity=AlertSeverity.WARNING,
                    message=f"{metric.name} warning: {metric.value:.1f}%",
                    source="threshold_check",
                    details={"metric": metric.name, "value": metric.value}
                )
                self.alerts.append(alert)
                return alert
        
        return None
    
    def analyze_trend(self, metric_name: str, window_size: int = 10) -> Dict[str, Any]:
        """
        Analyze trend for a specific metric
        
        Returns:
            Dict with trend analysis (direction, rate of change, prediction)
        """
        # Filter metrics by name
        relevant = [m for m in self.metrics_history if m.name == metric_name][-window_size:]
        
        if len(relevant) < 2:
            return {"status": "insufficient_data", "message": "Need more data points"}
        
        values = [m.value for m in relevant]
        
        # Calculate basic trend
        avg = sum(values) / len(values)
        first_half_avg = sum(values[:len(values)//2]) / (len(values)//2)
        second_half_avg = sum(values[len(values)//2:]) / (len(values) - len(values)//2)
        
        if second_half_avg > first_half_avg * 1.1:
            direction = "increasing"
        elif second_half_avg < first_half_avg * 0.9:
            direction = "decreasing"
        else:
            direction = "stable"
        
        return {
            "status": "analyzed",
            "metric": metric_name,
            "direction": direction,
            "average": round(avg, 2),
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "samples": len(values)
        }
    
    def detect_anomaly(self, metric: MetricPoint) -> Optional[Alert]:
        """
        Detect anomalies using simple statistical method
        
        Uses z-score based detection
        """
        relevant = [m for m in self.metrics_history if m.name == metric.name][-50:]
        
        if len(relevant) < 10:
            return None  # Not enough data
        
        values = [m.value for m in relevant]
        avg = sum(values) / len(values)
        variance = sum((x - avg) ** 2 for x in values) / len(values)
        std_dev = variance ** 0.5
        
        if std_dev == 0:
            return None
        
        z_score = abs(metric.value - avg) / std_dev
        
        if z_score > 3:  # 3 standard deviations
            alert = Alert(
                severity=AlertSeverity.WARNING,
                message=f"Anomaly detected in {metric.name}: {metric.value} (z-score: {z_score:.2f})",
                source="anomaly_detection",
                details={
                    "metric": metric.name,
                    "value": metric.value,
                    "average": avg,
                    "std_dev": std_dev,
                    "z_score": z_score
                }
            )
            self.alerts.append(alert)
            return alert
        
        return None
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary including system metrics"""
        recent_alerts = [a for a in self.alerts[-100:]]
        
        critical_count = sum(1 for a in recent_alerts if a.severity == AlertSeverity.CRITICAL)
        warning_count = sum(1 for a in recent_alerts if a.severity == AlertSeverity.WARNING)
        
        if critical_count > 0:
            status = "critical"
        elif warning_count > 5:
            status = "degraded"
        elif warning_count > 0:
            status = "warning"
        else:
            status = "healthy"
        
        result = {
            "status": status,
            "critical_alerts": critical_count,
            "warning_alerts": warning_count,
            "total_metrics": len(self.metrics_history),
            "recent_alerts": [a.to_dict() for a in recent_alerts[-5:]],
            "collection_active": self._collection_running
        }
        
        # Add current system metrics if available
        if self._current_metrics:
            result["system"] = self._current_metrics.to_dict()
        
        return result
    
    def format_for_agent(self) -> str:
        """Format monitoring data for agent context"""
        summary = self.get_health_summary()
        
        output = f"""
## 📊 Monitoring Status

**Overall Health:** {summary['status'].upper()}
**Critical Alerts:** {summary['critical_alerts']}
**Warning Alerts:** {summary['warning_alerts']}
**Total Metrics Collected:** {summary['total_metrics']}
"""
        
        # Add system metrics if available
        if "system" in summary:
            sys = summary["system"]
            output += f"""
### System Resources
- **CPU:** {sys['cpu']['percent']}% ({sys['cpu']['count']} cores)
- **Memory:** {sys['memory']['used_gb']} / {sys['memory']['total_gb']} GB ({sys['memory']['percent']}%)
- **Disk:** {sys['disk']['used_gb']} / {sys['disk']['total_gb']} GB ({sys['disk']['percent']}%)
- **Network:** ↑ {sys['network']['bytes_sent_mb']} MB / ↓ {sys['network']['bytes_recv_mb']} MB
- **Uptime:** {sys['uptime_hours']} hours
"""
        
        output += "\n### Recent Alerts\n"
        for alert in summary['recent_alerts']:
            output += f"- [{alert['severity'].upper()}] {alert['message']}\n"
        
        return output
    
    def _store_metrics_to_db(self, metrics: SystemMetrics):
        """Store system metrics to database using shared connection"""
        try:
            with self._db_lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                now = datetime.now().isoformat()

                rows = [
                    ("cpu_usage",    metrics.cpu_percent,  "%",  None, now),
                    ("memory_usage", metrics.memory_percent, "%", None, now),
                    ("disk_usage",   metrics.disk_percent,  "%",  None, now),
                    ("disk_read_mb", metrics.disk_read_mb,  "MB", None, now),
                    ("disk_write_mb",metrics.disk_write_mb, "MB", None, now),
                ]
                for i, core_pct in enumerate(metrics.cpu_per_core):
                    rows.append(("cpu_core_usage", core_pct, "%", f'{{"core":{i}}}', now))

                cursor.executemany(
                    "INSERT INTO metrics_raw (metric_name, value, unit, labels, timestamp) VALUES (?, ?, ?, ?, ?)",
                    rows
                )
                conn.commit()

            # Cleanup old data outside the write lock
            self._cleanup_old_metrics()
        except Exception as e:
            logger.warning(f"Could not store metrics to database: {e}")

    def _store_interface_metrics(self, iface: InterfaceMetrics):
        """Store interface metrics to database using shared connection"""
        try:
            with self._db_lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO interface_metrics
                    (interface_name, bytes_sent, bytes_recv, packets_sent, packets_recv,
                     errors_in, errors_out, drops_in, drops_out, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (iface.name, iface.bytes_sent, iface.bytes_recv, iface.packets_sent,
                      iface.packets_recv, iface.errin, iface.errout, iface.dropin,
                      iface.dropout, iface.timestamp.isoformat()))
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not store interface metrics: {e}")
    
    def _cleanup_old_metrics(self):
        """Delete metrics older than retention window"""
        try:
            with self._db_lock:
                conn = self._get_connection()
                cursor = conn.cursor()

                cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
                cursor.execute("DELETE FROM metrics_raw WHERE timestamp < ?", (cutoff,))
                cursor.execute("DELETE FROM interface_metrics WHERE timestamp < ?", (cutoff,))

                cutoff_30d = (datetime.now() - timedelta(days=30)).isoformat()
                cursor.execute("DELETE FROM metrics_5min WHERE timestamp < ?", (cutoff_30d,))

                conn.commit()
        except Exception as e:
            logger.warning(f"Could not cleanup old metrics: {e}")
    
    def get_metric_history(self, metric_name: str, hours: int = 1) -> List[Dict[str, Any]]:
        """Get historical data for a specific metric"""
        try:
            with self._db_lock:
                conn = self._get_connection()
                cursor = conn.cursor()
                cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
                cursor.execute("""
                    SELECT timestamp, value, unit FROM metrics_raw
                    WHERE metric_name = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                """, (metric_name, cutoff))
                rows = cursor.fetchall()
            return [{"timestamp": row[0], "value": row[1], "unit": row[2]} for row in rows]
        except Exception as e:
            print(f"Warning: Could not get metric history: {e}")
            return []
    
    def get_interface_history(self, interface_name: str, hours: int = 1) -> List[Dict[str, Any]]:
        """Get historical data for a specific network interface"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            cursor.execute("""
                SELECT timestamp, bytes_sent, bytes_recv, packets_sent, packets_recv,
                       errors_in, errors_out, drops_in, drops_out
                FROM interface_metrics 
                WHERE interface_name = ? AND timestamp >= ?
                ORDER BY timestamp ASC
            """, (interface_name, cutoff))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [{
                "timestamp": row[0],
                "bytes_sent": row[1],
                "bytes_recv": row[2],
                "packets_sent": row[3],
                "packets_recv": row[4],
                "errors_in": row[5],
                "errors_out": row[6],
                "drops_in": row[7],
                "drops_out": row[8]
            } for row in rows]
        except Exception as e:
            logger.warning(f"Could not get interface history: {e}")
            return []
    
    def get_interface_details(self, interface_name: str) -> Optional[Dict[str, Any]]:
        """Get current and historical details for a specific interface"""
        if not self._current_metrics:
            return None
        
        # Find current stats
        current = None
        for iface in self._current_metrics.interfaces:
            if iface.name == interface_name:
                current = iface.to_dict()
                break
        
        if not current:
            return None
        
        # Add historical data
        history = self.get_interface_history(interface_name, hours=1)
        current["history"] = history
        
        return current


# Singleton instance
monitoring = MonitoringModule()
