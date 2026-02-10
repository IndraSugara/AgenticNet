"""
FastAPI Web Application for Network Infrastructure Agent

Optimized with:
- Non-blocking health checks
- Background health monitoring
- Lifespan context manager (replacing deprecated on_event)
- Request timeout handling
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
import asyncio
import json
import os
import time

from config import config
from agent.llm_client import llm_client
from agent.transparency import transparency
from agent.workflow import Workflow, save_workflow, get_workflow_history, get_workflow_by_id
from agent.planner import planner
from agent.executor import execute_tool
from agent.memory import memory
from agent.infrastructure import infrastructure
from agent.scheduler import scheduler
from agent.alerting import alert_manager, handle_device_alert
from modules.monitoring import monitoring
from modules.security import security
from modules.inventory import inventory, DeviceInfo, VendorType, DeviceRole
from modules.guardrails import guardrails, RiskLevel, ExecutionPlan
from tools.network_tools import network_tools
from tools.vendor_drivers import connection_manager, UnifiedCommand
from tools.unified_commands import unified_commands
from tools.tool_registry import registry as tool_registry
from web.websocket_manager import ws_manager

# LangGraph Agent (primary - required)
from agent.langgraph_agent import network_agent as langgraph_agent
from agent.langchain_tools import get_all_tools
print(f"🔗 LangGraph agent loaded with {len(get_all_tools())} tools")

# LangGraph availability flag (used in route handlers)
LANGGRAPH_AVAILABLE = True


# Global state for cached health status
_health_cache: Dict[str, Any] = {
    "status": "unknown",
    "ollama_connected": False,
    "model": config.OLLAMA_MODEL,
    "last_check": 0,
    "monitoring": {}
}


async def update_health_cache():
    """Update the health cache asynchronously"""
    global _health_cache
    try:
        ollama_ok = await llm_client.check_connection_async(use_cache=False)
        _health_cache.update({
            "status": "healthy" if ollama_ok else "degraded",
            "ollama_connected": ollama_ok,
            "model": config.OLLAMA_MODEL,
            "last_check": time.time(),
            "monitoring": monitoring.get_health_summary()
        })
    except Exception as e:
        _health_cache.update({
            "status": "error",
            "ollama_connected": False,
            "error": str(e),
            "last_check": time.time()
        })


async def health_check_background_task():
    """Background task to periodically check health"""
    while True:
        await update_health_cache()
        await asyncio.sleep(30)  # Check every 30 seconds


async def network_monitor_task():
    """Background task to monitor network latency and bandwidth"""
    while True:
        try:
            # Measure latency
            latency_data = await asyncio.to_thread(network_tools.measure_latency)
            monitoring.update_network_metrics(latency=latency_data.get("latencies", []))
            
            # Measure bandwidth
            bandwidth_data = await asyncio.to_thread(network_tools.get_bandwidth_stats)
            monitoring.update_network_metrics(bandwidth={
                "upload_rate_kbps": bandwidth_data.get("upload_rate_kbps", 0),
                "download_rate_kbps": bandwidth_data.get("download_rate_kbps", 0)
            })
            
        except Exception as e:
            print(f"⚠️ Network monitor error: {e}")
            
        await asyncio.sleep(10)  # Check network every 10 seconds

async def metrics_broadcast_task():
    """Background task to broadcast metrics via WebSocket every 5 seconds"""
    while True:
        try:
            # Only broadcast if there are connected clients
            if ws_manager.get_connection_count("metrics") > 0:
                metrics = monitoring.get_current_metrics()
                if metrics:
                    metrics_data = metrics.to_dict()
                    
                    # Add cached network metrics
                    net_metrics = monitoring.get_network_metrics()
                    metrics_data["latency"] = net_metrics.get("latency", [])
                    metrics_data["bandwidth"] = net_metrics.get("bandwidth", {})
                    
                    await ws_manager.broadcast_metrics(metrics_data)
        except Exception as e:
            print(f"⚠️ Metrics broadcast error: {e}")
        await asyncio.sleep(5)  # Broadcast every 5 seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown events
    Replaces deprecated @app.on_event decorators
    """
    # Startup
    print("🚀 Starting Agentic Network Infrastructure Operator...")
    print(f"📡 Checking Ollama connection at {config.OLLAMA_HOST}...")
    
    # Non-blocking initial health check
    await update_health_cache()
    
    if _health_cache["ollama_connected"]:
        print(f"✅ Connected to Ollama with model: {config.OLLAMA_MODEL}")
    else:
        print(f"⚠️ Ollama not available at startup")
    
    # Log tool count from registry
    print(f"🔧 Tool Registry: {len(tool_registry.get_tool_names())} tools available")
    
    # Start background health check task
    health_task = asyncio.create_task(health_check_background_task())
    
    # Start network monitor task
    network_task = asyncio.create_task(network_monitor_task())
    
    # Start WebSocket metrics broadcast task
    metrics_task = asyncio.create_task(metrics_broadcast_task())
    print("📡 WebSocket metrics broadcast started (every 5s)")
    
    # Start system metrics collection
    monitoring.start_collection(interval=10)
    
    print(f"🌐 Server ready at http://{config.HOST}:{config.PORT}")
    
    yield  # App is running
    
    # Shutdown
    monitoring.stop_collection()
    health_task.cancel()
    network_task.cancel()
    metrics_task.cancel()
    try:
        await health_task
        await network_task
        await metrics_task
    except asyncio.CancelledError:
        pass
    print("👋 Shutting down...")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Agentic Network Infrastructure Operator",
    description="AI-powered network infrastructure management with LangGraph",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup templates
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
static_dir = os.path.join(os.path.dirname(__file__), "static")

os.makedirs(templates_dir, exist_ok=True)
os.makedirs(static_dir, exist_ok=True)
os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
os.makedirs(os.path.join(static_dir, "js"), exist_ok=True)

templates = Jinja2Templates(directory=templates_dir)

# Mount static files - unconditionally since directories are created above
print(f"📁 Static directory path: {static_dir}")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
print(f"✅ Mounted static files at /static")


# Request/Response Models
class QueryRequest(BaseModel):
    query: str
    stream: bool = False


class QueryResponse(BaseModel):
    success: bool
    response: str
    decision: Optional[dict] = None
    blocked: bool = False
    timing: Optional[dict] = None


class ToolRequest(BaseModel):
    tool: str
    params: dict


class WorkflowRequest(BaseModel):
    goal: str


class WorkflowResponse(BaseModel):
    workflow_id: str
    goal: str
    status: str
    steps: list
    result: Optional[dict] = None


class DeviceRequest(BaseModel):
    name: str
    ip: str
    type: str = "other"
    description: str = ""
    location: str = ""
    ports_to_monitor: List[int] = []
    check_interval: int = 60

# API Endpoints

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main dashboard"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "model": config.OLLAMA_MODEL
    })


@app.get("/health")
async def health_check():
    """
    Check system health (non-blocking, uses cached status)
    """
    # Return cached health if recent enough (< 5 seconds)
    if time.time() - _health_cache["last_check"] < 5:
        return _health_cache
    
    # Otherwise, update cache asynchronously
    await update_health_cache()
    return _health_cache


@app.post("/agent/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """
    Send a query to the network agent.
    Uses LangGraph agent with automatic tool selection.
    """
    try:
        # Check if Ollama is connected first
        if not _health_cache.get("ollama_connected", False):
            connected = await llm_client.check_connection_async(use_cache=True)
            if not connected:
                return QueryResponse(
                    success=False,
                    response="⚠️ Ollama tidak terhubung. Pastikan Ollama sudah berjalan dengan `ollama serve`.",
                    blocked=False
                )
        
        # Use LangGraph agent
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


@app.websocket("/agent/stream")
async def stream_agent(websocket: WebSocket):
    """
    WebSocket endpoint for streaming agent responses.
    Uses LangGraph streaming for real-time responses.
    """
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
            
            # Stream response chunks
            full_response = ""
            async for chunk in langgraph_agent.astream(query, thread_id):
                full_response += chunk
                await websocket.send_json({
                    "type": "chunk",
                    "content": chunk
                })
            
            # Send completion
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
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass


@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    """
    WebSocket endpoint for real-time metrics streaming.
    
    Clients receive automatic metrics updates every 5 seconds.
    Message format:
    {
        "type": "metrics",
        "data": { cpu, memory, disk, network, interfaces, ... },
        "timestamp": "ISO datetime"
    }
    """
    await ws_manager.connect(websocket, "metrics")
    
    try:
        # Send initial metrics immediately
        metrics = monitoring.get_current_metrics()
        if metrics:
            await ws_manager.send_personal(websocket, {
                "type": "metrics",
                "data": metrics.to_dict(),
                "timestamp": metrics.timestamp.isoformat()
            })
        
        # Keep connection alive and wait for any client messages
        while True:
            try:
                # Receive heartbeat or commands from client
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                msg = json.loads(data) if data else {}
                
                # Handle ping/pong for keepalive
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
                # Handle manual refresh request
                elif msg.get("type") == "refresh":
                    metrics = monitoring.get_current_metrics()
                    if metrics:
                        await ws_manager.send_personal(websocket, {
                            "type": "metrics",
                            "data": metrics.to_dict(),
                            "timestamp": metrics.timestamp.isoformat()
                        })
            except asyncio.TimeoutError:
                # Send ping to check if client is alive
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


@app.get("/agent/history")
async def get_history(limit: int = 10):
    """Get decision history (legacy ODRVA)"""
    history = transparency.get_history(limit)
    return {
        "count": len(history),
        "decisions": [d.to_dict() for d in history]
    }


# ============= LANGGRAPH CONVERSATION ENDPOINTS =============

@app.get("/agent/conversations/{thread_id}")
async def get_conversation_history(thread_id: str):
    """
    Get conversation history for a specific thread.
    
    Args:
        thread_id: Unique conversation thread identifier
    
    Returns:
        List of messages in the conversation
    """
    if not LANGGRAPH_AVAILABLE or not langgraph_agent:
        return {"success": False, "error": "LangGraph not available"}
    
    history = langgraph_agent.get_history(thread_id)
    return {
        "success": True,
        "thread_id": thread_id,
        "count": len(history),
        "messages": history
    }


@app.delete("/agent/conversations/{thread_id}")
async def clear_conversation(thread_id: str):
    """
    Clear conversation history for a thread.
    
    Args:
        thread_id: Thread to clear
    """
    # Clear from SQLite
    try:
        import aiosqlite
        async with aiosqlite.connect("data/chat_history.db") as db:
            await db.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
            await db.commit()
    except Exception as e:
        print(f"Error clearing history: {e}")
    
    return {
        "success": True,
        "message": f"Conversation '{thread_id}' cleared"
    }


class SaveMessageRequest(BaseModel):
    thread_id: str
    role: str
    content: str


class SaveHistoryRequest(BaseModel):
    thread_id: str
    messages: list


@app.post("/agent/history/save")
async def save_chat_message(request: SaveMessageRequest):
    """Async save single message to SQLite"""
    try:
        import aiosqlite
        import os
        os.makedirs("data", exist_ok=True)
        
        async with aiosqlite.connect("data/chat_history.db") as db:
            # Create table if not exists
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


@app.post("/agent/history/bulk-save")
async def save_chat_history(request: SaveHistoryRequest):
    """Async save full conversation to SQLite (replaces existing)"""
    try:
        import aiosqlite
        import os
        os.makedirs("data", exist_ok=True)
        
        async with aiosqlite.connect("data/chat_history.db") as db:
            # Create table if not exists
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Clear existing messages for this thread
            await db.execute("DELETE FROM messages WHERE thread_id = ?", (request.thread_id,))
            # Insert all messages
            for msg in request.messages:
                await db.execute(
                    "INSERT INTO messages (thread_id, role, content) VALUES (?, ?, ?)",
                    (request.thread_id, msg.get('role', 'user'), msg.get('content', ''))
                )
            await db.commit()
        
        return {"success": True, "count": len(request.messages)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============= MODEL MANAGEMENT ENDPOINTS =============

@app.get("/agent/models/list")
async def list_available_models():
    """Get list of available LLM models"""
    try:
        return {
            "success": True,
            "models": config.AVAILABLE_MODELS,
            "current": config.DEFAULT_MODEL
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/agent/model/switch")
async def switch_model(request: Request):
    """Switch the active LLM model"""
    try:
        data = await request.json()
        model_id = data.get("model_id")
        
        if not model_id or model_id not in config.AVAILABLE_MODELS:
            return {
                "success": False,
                "error": "Invalid model ID. Available models: " + ", ".join(config.AVAILABLE_MODELS.keys())
            }
        
        # Update configuration
        config.DEFAULT_MODEL = model_id
        config.OLLAMA_MODEL = model_id
        
        # Reinitialize LLM client with new model
        llm_client.model = model_id
        
        # Update health cache
        _health_cache["model"] = model_id
        
        return {
            "success": True,
            "model": config.AVAILABLE_MODELS[model_id],
            "message": f"Switched to {config.AVAILABLE_MODELS[model_id]['name']}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/agent/history/threads")
async def list_chat_threads():
    """List all chat threads with preview and message count"""
    try:
        import aiosqlite
        import os
        
        db_path = "data/chat_history.db"
        if not os.path.exists(db_path):
            return {"success": True, "threads": []}
        
        async with aiosqlite.connect(db_path) as db:
            # Get unique threads with first message preview and count
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


@app.get("/agent/history/{thread_id}")
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


class ConversationQueryRequest(BaseModel):
    query: str
    thread_id: str = "default"


@app.post("/agent/conversations/query")
async def query_with_thread(request: ConversationQueryRequest):
    """
    Send a query with a specific thread ID for conversation memory.
    
    This allows maintaining separate conversation contexts.
    """
    if not LANGGRAPH_AVAILABLE or not langgraph_agent:
        # Fallback to legacy
        return await query_agent(QueryRequest(query=request.query))
    
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


@app.post("/tools/run")
async def run_tool(request: ToolRequest):
    """Run a network diagnostic tool"""
    tool_name = request.tool
    params = request.params
    
    tool_map = {
        "ping": lambda p: network_tools.ping(p.get("host", ""), p.get("count", 4)),
        "traceroute": lambda p: network_tools.traceroute(p.get("host", "")),
        "dns": lambda p: network_tools.dns_lookup(p.get("hostname", "")),
        "port_scan": lambda p: network_tools.port_scan(p.get("host", ""), p.get("ports")),
        "check_port": lambda p: network_tools.check_port(p.get("host", ""), p.get("port", 80)),
        "network_info": lambda p: network_tools.get_network_info(),
        "provider_info": lambda p: network_tools.get_provider_info_formatted()
    }
    
    if tool_name not in tool_map:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
    
    # Run tool in thread to avoid blocking
    try:
        result = await asyncio.to_thread(tool_map[tool_name], params)
        return {
            "tool": tool_name,
            "success": result.success,
            "output": result.output,
            "error": result.error
        }
    except Exception as e:
        return {
            "tool": tool_name,
            "success": False,
            "output": "",
            "error": str(e)
        }


@app.get("/monitoring/status")
async def get_monitoring_status():
    """Get current monitoring status"""
    return monitoring.get_health_summary()


@app.get("/monitoring/metrics")
async def get_system_metrics():
    """Get real-time system metrics (CPU, RAM, Disk, Network)"""
    metrics = await asyncio.to_thread(monitoring.collect_system_metrics)
    if metrics:
        return {
            "success": True,
            "metrics": metrics.to_dict()
        }
    return {
        "success": False,
        "error": "Could not collect system metrics. Is psutil installed?"
    }


@app.get("/monitoring/trends/{metric_name}")
async def get_metric_trend(metric_name: str, window: int = 10):
    """Get trend analysis for a specific metric"""
    return monitoring.analyze_trend(metric_name, window)


@app.get("/security/status")
async def get_security_status():
    """Get security findings summary"""
    return security.get_risk_summary()


@app.post("/security/analyze")
async def analyze_config(config_text: str, device_type: str = "generic"):
    """Analyze network device configuration"""
    findings = await asyncio.to_thread(security.analyze_config, config_text, device_type)
    return {
        "findings_count": len(findings),
        "findings": [f.to_dict() for f in findings]
    }


# Network Monitoring Endpoints
@app.get("/network/interfaces")
async def get_network_interfaces():
    """Get all network interfaces with status and statistics"""
    return await asyncio.to_thread(network_tools.get_interfaces)


@app.get("/network/connections")
async def get_network_connections():
    """Get active network connections"""
    return await asyncio.to_thread(network_tools.get_connections)


@app.get("/network/latency")
async def get_network_latency():
    """Measure latency to common hosts (Google DNS, Cloudflare, Google)"""
    return await asyncio.to_thread(network_tools.measure_latency)


@app.get("/network/bandwidth")
async def get_network_bandwidth():
    """Get current bandwidth statistics (requires ~1 second)"""
    return await asyncio.to_thread(network_tools.get_bandwidth_stats)


# ============= ENHANCED MONITORING ENDPOINTS =============

@app.get("/monitoring/metrics/detailed")
async def get_detailed_metrics():
    """Get detailed system metrics including per-interface data"""
    metrics = await asyncio.to_thread(monitoring.get_current_metrics)
    if metrics:
        return {
            "success": True,
            "metrics": metrics.to_dict()
        }
    return {
        "success": False,
        "error": "Could not collect detailed metrics. Is psutil installed?"
    }


@app.get("/monitoring/interfaces/{interface_name}")
async def get_interface_details(interface_name: str):
    """Get detailed statistics for a specific network interface"""
    details = await asyncio.to_thread(monitoring.get_interface_details, interface_name)
    if details:
        return {
            "success": True,
            "interface": details
        }
    return {
        "success": False,
        "error": f"Interface '{interface_name}' not found"
    }


@app.get("/monitoring/interfaces/{interface_name}/history")
async def get_interface_history_endpoint(interface_name: str, hours: int = 1):
    """Get historical data for a specific interface"""
    history = await asyncio.to_thread(monitoring.get_interface_history, interface_name, hours)
    return {
        "success": True,
        "interface_name": interface_name,
        "hours": hours,
        "data": history
    }


@app.get("/monitoring/history/{metric_name}")
async def get_metric_history_endpoint(metric_name: str, hours: int = 1):
    """Get historical data for a specific metric"""
    history = await asyncio.to_thread(monitoring.get_metric_history, metric_name, hours)
    return {
        "success": True,
        "metric_name": metric_name,
        "hours": hours,
        "data": history
    }


# ============= AGENTIC WORKFLOW ENDPOINTS =============


@app.post("/workflow/create")
async def create_workflow(request: WorkflowRequest):
    """
    Create and execute an agentic workflow from a goal
    
    This endpoint:
    1. Uses LLM to plan steps for the goal
    2. Executes each step with appropriate tools
    3. Returns the complete result
    """
    try:
        # Check Ollama connection
        if not _health_cache.get("ollama_connected", False):
            connected = await llm_client.check_connection_async(use_cache=True)
            if not connected:
                return {
                    "success": False,
                    "error": "Ollama tidak terhubung. Pastikan Ollama sudah berjalan."
                }
        
        # Plan the workflow
        workflow = await planner.plan(request.goal)
        
        # Set the tool executor
        workflow.set_tool_executor(execute_tool)
        
        # Execute the workflow
        result = await workflow.execute()
        
        # Save to history and memory
        save_workflow(workflow)
        memory.remember("workflow", {
            "goal": request.goal,
            "success": result.success,
            "steps_completed": result.completed_steps,
            "duration": result.duration_seconds
        })
        
        # Learn from the result
        if result.success:
            memory.learn_from_success(
                goal=request.goal,
                steps=[s.name for s in workflow.steps],
                tools=[s.tool for s in workflow.steps]
            )
        
        return {
            "success": True,
            "workflow_id": workflow.id,
            "goal": request.goal,
            "status": workflow.status.value,
            "result": result.to_dict(),
            "steps": [s.to_dict() for s in workflow.steps]
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/workflow/list/history")
async def list_workflow_history(limit: int = 10):
    """Get list of past workflows"""
    workflows = get_workflow_history(limit)
    return {
        "count": len(workflows),
        "workflows": [
            {
                "id": w.id,
                "goal": w.goal,
                "status": w.status.value,
                "created_at": w.created_at,
                "completed_at": w.completed_at,
                "steps_count": len(w.steps)
            }
            for w in workflows
        ]
    }


@app.get("/workflow/memory/stats")
async def get_memory_stats():
    """Get workflow memory statistics"""
    return memory.get_stats()


@app.get("/workflow/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get status of a specific workflow"""
    workflow = get_workflow_by_id(workflow_id)
    
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return workflow.to_dict()


@app.post("/workflow/quick")
async def quick_workflow(request: WorkflowRequest):
    """
    Quick workflow execution for simple goals
    
    Combines planning and execution into a single fast response
    """
    try:
        # For simple queries, use the original agent's quick response
        if agent._is_simple_query(request.goal):
            response = await agent.quick_response(request.goal)
            return {
                "success": True,
                "mode": "quick",
                "response": response
            }
        
        # Otherwise, use full workflow
        workflow = await planner.plan(request.goal)
        workflow.set_tool_executor(execute_tool)
        result = await workflow.execute()
        save_workflow(workflow)
        
        return {
            "success": True,
            "mode": "workflow",
            "workflow_id": workflow.id,
            "summary": result.summary,
            "duration_seconds": result.duration_seconds
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.websocket("/workflow/stream")
async def stream_workflow(websocket: WebSocket):
    """
    WebSocket endpoint for streaming workflow execution with progress updates
    """
    await websocket.accept()
    
    async def progress_callback(workflow_id: str, step_id: str, status: str):
        """Send progress updates via websocket"""
        try:
            await websocket.send_json({
                "type": "progress",
                "workflow_id": workflow_id,
                "step_id": step_id,
                "status": status
            })
        except:
            pass
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            goal = message.get("goal", "")
            
            # Send planning status
            await websocket.send_json({"type": "status", "phase": "planning"})
            
            # Plan workflow
            workflow = await planner.plan(goal)
            workflow.set_tool_executor(execute_tool)
            workflow.set_progress_callback(progress_callback)
            
            # Send planned steps
            await websocket.send_json({
                "type": "planned",
                "workflow_id": workflow.id,
                "steps": [s.to_dict() for s in workflow.steps]
            })
            
            # Execute
            await websocket.send_json({"type": "status", "phase": "executing"})
            result = await workflow.execute()
            
            # Save
            save_workflow(workflow)
            
            # Send final result
            await websocket.send_json({
                "type": "complete",
                "result": result.to_dict()
            })
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass


# ============= INFRASTRUCTURE MONITORING ENDPOINTS =============

# --- Device Management ---

@app.get("/infra/devices")
async def list_devices(device_type: str = None, status: str = None):
    """List all registered devices with optional filtering"""
    devices = infrastructure.list_devices(device_type=device_type, status=status)
    return {
        "count": len(devices),
        "devices": [d.to_dict() for d in devices]
    }


@app.post("/infra/devices")
async def add_device(request: DeviceRequest):
    """Add a new device to monitoring"""
    device = infrastructure.add_device(
        name=request.name,
        ip=request.ip,
        device_type=request.type,
        description=request.description,
        location=request.location,
        ports_to_monitor=request.ports_to_monitor,
        check_interval=request.check_interval
    )
    
    return {
        "success": True,
        "message": f"Device '{device.name}' added",
        "device": device.to_dict()
    }


@app.get("/infra/devices/{device_id}")
async def get_device(device_id: str):
    """Get device details"""
    device = infrastructure.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return device.to_dict()


@app.put("/infra/devices/{device_id}")
async def update_device(device_id: str, request: DeviceRequest):
    """Update device configuration"""
    device = infrastructure.update_device(
        device_id,
        name=request.name,
        ip=request.ip,
        type=request.type,
        description=request.description,
        location=request.location,
        ports_to_monitor=request.ports_to_monitor,
        check_interval_seconds=request.check_interval
    )
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return {
        "success": True,
        "device": device.to_dict()
    }


@app.delete("/infra/devices/{device_id}")
async def delete_device(device_id: str):
    """Remove a device from monitoring"""
    success = infrastructure.remove_device(device_id)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return {"success": True, "message": "Device removed"}


@app.get("/infra/devices/{device_id}/status")
async def check_device_status(device_id: str):
    """Check device status immediately"""
    result = await scheduler.check_now(device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device = infrastructure.get_device(device_id)
    return {
        "device": device.to_dict() if device else None,
        "last_check": result.to_dict()
    }


@app.get("/infra/summary")
async def get_infrastructure_summary():
    """Get overall infrastructure status summary"""
    return infrastructure.get_status_summary()


# --- Monitoring Control ---

@app.post("/infra/monitor/start")
async def start_monitoring():
    """Start the automatic monitoring scheduler"""
    if scheduler.is_running:
        return {"success": True, "message": "Monitoring already running"}
    
    # Set alert callback
    scheduler.set_alert_callback(handle_device_alert)
    
    await scheduler.start()
    
    return {
        "success": True,
        "message": "Monitoring started",
        "devices_count": len(infrastructure.list_devices())
    }


@app.post("/infra/monitor/stop")
async def stop_monitoring():
    """Stop the automatic monitoring"""
    if not scheduler.is_running:
        return {"success": True, "message": "Monitoring not running"}
    
    await scheduler.stop()
    
    return {"success": True, "message": "Monitoring stopped"}


@app.get("/infra/monitor/status")
async def get_monitoring_status():
    """Get current monitoring status"""
    return {
        "running": scheduler.is_running,
        "devices_monitored": len(infrastructure.list_devices()),
        "last_results": {
            k: v.to_dict() for k, v in scheduler.get_all_results().items()
        }
    }


@app.post("/infra/monitor/check-all")
async def check_all_devices():
    """Immediately check all devices"""
    results = await scheduler.check_all_now()
    
    return {
        "success": True,
        "checked": len(results),
        "results": {k: v.to_dict() for k, v in results.items()}
    }


# --- Alerts ---

@app.get("/infra/alerts")
async def get_alerts(
    severity: str = None,
    device_id: str = None,
    unresolved_only: bool = True,
    limit: int = 50
):
    """Get alerts with optional filtering"""
    alerts = alert_manager.get_alerts(
        severity=severity,
        device_id=device_id,
        unresolved_only=unresolved_only,
        limit=limit
    )
    
    return {
        "count": len(alerts),
        "alerts": [a.to_dict() for a in alerts]
    }


@app.get("/infra/alerts/summary")
async def get_alerts_summary():
    """Get alert summary"""
    return alert_manager.get_summary()


@app.post("/infra/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, by: str = "user"):
    """Acknowledge an alert"""
    success = alert_manager.acknowledge(alert_id, by)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"success": True, "message": "Alert acknowledged"}


@app.post("/infra/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Resolve an alert"""
    success = alert_manager.resolve(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"success": True, "message": "Alert resolved"}


# --- Live Status WebSocket ---

@app.websocket("/infra/live")
async def infrastructure_live(websocket: WebSocket):
    """
    WebSocket for real-time infrastructure status updates
    
    Sends periodic updates with device statuses
    """
    await websocket.accept()
    
    try:
        # Send initial status
        await websocket.send_json({
            "type": "initial",
            "summary": infrastructure.get_status_summary(),
            "devices": [d.to_dict() for d in infrastructure.list_devices()],
            "alerts": [a.to_dict() for a in alert_manager.get_active_alerts()[:10]]
        })
        
        # Keep alive and send updates
        while True:
            await asyncio.sleep(5)  # Update every 5 seconds
            
            await websocket.send_json({
                "type": "update",
                "summary": infrastructure.get_status_summary(),
                "devices": [d.to_dict() for d in infrastructure.list_devices()],
                "alerts_count": len(alert_manager.get_active_alerts()),
                "monitoring_running": scheduler.is_running
            })
            
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# --- Config Export/Import ---

@app.get("/infra/config/export")
async def export_config():
    """Export device configuration as JSON"""
    return {
        "config": infrastructure.export_config()
    }


@app.post("/infra/config/import")
async def import_config(config: dict):
    """Import device configuration from JSON"""
    try:
        count = infrastructure.import_config(json.dumps(config))
        return {
            "success": True,
            "imported": count
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============= INVENTORY (NetOps Sentinel) ENDPOINTS =============


@app.get("/inventory")
async def get_inventory(vendor: str = None, enabled_only: bool = True):
    """Get all devices from inventory (Source of Truth)"""
    vendor_filter = None
    if vendor:
        try:
            vendor_filter = VendorType(vendor)
        except ValueError:
            pass
    
    devices = inventory.list_devices(vendor=vendor_filter, enabled_only=enabled_only)
    return {
        "count": len(devices),
        "devices": [d.to_dict() for d in devices]
    }


@app.get("/inventory/{device_ip}")
async def get_inventory_device(device_ip: str):
    """Get device info from inventory"""
    device = inventory.get_device(device_ip)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found in inventory")
    return device.to_dict()


class InventoryDeviceRequest(BaseModel):
    id: str
    name: str
    ip_address: str
    vendor: str = "unknown"
    role: str = "other"
    model: str = ""
    location: str = ""
    description: str = ""
    ssh_port: int = 22
    credential_id: str = "default"


@app.post("/inventory")
async def add_inventory_device(request: InventoryDeviceRequest):
    """Add device to inventory"""
    # Vendor alias mapping for convenience
    vendor_aliases = {
        "mikrotik": "mikrotik_routeros",
        "ubiquiti": "ubiquiti_edgerouter",
        "ubiquiti_edge": "ubiquiti_edgerouter",
        "cisco": "cisco_ios",
        "linux": "linux",
        "cisco_ios": "cisco_ios",
        "cisco_nxos": "cisco_nxos",
        "mikrotik_routeros": "mikrotik_routeros",
    }
    
    vendor_value = vendor_aliases.get(request.vendor.lower(), request.vendor)
    
    try:
        vendor_type = VendorType(vendor_value)
    except ValueError:
        vendor_type = VendorType.UNKNOWN
    
    try:
        device_role = DeviceRole(request.role)
    except ValueError:
        device_role = DeviceRole.OTHER
    
    device = DeviceInfo(
        id=request.id,
        name=request.name,
        ip_address=request.ip_address,
        vendor=vendor_type,
        role=device_role,
        model=request.model,
        location=request.location,
        description=request.description,
        ssh_port=request.ssh_port,
        credential_id=request.credential_id
    )
    success = inventory.add_device(device)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to add device (may already exist)")
    return {"success": True, "device": device.to_dict()}


@app.delete("/inventory/{device_ip}")
async def delete_inventory_device(device_ip: str):
    """Remove device from inventory"""
    success = inventory.delete_device(device_ip)
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True}


# ============= UNIFIED DEVICE COMMANDS =============


class DeviceCommandRequest(BaseModel):
    device_ip: str
    command: str  # Unified command name
    params: dict = {}


@app.post("/device/command")
async def execute_device_command(request: DeviceCommandRequest):
    """Execute unified command on a device"""
    try:
        cmd = UnifiedCommand(request.command)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown command: {request.command}")
    
    result = await connection_manager.execute_on_device(
        request.device_ip, cmd, request.params
    )
    return result.to_dict()


@app.get("/device/{device_ip}/interfaces")
async def get_device_interfaces(device_ip: str):
    """Get interfaces from network device"""
    result = await unified_commands.get_interfaces(device_ip)
    return result.to_dict()


@app.get("/device/{device_ip}/cpu-memory")
async def get_device_resources(device_ip: str):
    """Get CPU and memory usage from device"""
    result = await unified_commands.get_cpu_memory(device_ip)
    return result.to_dict()


@app.get("/device/{device_ip}/routing")
async def get_device_routing(device_ip: str):
    """Get routing table from device"""
    result = await unified_commands.get_routing_table(device_ip)
    return result.to_dict()


@app.get("/device/{device_ip}/arp")
async def get_device_arp(device_ip: str):
    """Get ARP table from device"""
    result = await unified_commands.get_arp_table(device_ip)
    return result.to_dict()


@app.get("/device/{device_ip}/logs")
async def get_device_logs(device_ip: str):
    """Get recent logs from device"""
    result = await unified_commands.get_logs(device_ip)
    return result.to_dict()


@app.post("/device/{device_ip}/ping")
async def ping_from_device(device_ip: str, target: str):
    """Ping target from device"""
    result = await unified_commands.ping(device_ip, target)
    return result.to_dict()


# ============= GUARDRAILS (Human-in-the-Loop) =============


class ActionPlanRequest(BaseModel):
    goal: str
    actions: List[dict]  # [{device_ip, command, description}]


@app.post("/guardrails/plan")
async def create_action_plan(request: ActionPlanRequest):
    """Create an execution plan requiring approval"""
    plan = guardrails.create_execution_plan(request.goal, request.actions)
    requires_approval = guardrails.requires_approval(plan)
    
    return {
        "plan_id": plan.id,
        "requires_approval": requires_approval,
        "preview": plan.generate_preview(),
        "overall_risk": plan.overall_risk.value,
        "actions": [a.to_dict() for a in plan.actions]
    }


@app.get("/guardrails/pending")
async def list_pending_plans():
    """List all pending execution plans"""
    plans = guardrails.list_pending_plans()
    return {
        "count": len(plans),
        "plans": [p.to_dict() for p in plans]
    }


@app.post("/guardrails/approve/{plan_id}")
async def approve_plan(plan_id: str, approved_by: str = "user"):
    """Approve an execution plan"""
    success = guardrails.approve_plan(plan_id, approved_by)
    if not success:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"success": True, "message": "Plan approved"}


@app.post("/guardrails/reject/{plan_id}")
async def reject_plan(plan_id: str, reason: str = ""):
    """Reject an execution plan"""
    success = guardrails.reject_plan(plan_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"success": True, "message": "Plan rejected"}


@app.post("/guardrails/validate")
async def validate_command(command: str):
    """Validate a command and get risk assessment"""
    is_valid, message, risk_level = guardrails.validate_command(command)
    return {
        "command": command,
        "is_valid": is_valid,
        "message": message,
        "risk_level": risk_level.value
    }


@app.get("/guardrails/status")
async def get_guardrails_status():
    """Get current guardrails status"""
    return {
        "max_iterations": guardrails.max_iterations,
        "pending_plans": len(guardrails.list_pending_plans()),
        "auto_approve_below": guardrails.auto_approve_below.value
    }


@app.get("/llm/info")
async def get_llm_info():
    """Get current LLM provider information"""
    return llm_client.get_provider_info()
