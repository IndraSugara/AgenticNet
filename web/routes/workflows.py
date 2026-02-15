"""
Workflow Routes

Endpoints for agentic workflow creation, execution, and history.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import asyncio
import json

from agent.llm_client import llm_client
from agent.workflow import Workflow, save_workflow, get_workflow_history, get_workflow_by_id
from agent.planner import planner
from agent.executor import execute_tool
from agent.memory import memory
from tools.network_tools import network_tools

router = APIRouter()


# --- Request/Response Models ---

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


# --- Workflow Endpoints ---

@router.post("/workflow/create")
async def create_workflow(request: WorkflowRequest):
    """Create and execute an agentic workflow from a goal"""
    try:
        from web.routes.health import _health_cache
        if not _health_cache.get("ollama_connected", False):
            connected = await llm_client.check_connection_async(use_cache=True)
            if not connected:
                return {"success": False, "error": "Ollama tidak terhubung. Pastikan Ollama sudah berjalan."}
        
        workflow = await planner.plan(request.goal)
        workflow.set_tool_executor(execute_tool)
        result = await workflow.execute()
        
        save_workflow(workflow)
        memory.remember("workflow", {
            "goal": request.goal,
            "success": result.success,
            "steps_completed": result.completed_steps,
            "duration": result.duration_seconds
        })
        
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
        return {"success": False, "error": str(e)}


@router.get("/workflow/list/history")
async def list_workflow_history(limit: int = 10):
    """Get list of past workflows"""
    workflows = get_workflow_history(limit)
    return {
        "count": len(workflows),
        "workflows": [{
            "id": w.id,
            "goal": w.goal,
            "status": w.status.value,
            "created_at": w.created_at,
            "completed_at": w.completed_at,
            "steps_count": len(w.steps)
        } for w in workflows]
    }


@router.get("/workflow/memory/stats")
async def get_memory_stats():
    """Get workflow memory statistics"""
    return memory.get_stats()


@router.get("/workflow/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get status of a specific workflow"""
    workflow = get_workflow_by_id(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow.to_dict()


@router.post("/workflow/quick")
async def quick_workflow(request: WorkflowRequest):
    """Quick workflow execution for simple goals"""
    try:
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
        return {"success": False, "error": str(e)}


@router.websocket("/workflow/stream")
async def stream_workflow(websocket: WebSocket):
    """WebSocket endpoint for streaming workflow execution with progress updates"""
    await websocket.accept()
    
    async def progress_callback(workflow_id: str, step_id: str, status: str):
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
            
            await websocket.send_json({"type": "status", "phase": "planning"})
            
            workflow = await planner.plan(goal)
            workflow.set_tool_executor(execute_tool)
            workflow.set_progress_callback(progress_callback)
            
            await websocket.send_json({
                "type": "planned",
                "workflow_id": workflow.id,
                "steps": [s.to_dict() for s in workflow.steps]
            })
            
            await websocket.send_json({"type": "status", "phase": "executing"})
            result = await workflow.execute()
            save_workflow(workflow)
            
            await websocket.send_json({
                "type": "complete",
                "result": result.to_dict()
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
