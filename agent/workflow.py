"""
Workflow Orchestration Engine

Manages multi-step agentic workflows with:
- Step dependency resolution
- Parallel and sequential execution
- State persistence
- Error handling and recovery
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from datetime import datetime
import asyncio
import json
import uuid


class StepStatus(Enum):
    """Status of a workflow step"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(Enum):
    """Status of the entire workflow"""
    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class WorkflowStep:
    """Individual step in a workflow"""
    id: str
    name: str
    description: str
    tool: str
    params: Dict[str, Any]
    depends_on: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retries: int = 0
    max_retries: int = 2
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tool": self.tool,
            "params": self.params,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retries": self.retries
        }
    
    def can_run(self, completed_steps: set) -> bool:
        """Check if all dependencies are satisfied"""
        return all(dep in completed_steps for dep in self.depends_on)


@dataclass
class WorkflowResult:
    """Result of workflow execution"""
    success: bool
    workflow_id: str
    goal: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    results: Dict[str, Any]
    summary: str
    duration_seconds: float
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "workflow_id": self.workflow_id,
            "goal": self.goal,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "results": self.results,
            "summary": self.summary,
            "duration_seconds": round(self.duration_seconds, 2)
        }


class Workflow:
    """
    Agentic Workflow Manager
    
    Orchestrates multi-step task execution with:
    - Dependency resolution
    - Parallel execution where possible
    - State management
    - Error recovery
    """
    
    def __init__(self, goal: str, workflow_id: str = None):
        self.id = workflow_id or str(uuid.uuid4())[:8]
        self.goal = goal
        self.steps: List[WorkflowStep] = []
        self.status = WorkflowStatus.CREATED
        self.state: Dict[str, Any] = {}  # Shared state between steps
        self.created_at = datetime.now().isoformat()
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self._tool_executor: Optional[Callable] = None
        self._progress_callback: Optional[Callable] = None
    
    def add_step(
        self,
        name: str,
        tool: str,
        params: Dict[str, Any],
        description: str = "",
        depends_on: List[str] = None
    ) -> str:
        """Add a step to the workflow"""
        step_id = f"step_{len(self.steps) + 1}"
        step = WorkflowStep(
            id=step_id,
            name=name,
            description=description or name,
            tool=tool,
            params=params,
            depends_on=depends_on or []
        )
        self.steps.append(step)
        return step_id
    
    def set_tool_executor(self, executor: Callable):
        """Set the function that executes tools"""
        self._tool_executor = executor
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self._progress_callback = callback
    
    async def _notify_progress(self, step: WorkflowStep, status: str):
        """Notify progress callback"""
        if self._progress_callback:
            try:
                if asyncio.iscoroutinefunction(self._progress_callback):
                    await self._progress_callback(self.id, step.id, status)
                else:
                    self._progress_callback(self.id, step.id, status)
            except Exception:
                pass
    
    def get_ready_steps(self) -> List[WorkflowStep]:
        """Get steps that are ready to execute"""
        completed = {s.id for s in self.steps if s.status == StepStatus.COMPLETED}
        return [
            s for s in self.steps 
            if s.status == StepStatus.PENDING and s.can_run(completed)
        ]
    
    async def execute_step(self, step: WorkflowStep) -> bool:
        """Execute a single step"""
        if not self._tool_executor:
            step.status = StepStatus.FAILED
            step.error = "No tool executor configured"
            return False
        
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now().isoformat()
        await self._notify_progress(step, "running")
        
        try:
            # Inject state variables into params
            resolved_params = self._resolve_params(step.params)
            
            # Execute the tool
            if asyncio.iscoroutinefunction(self._tool_executor):
                result = await self._tool_executor(step.tool, resolved_params)
            else:
                result = await asyncio.to_thread(
                    self._tool_executor, step.tool, resolved_params
                )
            
            step.result = result
            step.status = StepStatus.COMPLETED
            step.completed_at = datetime.now().isoformat()
            
            # Store result in state for dependent steps
            self.state[step.id] = result
            self.state[f"{step.id}_output"] = result.get("output", "")
            
            await self._notify_progress(step, "completed")
            return True
            
        except Exception as e:
            step.error = str(e)
            step.retries += 1
            
            if step.retries < step.max_retries:
                step.status = StepStatus.PENDING
                await self._notify_progress(step, "retrying")
                return False
            
            step.status = StepStatus.FAILED
            step.completed_at = datetime.now().isoformat()
            await self._notify_progress(step, "failed")
            return False
    
    def _resolve_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve parameter references to state values"""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                # Reference to state variable
                ref = value[2:-1]
                resolved[key] = self.state.get(ref, value)
            else:
                resolved[key] = value
        return resolved
    
    async def execute(self) -> WorkflowResult:
        """Execute the entire workflow"""
        start_time = datetime.now()
        self.status = WorkflowStatus.EXECUTING
        self.started_at = start_time.isoformat()
        
        max_iterations = len(self.steps) * 3  # Prevent infinite loops
        iterations = 0
        
        while iterations < max_iterations:
            iterations += 1
            
            # Get steps ready to run
            ready_steps = self.get_ready_steps()
            
            if not ready_steps:
                # Check if all done or stuck
                pending = [s for s in self.steps if s.status == StepStatus.PENDING]
                if not pending:
                    break
                # Check for circular dependency or all failed
                failed = [s for s in self.steps if s.status == StepStatus.FAILED]
                if len(failed) + len([s for s in self.steps if s.status == StepStatus.COMPLETED]) == len(self.steps):
                    break
                # Stuck - break
                break
            
            # Execute ready steps in parallel
            tasks = [self.execute_step(step) for step in ready_steps]
            await asyncio.gather(*tasks)
        
        # Calculate results
        end_time = datetime.now()
        self.completed_at = end_time.isoformat()
        
        completed = [s for s in self.steps if s.status == StepStatus.COMPLETED]
        failed = [s for s in self.steps if s.status == StepStatus.FAILED]
        
        success = len(failed) == 0 and len(completed) == len(self.steps)
        self.status = WorkflowStatus.COMPLETED if success else WorkflowStatus.FAILED
        
        # Build result summary
        results = {s.id: s.result for s in completed}
        summary = self._build_summary(completed, failed)
        
        return WorkflowResult(
            success=success,
            workflow_id=self.id,
            goal=self.goal,
            total_steps=len(self.steps),
            completed_steps=len(completed),
            failed_steps=len(failed),
            results=results,
            summary=summary,
            duration_seconds=(end_time - start_time).total_seconds()
        )
    
    def _build_summary(self, completed: List[WorkflowStep], failed: List[WorkflowStep]) -> str:
        """Build a human-readable summary"""
        lines = [f"## Workflow: {self.goal}\n"]
        
        if completed:
            lines.append("### ✅ Completed Steps")
            for step in completed:
                output = ""
                if step.result and step.result.get("output"):
                    output = f"\n```\n{step.result['output'][:300]}...\n```" if len(str(step.result.get('output', ''))) > 300 else f"\n```\n{step.result['output']}\n```"
                lines.append(f"- **{step.name}**: {step.description}{output}")
        
        if failed:
            lines.append("\n### ❌ Failed Steps")
            for step in failed:
                lines.append(f"- **{step.name}**: {step.error}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """Serialize workflow to dict"""
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }
    
    def to_json(self) -> str:
        """Serialize workflow to JSON"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# Workflow history storage (in-memory for now)
_workflow_history: List[Workflow] = []


def save_workflow(workflow: Workflow):
    """Save workflow to history"""
    _workflow_history.append(workflow)
    # Keep only last 50
    if len(_workflow_history) > 50:
        _workflow_history.pop(0)


def get_workflow_history(limit: int = 10) -> List[Workflow]:
    """Get recent workflows"""
    return _workflow_history[-limit:]


def get_workflow_by_id(workflow_id: str) -> Optional[Workflow]:
    """Get workflow by ID"""
    for w in reversed(_workflow_history):
        if w.id == workflow_id:
            return w
    return None
