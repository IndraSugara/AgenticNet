"""
Long-Term Memory Module

Enhanced memory for the agent:
- Solution caching for troubleshooting
- User preferences storage
- Learned patterns from past interactions
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
        
        conn.close()
        
        return {
            "solutions_stored": solutions_count,
            "preferences_count": prefs_count,
            "patterns_learned": patterns_count,
            "total_solution_uses": total_uses
        }


# Singleton instance
long_term_memory = LongTermMemory()
