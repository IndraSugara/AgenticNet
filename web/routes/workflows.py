"""
Workflow Routes

Endpoints for:
- Direct tool execution
- Pending high-risk action management
- Goal-based workflow execution via LangGraph agent
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio
import json

from agent.langgraph_agent import network_agent
from tools.network_tools import network_tools

router = APIRouter()


# --- Request/Response Models ---

class ToolRequest(BaseModel):
    tool: str
    params: dict


class WorkflowRequest(BaseModel):
    goal: str
    thread_id: str = "workflow"


class WorkflowResponse(BaseModel):
    success: bool
    goal: str
    response: str
    timing: Optional[dict] = None


# --- Tool Execution ---

@router.post("/tools/run")
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
    
    try:
        result = await asyncio.to_thread(tool_map[tool_name], params)
        return {
            "tool": tool_name,
            "success": result.success,
            "output": result.output,
            "error": result.error
        }
    except Exception as e:
        return {"tool": tool_name, "success": False, "output": "", "error": str(e)}


# --- Pending Actions ---

@router.get("/tools/pending")
async def list_pending_actions():
    """List all pending high-risk actions awaiting confirmation"""
    from tools.pending_actions import pending_store
    return {"success": True, "actions": pending_store.list_pending()}


@router.post("/tools/confirm/{action_id}")
async def confirm_pending_action(action_id: str):
    """Confirm and execute a pending high-risk action"""
    from tools.pending_actions import pending_store
    from tools.unified_commands import unified_commands
    
    action = pending_store.get(action_id)
    if not action:
        return {"success": False, "error": f"Action '{action_id}' tidak ditemukan atau sudah expired"}
    
    if action.confirmed:
        return {"success": False, "error": f"Action '{action_id}' sudah dieksekusi"}
    
    action.confirmed = True
    try:
        if action.tool_name == "disable_interface":
            result = network_tools.disable_interface(**action.params)
            return {"success": result.success, "output": result.output, "error": result.error}
        elif action.tool_name == "enable_interface":
            result = network_tools.enable_interface(**action.params)
            return {"success": result.success, "output": result.output, "error": result.error}
        elif action.tool_name == "shutdown_remote_interface":
            result = await unified_commands.shutdown_interface(**action.params)
            return {"success": result.success, "data": result.data, "error": result.error}
        elif action.tool_name == "enable_remote_interface":
            result = await unified_commands.no_shutdown_interface(**action.params)
            return {"success": result.success, "data": result.data, "error": result.error}
        else:
            return {"success": False, "error": f"Unknown tool: {action.tool_name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/tools/cancel/{action_id}")
async def cancel_pending_action(action_id: str):
    """Cancel a pending high-risk action"""
    from tools.pending_actions import pending_store
    return pending_store.cancel(action_id)


# --- Workflow Endpoints (via LangGraph Agent) ---

@router.post("/workflow/create")
async def create_workflow(request: WorkflowRequest):
    """
    Execute a goal using the LangGraph agent.
    
    The agent autonomously decides which tools to call based on the goal.
    """
    try:
        from web.routes.health import _health_cache
        if not _health_cache.get("ollama_connected", False):
            from web.routes.health import _check_ollama_connection
            connected = await _check_ollama_connection()
            if not connected:
                return {"success": False, "error": "Ollama tidak terhubung. Pastikan Ollama sudah berjalan."}
        
        response_text = await network_agent.ainvoke(request.goal, request.thread_id)
        
        return {
            "success": True,
            "goal": request.goal,
            "response": response_text,
            "timing": {"mode": "langgraph"}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/workflow/quick")
async def quick_workflow(request: WorkflowRequest):
    """Quick workflow execution — same as create but lighter response"""
    try:
        response_text = await network_agent.ainvoke(request.goal, request.thread_id)
        
        return {
            "success": True,
            "mode": "langgraph",
            "summary": response_text
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.websocket("/workflow/stream")
async def stream_workflow(websocket: WebSocket):
    """WebSocket endpoint for streaming workflow execution via LangGraph agent"""
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            goal = message.get("goal", "")
            thread_id = message.get("thread_id", "workflow")
            
            await websocket.send_json({"type": "status", "phase": "processing"})
            
            full_response = ""
            async for chunk in network_agent.astream(goal, thread_id):
                full_response += chunk
                await websocket.send_json({
                    "type": "chunk",
                    "content": chunk
                })
            
            await websocket.send_json({
                "type": "complete",
                "response": full_response,
                "timing": {"mode": "langgraph_stream"}
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
