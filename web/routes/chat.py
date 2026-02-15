"""
Chat & Conversation Routes

Endpoints for agent queries, streaming, conversation management, and chat history.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
import asyncio
import json

from config import config
from agent.langgraph_agent import network_agent as langgraph_agent
from web.websocket_manager import ws_manager
from modules.monitoring import monitoring

router = APIRouter()


# --- Request/Response Models ---

class QueryRequest(BaseModel):
    query: str
    stream: bool = False


class QueryResponse(BaseModel):
    success: bool
    response: str
    decision: Optional[dict] = None
    blocked: bool = False
    timing: Optional[dict] = None


class SaveMessageRequest(BaseModel):
    thread_id: str
    role: str
    content: str


class SaveHistoryRequest(BaseModel):
    thread_id: str
    messages: list


class ConversationQueryRequest(BaseModel):
    query: str
    thread_id: str = "default"


# --- Agent Query Endpoints ---

@router.post("/agent/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """Send a query to the network agent. Uses LangGraph agent with automatic tool selection."""
    try:
        from web.routes.health import _health_cache
        if not _health_cache.get("ollama_connected", False):
            from web.routes.health import _check_ollama_connection
            connected = await _check_ollama_connection()
            if not connected:
                return QueryResponse(
                    success=False,
                    response="⚠️ Ollama tidak terhubung. Pastikan Ollama sudah berjalan dengan `ollama serve`.",
                    blocked=False
                )
        
        response_text = await langgraph_agent.ainvoke(request.query)
        return QueryResponse(
            success=True,
            response=response_text,
            decision=None,
            blocked=False,
            timing={"mode": "langgraph"}
        )
    except asyncio.TimeoutError:
        return QueryResponse(
            success=False,
            response="⏱️ Request timeout. Model mungkin sedang sibuk, coba lagi.",
            blocked=False
        )
    except Exception as e:
        return QueryResponse(
            success=False,
            response=f"❌ Error: {str(e)}",
            blocked=False
        )


@router.post("/agent/conversations/query")
async def query_with_thread(request: ConversationQueryRequest):
    """Send a query with a specific thread ID for conversation memory."""
    try:
        response_text = await langgraph_agent.ainvoke(request.query, request.thread_id)
        return {
            "success": True,
            "response": response_text,
            "thread_id": request.thread_id,
            "timing": {"mode": "langgraph"}
        }
    except Exception as e:
        return {
            "success": False,
            "response": f"Error: {str(e)}",
            "thread_id": request.thread_id
        }


# --- Streaming Endpoints ---

@router.websocket("/agent/stream")
async def stream_agent(websocket: WebSocket):
    """WebSocket endpoint for streaming agent responses."""
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            query = message.get("query", "")
            thread_id = message.get("thread_id", "default")
            
            await websocket.send_json({
                "type": "progress",
                "phase": "processing",
                "status": "starting"
            })
            
            full_response = ""
            async for chunk in langgraph_agent.astream(query, thread_id):
                full_response += chunk
                await websocket.send_json({
                    "type": "chunk",
                    "content": chunk
                })
            
            await websocket.send_json({
                "type": "complete",
                "response": full_response,
                "blocked": False,
                "timing": {"mode": "langgraph_stream"}
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


@router.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    """WebSocket endpoint for real-time metrics streaming."""
    await ws_manager.connect(websocket, "metrics")
    
    try:
        metrics = monitoring.get_current_metrics()
        if metrics:
            await ws_manager.send_personal(websocket, {
                "type": "metrics",
                "data": metrics.to_dict(),
                "timestamp": metrics.timestamp.isoformat()
            })
        
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                msg = json.loads(data) if data else {}
                
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg.get("type") == "refresh":
                    metrics = monitoring.get_current_metrics()
                    if metrics:
                        await ws_manager.send_personal(websocket, {
                            "type": "metrics",
                            "data": metrics.to_dict(),
                            "timestamp": metrics.timestamp.isoformat()
                        })
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        ws_manager.disconnect(websocket, "metrics")


# --- History & Conversation Endpoints ---


@router.get("/agent/conversations/{thread_id}")
async def get_conversation_history(thread_id: str):
    """Get conversation history for a specific thread."""
    history = langgraph_agent.get_history(thread_id)
    return {
        "success": True,
        "thread_id": thread_id,
        "count": len(history),
        "messages": history
    }


@router.delete("/agent/conversations/{thread_id}")
async def clear_conversation(thread_id: str):
    """Clear conversation history for a thread."""
    try:
        langgraph_agent.clear_history(thread_id)
    except Exception as e:
        print(f"Error clearing LangGraph history: {e}")
    
    # Also clear from SQLite if present
    try:
        import aiosqlite
        async with aiosqlite.connect("data/chat_history.db") as db:
            await db.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            await db.commit()
    except Exception:
        pass
    
    return {"success": True, "message": f"Conversation '{thread_id}' cleared"}


@router.post("/agent/history/save")
async def save_chat_message(request: SaveMessageRequest):
    """Async save single message to SQLite"""
    try:
        import aiosqlite
        import os
        os.makedirs("data", exist_ok=True)
        
        async with aiosqlite.connect("data/chat_history.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute(
                "INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)",
                (request.thread_id, request.role, request.content)
            )
            await db.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/agent/history/bulk-save")
async def save_chat_history(request: SaveHistoryRequest):
    """Async save full conversation to SQLite (replaces existing)"""
    try:
        import aiosqlite
        import os
        os.makedirs("data", exist_ok=True)
        
        async with aiosqlite.connect("data/chat_history.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("DELETE FROM messages WHERE thread_id = ?", (request.thread_id,))
            for msg in request.messages:
                await db.execute(
                    "INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)",
                    (request.thread_id, msg.get('role', 'user'), msg.get('content', ''))
                )
            await db.commit()
        return {"success": True, "count": len(request.messages)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/agent/history/threads")
async def list_chat_threads():
    """List all chat threads with preview and message count"""
    try:
        import aiosqlite
        import os
        
        db_path = "data/chat_history.db"
        if not os.path.exists(db_path):
            return {"success": True, "threads": []}
        
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("""
                SELECT 
                    thread_id,
                    MIN(timestamp) as created,
                    MAX(timestamp) as last_updated,
                    COUNT(*) as message_count,
                    (SELECT content FROM messages m2 WHERE m2.thread_id = m.thread_id ORDER BY id LIMIT 1) as preview
                FROM messages m
                GROUP BY thread_id
                ORDER BY MAX(timestamp) DESC
            """)
            rows = await cursor.fetchall()
            threads = [{
                "thread_id": row[0],
                "created": row[1],
                "last_updated": row[2],
                "message_count": row[3],
                "preview": (row[4][:50] + "...") if row[4] and len(row[4]) > 50 else row[4]
            } for row in rows]
        
        return {"success": True, "threads": threads, "count": len(threads)}
    except Exception as e:
        return {"success": False, "error": str(e), "threads": []}


@router.get("/agent/history/{thread_id}")
async def get_chat_history(thread_id: str):
    """Async load chat history from SQLite"""
    try:
        import aiosqlite
        import os
        
        db_path = "data/chat_history.db"
        if not os.path.exists(db_path):
            return {"success": True, "messages": []}
        
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY id ASC",
                (thread_id,)
            )
            rows = await cursor.fetchall()
            messages = [{"role": row[0], "content": row[1]} for row in rows]
        
        return {"success": True, "messages": messages, "count": len(messages)}
    except Exception as e:
        return {"success": False, "error": str(e), "messages": []}
