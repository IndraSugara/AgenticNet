"""
Pending Actions Store

Stores high-risk actions that require user confirmation before execution.
Actions auto-expire after 5 minutes.
"""
import uuid
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable


@dataclass
class PendingAction:
    """A high-risk action waiting for user confirmation"""
    action_id: str
    tool_name: str
    params: Dict[str, Any]
    description: str
    risk_reason: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    confirmed: bool = False
    cancelled: bool = False
    
    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 300  # 5 minute expiry
    
    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        return not self.is_expired and not self.cancelled and not self.confirmed
    
    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "tool_name": self.tool_name,
            "params": self.params,
            "description": self.description,
            "risk_reason": self.risk_reason,
            "is_expired": self.is_expired,
            "confirmed": self.confirmed,
            "cancelled": self.cancelled
        }


class PendingActionsStore:
    """
    Store for pending high-risk actions.
    
    Actions are stored with a unique ID and auto-expire after 5 minutes.
    """
    
    def __init__(self):
        self._actions: Dict[str, PendingAction] = {}
        # Map tool names to their execution functions
        self._executors: Dict[str, Callable] = {}
    
    def register_executor(self, tool_name: str, executor: Callable):
        """Register an executor function for a tool"""
        self._executors[tool_name] = executor
    
    def add(self, tool_name: str, params: Dict[str, Any], 
            description: str, risk_reason: str) -> PendingAction:
        """Add a new pending action and return it"""
        self._cleanup_expired()
        
        action_id = str(uuid.uuid4())[:8]
        action = PendingAction(
            action_id=action_id,
            tool_name=tool_name,
            params=params,
            description=description,
            risk_reason=risk_reason
        )
        self._actions[action_id] = action
        return action
    
    def get(self, action_id: str) -> Optional[PendingAction]:
        """Get a pending action by ID"""
        action = self._actions.get(action_id)
        if action and action.is_expired:
            del self._actions[action_id]
            return None
        return action
    
    def confirm(self, action_id: str) -> Dict[str, Any]:
        """
        Confirm and execute a pending action.
        
        Returns:
            Execution result dict
        """
        action = self.get(action_id)
        if not action:
            return {"success": False, "error": f"Action '{action_id}' tidak ditemukan atau sudah expired"}
        
        if action.confirmed:
            return {"success": False, "error": f"Action '{action_id}' sudah dikonfirmasi sebelumnya"}
        
        if action.cancelled:
            return {"success": False, "error": f"Action '{action_id}' sudah dibatalkan"}
        
        # Mark as confirmed
        action.confirmed = True
        
        # Execute the action
        executor = self._executors.get(action.tool_name)
        if not executor:
            return {"success": False, "error": f"Executor untuk tool '{action.tool_name}' tidak ditemukan"}
        
        try:
            result = executor(**action.params)
            return {"success": True, "result": result, "action": action.to_dict()}
        except Exception as e:
            return {"success": False, "error": str(e), "action": action.to_dict()}
    
    def cancel(self, action_id: str) -> Dict[str, Any]:
        """Cancel a pending action"""
        action = self.get(action_id)
        if not action:
            return {"success": False, "error": f"Action '{action_id}' tidak ditemukan atau sudah expired"}
        
        action.cancelled = True
        return {"success": True, "message": f"Action '{action_id}' dibatalkan", "action": action.to_dict()}
    
    def list_pending(self) -> list:
        """List all valid pending actions"""
        self._cleanup_expired()
        return [a.to_dict() for a in self._actions.values() if a.is_valid]
    
    def _cleanup_expired(self):
        """Remove expired actions"""
        expired = [aid for aid, a in self._actions.items() if a.is_expired]
        for aid in expired:
            del self._actions[aid]


# Singleton instance
pending_store = PendingActionsStore()
