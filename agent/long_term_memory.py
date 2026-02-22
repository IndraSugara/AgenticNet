"""
Long-Term Memory Module — Network Intelligence

Enhanced memory for the agent:
- Solution caching for troubleshooting
- User preferences storage
- Learned patterns from past interactions
- Network event history (diagnostics, anomalies)
- Network baselines (learned "normal" per device/metric)

Inspired by OpenClaw's persistent and adaptive memory system.
"""
import os
import json
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class Solution:
    """A cached troubleshooting solution"""
    id: int
    problem: str
    solution: str
    category: str
    success_count: int
    last_used: str
    created_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "problem": self.problem,
            "solution": self.solution,
            "category": self.category,
            "success_count": self.success_count,
            "last_used": self.last_used,
            "created_at": self.created_at,
            "metadata": self.metadata
        }


@dataclass
class UserPreference:
    """A user preference setting"""
    key: str
    value: str
    updated_at: str


class LongTermMemory:
    """
    Long-term memory storage for the agent
    
    Features:
    - Solution caching with success tracking
    - User preferences
    - Learned patterns
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "data", 
                "long_term_memory.db"
            )
        
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection with threading support"""
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Solutions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS solutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem TEXT NOT NULL,
                solution TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                success_count INTEGER DEFAULT 1,
                last_used TEXT,
                created_at TEXT,
                metadata TEXT
            )
        """)
        
        # User preferences table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)
        
        # Learned patterns table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT,
                pattern_data TEXT,
                frequency INTEGER DEFAULT 1,
                last_seen TEXT,
                created_at TEXT
            )
        """)
        
        # Create FTS for solution search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS solutions_fts 
            USING fts5(problem, solution, category, content=solutions, content_rowid=id)
        """)
        
        # Network events table — records every significant network event
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS network_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_ip TEXT,
                event_type TEXT,
                event_data TEXT,
                severity TEXT DEFAULT 'info',
                source TEXT DEFAULT 'manual',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Network baselines — learned "normal" values per device/metric
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS network_baselines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_ip TEXT,
                metric_type TEXT,
                baseline_value REAL,
                threshold_low REAL,
                threshold_high REAL,
                sample_count INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(device_ip, metric_type)
            )
        """)
        
        conn.commit()
        conn.close()
    
    # ============= Solution Management =============
    
    def save_solution(
        self,
        problem: str,
        solution: str,
        category: str = "general",
        metadata: Dict = None
    ) -> Solution:
        """Save a new solution or update existing"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        metadata_json = json.dumps(metadata or {})
        
        # Check if similar problem exists
        cursor.execute("""
            SELECT id, success_count FROM solutions 
            WHERE problem = ? AND category = ?
        """, (problem, category))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing
            cursor.execute("""
                UPDATE solutions 
                SET solution = ?, success_count = success_count + 1, 
                    last_used = ?, metadata = ?
                WHERE id = ?
            """, (solution, now, metadata_json, existing[0]))
            solution_id = existing[0]
            success_count = existing[1] + 1
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO solutions (problem, solution, category, success_count, 
                                       last_used, created_at, metadata)
                VALUES (?, ?, ?, 1, ?, ?, ?)
            """, (problem, solution, category, now, now, metadata_json))
            solution_id = cursor.lastrowid
            success_count = 1
            
            # Update FTS
            cursor.execute("""
                INSERT INTO solutions_fts (rowid, problem, solution, category)
                VALUES (?, ?, ?, ?)
            """, (solution_id, problem, solution, category))
        
        conn.commit()
        conn.close()
        
        return Solution(
            id=solution_id,
            problem=problem,
            solution=solution,
            category=category,
            success_count=success_count,
            last_used=now,
            created_at=now,
            metadata=metadata or {}
        )
    
    def find_similar_solutions(
        self,
        query: str,
        category: str = None,
        limit: int = 5
    ) -> List[Solution]:
        """Find solutions similar to the query"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Use FTS for search
        if category:
            cursor.execute("""
                SELECT s.id, s.problem, s.solution, s.category, 
                       s.success_count, s.last_used, s.created_at, s.metadata
                FROM solutions s
                JOIN solutions_fts fts ON s.id = fts.rowid
                WHERE solutions_fts MATCH ? AND s.category = ?
                ORDER BY s.success_count DESC
                LIMIT ?
            """, (query, category, limit))
        else:
            cursor.execute("""
                SELECT s.id, s.problem, s.solution, s.category, 
                       s.success_count, s.last_used, s.created_at, s.metadata
                FROM solutions s
                JOIN solutions_fts fts ON s.id = fts.rowid
                WHERE solutions_fts MATCH ?
                ORDER BY s.success_count DESC
                LIMIT ?
            """, (query, limit))
        
        solutions = []
        for row in cursor.fetchall():
            solutions.append(Solution(
                id=row[0],
                problem=row[1],
                solution=row[2],
                category=row[3],
                success_count=row[4],
                last_used=row[5],
                created_at=row[6],
                metadata=json.loads(row[7]) if row[7] else {}
            ))
        
        conn.close()
        return solutions
    
    def get_top_solutions(self, category: str = None, limit: int = 10) -> List[Solution]:
        """Get most successful solutions"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if category:
            cursor.execute("""
                SELECT id, problem, solution, category, success_count, 
                       last_used, created_at, metadata
                FROM solutions
                WHERE category = ?
                ORDER BY success_count DESC
                LIMIT ?
            """, (category, limit))
        else:
            cursor.execute("""
                SELECT id, problem, solution, category, success_count, 
                       last_used, created_at, metadata
                FROM solutions
                ORDER BY success_count DESC
                LIMIT ?
            """, (limit,))
        
        solutions = []
        for row in cursor.fetchall():
            solutions.append(Solution(
                id=row[0],
                problem=row[1],
                solution=row[2],
                category=row[3],
                success_count=row[4],
                last_used=row[5],
                created_at=row[6],
                metadata=json.loads(row[7]) if row[7] else {}
            ))
        
        conn.close()
        return solutions
    
    def mark_solution_used(self, solution_id: int) -> bool:
        """Mark a solution as used (increment success count)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE solutions 
            SET success_count = success_count + 1, last_used = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), solution_id))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return updated
    
    # ============= Preferences Management =============
    
    def set_preference(self, key: str, value: str):
        """Set a user preference"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO preferences (key, value, updated_at)
            VALUES (?, ?, ?)
        """, (key, value, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_preference(self, key: str, default: str = None) -> Optional[str]:
        """Get a user preference"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM preferences WHERE key = ?", (key,))
        row = cursor.fetchone()
        
        conn.close()
        return row[0] if row else default
    
    def get_all_preferences(self) -> Dict[str, str]:
        """Get all preferences"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT key, value FROM preferences")
        prefs = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        return prefs
    
    # ============= Pattern Learning =============
    
    def record_pattern(self, pattern_type: str, pattern_data: Dict):
        """Record a learned pattern"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        data_json = json.dumps(pattern_data)
        now = datetime.now().isoformat()
        
        # Check if pattern exists
        cursor.execute("""
            SELECT id, frequency FROM patterns 
            WHERE pattern_type = ? AND pattern_data = ?
        """, (pattern_type, data_json))
        
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE patterns 
                SET frequency = frequency + 1, last_seen = ?
                WHERE id = ?
            """, (now, existing[0]))
        else:
            cursor.execute("""
                INSERT INTO patterns (pattern_type, pattern_data, frequency, 
                                      last_seen, created_at)
                VALUES (?, ?, 1, ?, ?)
            """, (pattern_type, data_json, now, now))
        
        conn.commit()
        conn.close()
    
    def get_common_patterns(self, pattern_type: str = None, limit: int = 10) -> List[Dict]:
        """Get most common patterns"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if pattern_type:
            cursor.execute("""
                SELECT pattern_type, pattern_data, frequency, last_seen
                FROM patterns
                WHERE pattern_type = ?
                ORDER BY frequency DESC
                LIMIT ?
            """, (pattern_type, limit))
        else:
            cursor.execute("""
                SELECT pattern_type, pattern_data, frequency, last_seen
                FROM patterns
                ORDER BY frequency DESC
                LIMIT ?
            """, (limit,))
        
        patterns = []
        for row in cursor.fetchall():
            patterns.append({
                "type": row[0],
                "data": json.loads(row[1]),
                "frequency": row[2],
                "last_seen": row[3]
            })
        
        conn.close()
        return patterns
    
    # ============= Stats =============
    
    # ============= NETWORK INTELLIGENCE =============
    
    def record_event(self, device_ip: str, event_type: str, 
                     event_data: Dict, severity: str = "info",
                     source: str = "manual") -> int:
        """Record a network event for historical analysis"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO network_events (device_ip, event_type, event_data, severity, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            device_ip, event_type, json.dumps(event_data),
            severity, source, datetime.now().isoformat()
        ))
        
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return event_id
    
    def get_device_history(self, device_ip: str, event_type: str = None,
                           limit: int = 20) -> List[Dict]:
        """Get event history for a device"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if event_type:
            cursor.execute("""
                SELECT id, device_ip, event_type, event_data, severity, source, created_at
                FROM network_events
                WHERE device_ip = ? AND event_type = ?
                ORDER BY created_at DESC LIMIT ?
            """, (device_ip, event_type, limit))
        else:
            cursor.execute("""
                SELECT id, device_ip, event_type, event_data, severity, source, created_at
                FROM network_events
                WHERE device_ip = ?
                ORDER BY created_at DESC LIMIT ?
            """, (device_ip, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": r[0], "device_ip": r[1], "event_type": r[2],
                "event_data": json.loads(r[3]) if r[3] else {},
                "severity": r[4], "source": r[5], "created_at": r[6]
            }
            for r in rows
        ]
    
    def update_baseline(self, device_ip: str, metric_type: str, value: float):
        """Update the baseline for a device metric using rolling average"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check if baseline exists
        cursor.execute("""
            SELECT baseline_value, sample_count, threshold_low, threshold_high
            FROM network_baselines
            WHERE device_ip = ? AND metric_type = ?
        """, (device_ip, metric_type))
        
        row = cursor.fetchone()
        now = datetime.now().isoformat()
        
        if row:
            old_avg, count, _, _ = row
            new_count = count + 1
            # Rolling average
            new_avg = old_avg + (value - old_avg) / new_count
            # Thresholds: ±30% of baseline (adaptive)
            threshold_low = new_avg * 0.5
            threshold_high = new_avg * 2.0
            
            cursor.execute("""
                UPDATE network_baselines
                SET baseline_value = ?, threshold_low = ?, threshold_high = ?,
                    sample_count = ?, updated_at = ?
                WHERE device_ip = ? AND metric_type = ?
            """, (new_avg, threshold_low, threshold_high, new_count, now,
                   device_ip, metric_type))
        else:
            # First measurement — initialize baseline
            cursor.execute("""
                INSERT INTO network_baselines 
                (device_ip, metric_type, baseline_value, threshold_low, threshold_high, sample_count, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (device_ip, metric_type, value, value * 0.5, value * 2.0, now))
        
        conn.commit()
        conn.close()
    
    def get_baseline(self, device_ip: str, metric_type: str) -> Optional[Dict]:
        """Get the learned baseline for a device metric"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT baseline_value, threshold_low, threshold_high, sample_count, updated_at
            FROM network_baselines
            WHERE device_ip = ? AND metric_type = ?
        """, (device_ip, metric_type))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            "device_ip": device_ip,
            "metric_type": metric_type,
            "baseline_value": row[0],
            "threshold_low": row[1],
            "threshold_high": row[2],
            "sample_count": row[3],
            "updated_at": row[4],
        }
    
    def is_anomalous(self, device_ip: str, metric_type: str, 
                      current_value: float) -> Dict:
        """Check if a current value is anomalous compared to baseline"""
        baseline = self.get_baseline(device_ip, metric_type)
        
        if not baseline or baseline["sample_count"] < 3:
            return {
                "anomalous": False,
                "reason": "Insufficient baseline data (need at least 3 samples)",
                "current_value": current_value,
                "baseline": baseline
            }
        
        is_low = current_value < baseline["threshold_low"]
        is_high = current_value > baseline["threshold_high"]
        
        if is_low or is_high:
            direction = "below" if is_low else "above"
            threshold = baseline["threshold_low"] if is_low else baseline["threshold_high"]
            return {
                "anomalous": True,
                "reason": f"Value {current_value} is {direction} threshold {threshold:.2f}",
                "current_value": current_value,
                "baseline_value": baseline["baseline_value"],
                "threshold_low": baseline["threshold_low"],
                "threshold_high": baseline["threshold_high"],
                "sample_count": baseline["sample_count"],
            }
        
        return {
            "anomalous": False,
            "reason": "Value is within normal range",
            "current_value": current_value,
            "baseline_value": baseline["baseline_value"],
        }
    
    def get_all_baselines(self, device_ip: str = None) -> List[Dict]:
        """Get all baselines, optionally filtered by device"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if device_ip:
            cursor.execute("""
                SELECT device_ip, metric_type, baseline_value, threshold_low, 
                       threshold_high, sample_count, updated_at
                FROM network_baselines WHERE device_ip = ?
                ORDER BY metric_type
            """, (device_ip,))
        else:
            cursor.execute("""
                SELECT device_ip, metric_type, baseline_value, threshold_low, 
                       threshold_high, sample_count, updated_at
                FROM network_baselines
                ORDER BY device_ip, metric_type
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "device_ip": r[0], "metric_type": r[1],
                "baseline_value": r[2], "threshold_low": r[3],
                "threshold_high": r[4], "sample_count": r[5],
                "updated_at": r[6]
            }
            for r in rows
        ]
    
    # ============= STATS =============
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM solutions")
        solutions_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM preferences")
        prefs_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM patterns")
        patterns_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(success_count) FROM solutions")
        total_uses = cursor.fetchone()[0] or 0
        
        # Network intelligence stats
        cursor.execute("SELECT COUNT(*) FROM network_events")
        events_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM network_baselines")
        baselines_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "solutions_stored": solutions_count,
            "preferences_count": prefs_count,
            "patterns_learned": patterns_count,
            "total_solution_uses": total_uses,
            "network_events": events_count,
            "network_baselines": baselines_count,
        }


# Singleton instance
long_term_memory = LongTermMemory()
