"""
Chat History Database Module

Centralized handling for chat conversation history.
Provides async methods for saving, loading, and managing chat messages.
"""
import os
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime


class ChatHistoryDB:
    """
    Database handler for chat conversation history.
    
    Uses SQLite with proper threading support for async context.
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "data", 
                "chat_history.db"
            )
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection with threading support"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for faster thread lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_thread_id ON messages(thread_id)
        """)
        
        conn.commit()
        conn.close()
    
    def save_message(self, thread_id: str, role: str, content: str) -> bool:
        """
        Save a single message to the database.
        
        Args:
            thread_id: Conversation thread identifier
            role: Message role ('user' or 'assistant')
            content: Message content
            
        Returns:
            True if successful
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)",
                (thread_id, role, content)
            )
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving message: {e}")
            return False
    
    def save_messages(self, thread_id: str, messages: List[Dict]) -> int:
        """
        Save multiple messages (replaces existing for thread).
        
        Args:
            thread_id: Conversation thread identifier
            messages: List of message dicts with 'role' and 'content'
            
        Returns:
            Number of messages saved
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Clear existing messages for this thread
            cursor.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            
            # Insert all messages
            for msg in messages:
                cursor.execute(
                    "INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)",
                    (thread_id, msg.get('role', 'user'), msg.get('content', ''))
                )
            
            conn.commit()
            conn.close()
            return len(messages)
        except Exception as e:
            print(f"Error saving messages: {e}")
            return 0
    
    def get_messages(self, thread_id: str) -> List[Dict]:
        """
        Get all messages for a thread.
        
        Args:
            thread_id: Conversation thread identifier
            
        Returns:
            List of message dicts
        """
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY id ASC",
                (thread_id,)
            )
            
            messages = [{"role": row["role"], "content": row["content"]} for row in cursor.fetchall()]
            conn.close()
            return messages
        except Exception as e:
            print(f"Error loading messages: {e}")
            return []
    
    def delete_thread(self, thread_id: str) -> bool:
        """
        Delete all messages for a thread.
        
        Args:
            thread_id: Thread to delete
            
        Returns:
            True if successful
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting thread: {e}")
            return False
    
    def list_threads(self) -> List[Dict]:
        """
        List all conversation threads.
        
        Returns:
            List of thread info dicts
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    thread_id,
                    MIN(timestamp) as created,
                    MAX(timestamp) as last_updated,
                    COUNT(*) as message_count,
                    (SELECT content FROM messages m2 
                     WHERE m2.thread_id = m.thread_id 
                     ORDER BY id LIMIT 1) as preview
                FROM messages m
                GROUP BY thread_id
                ORDER BY MAX(timestamp) DESC
            """)
            
            threads = []
            for row in cursor.fetchall():
                preview = row[4]
                if preview and len(preview) > 50:
                    preview = preview[:50] + "..."
                threads.append({
                    "thread_id": row[0],
                    "created": row[1],
                    "last_updated": row[2],
                    "message_count": row[3],
                    "preview": preview
                })
            
            conn.close()
            return threads
        except Exception as e:
            print(f"Error listing threads: {e}")
            return []
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM messages")
            thread_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM messages")
            message_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "thread_count": thread_count,
                "message_count": message_count,
                "db_path": self.db_path
            }
        except Exception as e:
            return {"error": str(e)}


# Singleton instance
chat_history_db = ChatHistoryDB()
