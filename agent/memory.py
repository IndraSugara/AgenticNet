"""
Workflow Memory

Context and memory persistence for:
- Short-term memory (current workflow)
- Long-term memory (past executions)
- Context retrieval
- SQLite persistence for data survival across restarts
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import sqlite3
import os


@dataclass
class MemoryEntry:
    """Single memory entry"""
    id: str
    type: str  # "workflow", "tool", "learning"
    content: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    relevance_score: float = 1.0
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "timestamp": self.timestamp,
            "relevance_score": self.relevance_score
        }


class WorkflowMemory:
    """
    Memory system for agentic workflows
    
    Provides:
    - Short-term memory for current context
    - Long-term storage of past executions
    - Retrieval of relevant past experiences
    - Learning from successes and failures
    - SQLite persistence for data survival
    """
    
    def __init__(self, max_short_term: int = 20, max_long_term: int = 100, db_path: str = None):
        self.short_term: List[MemoryEntry] = []
        self.long_term: List[MemoryEntry] = []
        self.max_short_term = max_short_term
        self.max_long_term = max_long_term
        self._entry_counter = 0
        
        # Setup database path
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "data", 
                "workflow_memory.db"
            )
        self.db_path = db_path
        
        # Initialize database and load existing data
        self._init_db()
        self._load_from_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection with threading support"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                relevance_score REAL DEFAULT 1.0,
                is_long_term INTEGER DEFAULT 0
            )
        """)
        
        # Get max entry counter
        cursor.execute("SELECT MAX(CAST(SUBSTR(id, 5) AS INTEGER)) FROM memory_entries WHERE id LIKE 'mem_%'")
        result = cursor.fetchone()[0]
        if result:
            self._entry_counter = result
        
        conn.commit()
        conn.close()
    
    def _load_from_db(self):
        """Load existing entries from database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Load short-term (most recent, not long-term)
        cursor.execute("""
            SELECT id, type, content, timestamp, relevance_score 
            FROM memory_entries 
            WHERE is_long_term = 0
            ORDER BY timestamp DESC
            LIMIT ?
        """, (self.max_short_term,))
        
        for row in cursor.fetchall():
            entry = MemoryEntry(
                id=row[0],
                type=row[1],
                content=json.loads(row[2]),
                timestamp=row[3],
                relevance_score=row[4]
            )
            self.short_term.append(entry)
        
        # Reverse to maintain chronological order
        self.short_term.reverse()
        
        # Load long-term
        cursor.execute("""
            SELECT id, type, content, timestamp, relevance_score 
            FROM memory_entries 
            WHERE is_long_term = 1
            ORDER BY timestamp DESC
            LIMIT ?
        """, (self.max_long_term,))
        
        for row in cursor.fetchall():
            entry = MemoryEntry(
                id=row[0],
                type=row[1],
                content=json.loads(row[2]),
                timestamp=row[3],
                relevance_score=row[4]
            )
            self.long_term.append(entry)
        
        self.long_term.reverse()
        conn.close()
    
    def _save_entry(self, entry: MemoryEntry, is_long_term: bool = False):
        """Save entry to database"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO memory_entries 
            (id, type, content, timestamp, relevance_score, is_long_term)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            entry.id,
            entry.type,
            json.dumps(entry.content),
            entry.timestamp,
            entry.relevance_score,
            1 if is_long_term else 0
        ))
        
        conn.commit()
        conn.close()
    
    def _generate_id(self) -> str:
        """Generate unique memory ID"""
        self._entry_counter += 1
        return f"mem_{self._entry_counter}"
    
    def remember(self, type: str, content: Dict[str, Any]) -> str:
        """
        Store something in short-term memory
        
        Args:
            type: Type of memory (workflow, tool, learning)
            content: Content to store
            
        Returns:
            Memory entry ID
        """
        entry = MemoryEntry(
            id=self._generate_id(),
            type=type,
            content=content
        )
        self.short_term.append(entry)
        self._save_entry(entry, is_long_term=False)
        
        # Trim if needed
        if len(self.short_term) > self.max_short_term:
            # Move oldest to long-term
            oldest = self.short_term.pop(0)
            self._move_to_long_term(oldest)
        
        return entry.id
    
    def _move_to_long_term(self, entry: MemoryEntry):
        """Move entry to long-term memory"""
        self.long_term.append(entry)
        self._save_entry(entry, is_long_term=True)
        
        # Trim long-term if needed
        if len(self.long_term) > self.max_long_term:
            removed = self.long_term.pop(0)
            # Delete from database
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_entries WHERE id = ?", (removed.id,))
            conn.commit()
            conn.close()
    
    def consolidate(self):
        """Move all short-term memories to long-term"""
        for entry in self.short_term:
            self._move_to_long_term(entry)
        self.short_term.clear()
    
    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """
        Retrieve relevant memories
        
        Args:
            query: Search query
            limit: Max results
            
        Returns:
            List of relevant memories
        """
        query_lower = query.lower()
        results = []
        
        # Simple keyword matching (could use embeddings later)
        all_memories = self.short_term + self.long_term
        
        for entry in all_memories:
            content_str = json.dumps(entry.content).lower()
            
            # Calculate simple relevance score
            score = 0
            for word in query_lower.split():
                if word in content_str:
                    score += 1
            
            if score > 0:
                entry.relevance_score = score
                results.append(entry)
        
        # Sort by relevance
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return results[:limit]
    
    def recall_by_type(self, type: str, limit: int = 10) -> List[MemoryEntry]:
        """Get memories by type"""
        all_memories = self.short_term + self.long_term
        matched = [m for m in all_memories if m.type == type]
        return matched[-limit:]
    
    def get_workflow_history(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get past workflow summaries"""
        workflows = self.recall_by_type("workflow", limit)
        return [w.content for w in workflows]
    
    def learn_from_success(self, goal: str, steps: List[str], tools: List[str]):
        """Store successful workflow pattern"""
        self.remember("learning", {
            "type": "success",
            "goal": goal,
            "steps": steps,
            "tools": tools
        })
    
    def learn_from_failure(self, goal: str, failed_step: str, error: str, recovery: str = None):
        """Store failure and recovery pattern"""
        self.remember("learning", {
            "type": "failure",
            "goal": goal,
            "failed_step": failed_step,
            "error": error,
            "recovery": recovery
        })
    
    def get_context_for_planning(self, goal: str) -> str:
        """Get relevant context for new planning"""
        # Find similar past workflows
        similar = self.recall(goal, limit=3)
        
        if not similar:
            return ""
        
        context_lines = ["## Pengalaman Sebelumnya\n"]
        
        for mem in similar:
            if mem.type == "workflow":
                context_lines.append(f"- Goal: {mem.content.get('goal', 'N/A')}")
                context_lines.append(f"  Success: {mem.content.get('success', False)}")
            elif mem.type == "learning":
                if mem.content.get("type") == "success":
                    context_lines.append(f"- ✅ {mem.content.get('goal')}: berhasil dengan {len(mem.content.get('steps', []))} langkah")
                else:
                    context_lines.append(f"- ❌ {mem.content.get('goal')}: gagal di {mem.content.get('failed_step')}")
        
        return "\n".join(context_lines)
    
    def clear_short_term(self):
        """Clear short-term memory"""
        # Delete from database
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memory_entries WHERE is_long_term = 0")
        conn.commit()
        conn.close()
        
        self.short_term.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            "short_term_count": len(self.short_term),
            "long_term_count": len(self.long_term),
            "total": len(self.short_term) + len(self.long_term),
            "db_path": self.db_path,
            "by_type": {
                "workflow": len([m for m in self.short_term + self.long_term if m.type == "workflow"]),
                "tool": len([m for m in self.short_term + self.long_term if m.type == "tool"]),
                "learning": len([m for m in self.short_term + self.long_term if m.type == "learning"])
            }
        }


# Singleton memory
memory = WorkflowMemory()
