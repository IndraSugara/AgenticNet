"""
WebSocket Connection Manager

Manages WebSocket connections for real-time updates:
- Metrics streaming (CPU, Memory, Disk, Network)
- System notifications and alerts
- Chat messaging
"""
from fastapi import WebSocket
from typing import Dict, List, Set, Any
import asyncio
import json
from datetime import datetime


class ConnectionManager:
    """
    Manages active WebSocket connections and broadcasts updates.
    
    Features:
    - Track multiple clients per channel (metrics, notifications, chat)
    - Broadcast to all clients in a channel
    - Handle connection lifecycle (connect/disconnect)
    - Graceful error handling for disconnected clients
    """
    
    def __init__(self):
        # Store connections by channel
        self.connections: Dict[str, Set[WebSocket]] = {
            "metrics": set(),
            "notifications": set(),
            "chat": set()
        }
        self._broadcast_task = None
        self._running = False
    
    async def connect(self, websocket: WebSocket, channel: str = "metrics"):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        if channel not in self.connections:
            self.connections[channel] = set()
        self.connections[channel].add(websocket)
        print(f"🔌 WebSocket connected to {channel} (total: {len(self.connections[channel])})")
    
    def disconnect(self, websocket: WebSocket, channel: str = "metrics"):
        """Remove a WebSocket connection"""
        if channel in self.connections and websocket in self.connections[channel]:
            self.connections[channel].discard(websocket)
            print(f"🔌 WebSocket disconnected from {channel} (remaining: {len(self.connections[channel])})")
    
    async def broadcast(self, message: dict, channel: str = "metrics"):
        """Broadcast a message to all clients in a channel"""
        if channel not in self.connections:
            return
        
        # Create a copy to avoid modification during iteration
        connections = list(self.connections[channel])
        disconnected = []
        
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                # Client disconnected
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.connections[channel].discard(ws)
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send a message to a specific client"""
        try:
            await websocket.send_json(message)
        except Exception:
            pass
    
    def get_connection_count(self, channel: str = None) -> int:
        """Get number of active connections"""
        if channel:
            return len(self.connections.get(channel, set()))
        return sum(len(conns) for conns in self.connections.values())
    
    async def broadcast_metrics(self, metrics: dict):
        """Broadcast metrics update to all metrics subscribers"""
        message = {
            "type": "metrics",
            "data": metrics,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message, "metrics")
    
    async def broadcast_notification(self, notification: dict):
        """Broadcast a notification to all notification subscribers"""
        message = {
            "type": "notification",
            "data": notification,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message, "notifications")
    
    async def broadcast_alert(self, alert: dict):
        """Broadcast an alert to all channels"""
        message = {
            "type": "alert",
            "data": alert,
            "timestamp": datetime.now().isoformat()
        }
        # Send to both metrics and notifications channels
        await self.broadcast(message, "metrics")
        await self.broadcast(message, "notifications")


# Singleton instance
ws_manager = ConnectionManager()
