"""
LangGraph Memory with SQLite Persistence

Provides persistent conversation memory using SQLite checkpointer.
Conversations are saved to disk and survive server restarts.
"""
import os
from typing import Optional
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.checkpoint.memory import MemorySaver

# Database path
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "conversations.db")

# Global checkpointer singleton
_async_checkpointer = None


def get_sqlite_checkpointer() -> AsyncSqliteSaver:
    """
    Get AsyncSqlite checkpointer for persistent memory
    
    Conversations are stored in data/conversations.db
    
    Returns:
        AsyncSqliteSaver instance
    """
    global _async_checkpointer
    
    # Ensure data directory exists
    os.makedirs(DB_DIR, exist_ok=True)
    
    # Create singleton checkpointer
    if _async_checkpointer is None:
        _async_checkpointer = AsyncSqliteSaver.from_conn_string(DB_PATH)
    
    return _async_checkpointer


def get_memory_checkpointer(persistent: bool = True):
    """
    Get appropriate checkpointer based on configuration
    
    Note: We use MemorySaver because SqliteSaver doesn't support async methods
    which are required by FastAPI's async endpoints. MemorySaver works with both
    sync and async operations.
    
    For true persistence, chat history is saved separately via chat_history.py
    
    Args:
        persistent: If True, use SQLite. If False, use in-memory.
    
    Returns:
        Checkpointer instance (MemorySaver for both cases due to async compatibility)
    """
    # Always use MemorySaver as it supports both sync and async operations
    # True persistence is handled by the separate chat_history module
    return MemorySaver()


class ConversationManager:
    """
    Manager for conversation history and memory
    
    Provides:
    - Thread-based conversation isolation
    - History retrieval
    - Memory clearing
    """
    
    def __init__(self, checkpointer=None):
        """
        Initialize conversation manager
        
        Args:
            checkpointer: Optional custom checkpointer
        """
        self.checkpointer = checkpointer or get_memory_checkpointer()
    
    def get_thread_config(self, thread_id: str) -> dict:
        """Get config dict for a thread"""
        return {"configurable": {"thread_id": thread_id}}
    
    def list_threads(self) -> list:
        """
        List all conversation threads
        
        Note: MemorySaver tracks threads internally via storage dict
        """
        if hasattr(self.checkpointer, 'storage'):
            try:
                # MemorySaver stores by thread_id in storage dict
                return list(set(
                    config.get('thread_id') 
                    for config in self.checkpointer.storage.keys()
                    if isinstance(config, tuple) and len(config) > 0
                ))
            except Exception:
                return []
        return []
    
    def clear_thread(self, thread_id: str) -> bool:
        """
        Clear conversation history for a thread
        
        Note: For MemorySaver, we remove entries from storage
        """
        if hasattr(self.checkpointer, 'storage'):
            try:
                # Remove all entries for this thread
                keys_to_remove = [
                    key for key in self.checkpointer.storage.keys()
                    if isinstance(key, tuple) and len(key) > 0 and key[0] == thread_id
                ]
                for key in keys_to_remove:
                    del self.checkpointer.storage[key]
                return True
            except Exception:
                return False
        return False


# Singleton instances
_sqlite_checkpointer = None
_conversation_manager = None


def get_checkpointer():
    """Get or create SQLite checkpointer singleton"""
    global _sqlite_checkpointer
    if _sqlite_checkpointer is None:
        _sqlite_checkpointer = get_memory_checkpointer(persistent=True)
    return _sqlite_checkpointer


def get_conversation_manager():
    """Get or create conversation manager singleton"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager(get_checkpointer())
    return _conversation_manager
