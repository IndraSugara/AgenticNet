"""
Guardrails Routes

Endpoints for human-in-the-loop action approval and risk assessment.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from modules.guardrails import guardrails, RiskLevel, ExecutionPlan

router = APIRouter()


# --- Request Models ---

class ActionPlanRequest(BaseModel):
    goal: str
    actions: List[dict]  # [{device_ip, command, description}]


# --- Guardrails Endpoints ---

@router.post("/guardrails/plan")
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


@router.get("/guardrails/pending")
async def list_pending_plans():
    """List all pending execution plans"""
    plans = guardrails.list_pending_plans()
    return {"count": len(plans), "plans": [p.to_dict() for p in plans]}


@router.post("/guardrails/approve/{plan_id}")
async def approve_plan(plan_id: str, approved_by: str = "user"):
    """Approve an execution plan"""
    success = guardrails.approve_plan(plan_id, approved_by)
    if not success:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"success": True, "message": "Plan approved"}


@router.post("/guardrails/reject/{plan_id}")
async def reject_plan(plan_id: str, reason: str = ""):
    """Reject an execution plan"""
    success = guardrails.reject_plan(plan_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"success": True, "message": "Plan rejected"}


@router.post("/guardrails/validate")
async def validate_command(command: str):
    """Validate a command and get risk assessment"""
    is_valid, message, risk_level = guardrails.validate_command(command)
    return {
        "command": command,
        "is_valid": is_valid,
        "message": message,
        "risk_level": risk_level.value
    }


@router.get("/guardrails/status")
async def get_guardrails_status():
    """Get current guardrails status"""
    return {
        "max_iterations": guardrails.max_iterations,
        "pending_plans": len(guardrails.list_pending_plans()),
        "auto_approve_below": guardrails.auto_approve_below.value
    }
