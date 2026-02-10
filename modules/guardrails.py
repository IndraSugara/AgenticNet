"""
Guardrails Module - Security Controls for Destructive Actions

Implements:
- Command risk classification
- Execution plan generation
- Human-in-the-Loop approval workflow
- Max iteration limits
"""
import asyncio
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from datetime import datetime
import json


class RiskLevel(Enum):
    """Risk levels for commands"""
    INFO = "info"           # Read-only, no risk
    LOW = "low"             # Minor changes
    MEDIUM = "medium"       # Reversible changes
    HIGH = "high"           # Significant changes
    CRITICAL = "critical"   # Potentially destructive


@dataclass
class PlannedAction:
    """Single action in an execution plan"""
    id: int
    device_ip: str
    command: str
    description: str
    risk_level: RiskLevel
    rollback_command: Optional[str] = None
    estimated_impact: str = ""
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_ip": self.device_ip,
            "command": self.command,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "rollback_command": self.rollback_command,
            "estimated_impact": self.estimated_impact
        }


@dataclass
class ExecutionPlan:
    """Complete execution plan requiring approval"""
    id: str
    goal: str
    actions: List[PlannedAction] = field(default_factory=list)
    overall_risk: RiskLevel = RiskLevel.INFO
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    approved: bool = False
    approved_by: Optional[str] = None
    approval_time: Optional[str] = None
    executed: bool = False
    execution_result: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "actions": [a.to_dict() for a in self.actions],
            "overall_risk": self.overall_risk.value,
            "created_at": self.created_at,
            "approved": self.approved,
            "approved_by": self.approved_by,
            "approval_time": self.approval_time,
            "executed": self.executed,
            "execution_result": self.execution_result
        }
    
    def generate_preview(self) -> str:
        """Generate human-readable execution preview"""
        lines = [
            f"# Execution Plan: {self.goal}",
            f"**Risk Level**: {self.overall_risk.value.upper()}",
            f"**Actions**: {len(self.actions)}",
            "",
            "## Planned Steps:",
        ]
        
        for action in self.actions:
            risk_emoji = {
                RiskLevel.INFO: "ℹ️",
                RiskLevel.LOW: "🟢",
                RiskLevel.MEDIUM: "🟡",
                RiskLevel.HIGH: "🟠",
                RiskLevel.CRITICAL: "🔴",
            }
            
            lines.append(
                f"{action.id}. {risk_emoji.get(action.risk_level, '⚪')} "
                f"**{action.description}**"
            )
            lines.append(f"   - Device: `{action.device_ip}`")
            lines.append(f"   - Command: `{action.command}`")
            if action.rollback_command:
                lines.append(f"   - Rollback: `{action.rollback_command}`")
            lines.append("")
        
        return "\n".join(lines)


class CommandClassifier:
    """
    Classifies commands by risk level
    """
    
    # Pattern-based risk classification
    RISK_PATTERNS = {
        RiskLevel.CRITICAL: [
            r"(reload|reboot|reset|factory)",
            r"(delete|erase|format|no\s+)",
            r"(shutdown|disable)\s+(all|system)",
            r"write\s+erase",
            r"crypto\s+key\s+zeroize",
        ],
        RiskLevel.HIGH: [
            r"(shutdown|disable)\s+\w+",
            r"(no\s+)?(switchport|vlan|trunk)",
            r"(ip\s+route|route\s+add|route\s+delete)",
            r"(access-list|acl|firewall)",
            r"(spanning-tree|stp)",
            r"snmp|radius|tacacs",
        ],
        RiskLevel.MEDIUM: [
            r"(interface|set|configure)",
            r"(enable|disable)\s+\w+",
            r"(ip\s+address|address)",
            r"description",
            r"mtu",
        ],
        RiskLevel.LOW: [
            r"(ping|traceroute|tracert)",
            r"(show|display|get|print)",
            r"(ssh|telnet)",
            r"(debug)",
        ],
    }
    
    # Commands that need special handling
    ALWAYS_BLOCKED = [
        r"format.*flash",
        r"erase.*startup",
        r"delete.*running",
        r"crypto.*destroy",
        r"(rm|del|delete)\s+-rf?\s+/",
    ]
    
    @classmethod
    def classify(cls, command: str) -> RiskLevel:
        """
        Classify command risk level
        
        Args:
            command: Command string to classify
            
        Returns:
            RiskLevel enum
        """
        command_lower = command.lower().strip()
        
        # Check from highest to lowest risk
        for risk_level in [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]:
            patterns = cls.RISK_PATTERNS.get(risk_level, [])
            for pattern in patterns:
                if re.search(pattern, command_lower, re.IGNORECASE):
                    return risk_level
        
        return RiskLevel.INFO
    
    @classmethod
    def is_blocked(cls, command: str) -> tuple[bool, str]:
        """
        Check if command should be completely blocked
        
        Returns:
            (is_blocked, reason)
        """
        command_lower = command.lower()
        
        for pattern in cls.ALWAYS_BLOCKED:
            if re.search(pattern, command_lower, re.IGNORECASE):
                return True, f"Command matches blocked pattern: {pattern}"
        
        return False, ""
    
    @classmethod
    def is_read_only(cls, command: str) -> bool:
        """Check if command is read-only (safe without approval)"""
        risk = cls.classify(command)
        return risk in [RiskLevel.INFO, RiskLevel.LOW]
    
    @classmethod
    def get_rollback_command(cls, command: str, vendor: str = "cisco_ios") -> Optional[str]:
        """
        Generate rollback command for reversible operations
        """
        command_lower = command.lower()
        
        # Interface shutdown -> no shutdown
        if "shutdown" in command_lower and "no shutdown" not in command_lower:
            return command.replace("shutdown", "no shutdown")
        
        # no shutdown -> shutdown  
        if "no shutdown" in command_lower:
            return command.replace("no shutdown", "shutdown")
        
        # Interface disable -> enable (Mikrotik)
        if "/interface disable" in command_lower:
            return command.replace("disable", "enable")
        
        if "/interface enable" in command_lower:
            return command.replace("enable", "disable")
        
        return None


class GuardrailsModule:
    """
    Security guardrails for agent actions
    
    Provides:
    - Risk assessment
    - Execution plan generation
    - Human-in-the-Loop approval workflow
    - Iteration limits
    """
    
    def __init__(
        self, 
        max_iterations: int = 5,
        auto_approve_below: RiskLevel = RiskLevel.LOW,
        approval_callback: Optional[Callable] = None
    ):
        self.max_iterations = max_iterations
        self.auto_approve_below = auto_approve_below
        self.approval_callback = approval_callback
        self.pending_plans: Dict[str, ExecutionPlan] = {}
        self.iteration_counts: Dict[str, int] = {}
        self._plan_counter = 0
    
    def check_iteration_limit(self, session_id: str) -> tuple[bool, int]:
        """
        Check if session has exceeded iteration limit
        
        Returns:
            (exceeded, current_count)
        """
        count = self.iteration_counts.get(session_id, 0)
        return count >= self.max_iterations, count
    
    def increment_iteration(self, session_id: str) -> int:
        """Increment and return new iteration count"""
        self.iteration_counts[session_id] = self.iteration_counts.get(session_id, 0) + 1
        return self.iteration_counts[session_id]
    
    def reset_iterations(self, session_id: str):
        """Reset iteration count for session"""
        self.iteration_counts[session_id] = 0
    
    def assess_risk(self, actions: List[Dict[str, str]]) -> RiskLevel:
        """
        Assess overall risk level for a set of actions
        
        Args:
            actions: List of {command, device_ip} dicts
            
        Returns:
            Highest risk level among all actions
        """
        highest_risk = RiskLevel.INFO
        
        for action in actions:
            cmd = action.get("command", "")
            risk = CommandClassifier.classify(cmd)
            
            if risk.value > highest_risk.value:  # Compare enum values
                highest_risk = risk
        
        return highest_risk
    
    def create_execution_plan(
        self, 
        goal: str, 
        actions: List[Dict[str, Any]]
    ) -> ExecutionPlan:
        """
        Create an execution plan requiring approval
        
        Args:
            goal: What the agent is trying to achieve
            actions: List of planned actions
            
        Returns:
            ExecutionPlan object
        """
        self._plan_counter += 1
        plan_id = f"plan_{self._plan_counter}_{int(datetime.now().timestamp())}"
        
        planned_actions = []
        max_risk = RiskLevel.INFO
        
        for i, action in enumerate(actions):
            command = action.get("command", "")
            device_ip = action.get("device_ip", "")
            description = action.get("description", command)
            
            risk = CommandClassifier.classify(command)
            if risk.value > max_risk.value:
                max_risk = risk
            
            planned_actions.append(PlannedAction(
                id=i + 1,
                device_ip=device_ip,
                command=command,
                description=description,
                risk_level=risk,
                rollback_command=CommandClassifier.get_rollback_command(command),
                estimated_impact=action.get("impact", "")
            ))
        
        plan = ExecutionPlan(
            id=plan_id,
            goal=goal,
            actions=planned_actions,
            overall_risk=max_risk
        )
        
        # Store for later approval
        self.pending_plans[plan_id] = plan
        
        return plan
    
    def requires_approval(self, plan: ExecutionPlan) -> bool:
        """Check if plan requires human approval"""
        # Compare risk level using value comparison
        risk_order = [RiskLevel.INFO, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        plan_index = risk_order.index(plan.overall_risk)
        threshold_index = risk_order.index(self.auto_approve_below)
        
        return plan_index > threshold_index
    
    async def request_approval(self, plan: ExecutionPlan) -> bool:
        """
        Request human approval for execution plan
        
        This will block until approval is received or denied
        """
        if self.approval_callback:
            return await self.approval_callback(plan)
        
        # Default: store and wait for external approval
        self.pending_plans[plan.id] = plan
        return False  # Not auto-approved
    
    def approve_plan(self, plan_id: str, approved_by: str = "user") -> bool:
        """
        Approve a pending execution plan
        
        Args:
            plan_id: Plan identifier
            approved_by: Who approved
            
        Returns:
            True if plan was found and approved
        """
        if plan_id not in self.pending_plans:
            return False
        
        plan = self.pending_plans[plan_id]
        plan.approved = True
        plan.approved_by = approved_by
        plan.approval_time = datetime.now().isoformat()
        
        return True
    
    def reject_plan(self, plan_id: str, reason: str = "") -> bool:
        """
        Reject a pending execution plan
        """
        if plan_id in self.pending_plans:
            del self.pending_plans[plan_id]
            return True
        return False
    
    def get_pending_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a pending plan by ID"""
        return self.pending_plans.get(plan_id)
    
    def list_pending_plans(self) -> List[ExecutionPlan]:
        """List all pending plans"""
        return list(self.pending_plans.values())
    
    def validate_command(self, command: str) -> tuple[bool, str, RiskLevel]:
        """
        Validate a command before execution
        
        Returns:
            (is_valid, message, risk_level)
        """
        # Check if blocked
        is_blocked, reason = CommandClassifier.is_blocked(command)
        if is_blocked:
            return False, f"❌ Command blocked: {reason}", RiskLevel.CRITICAL
        
        # Classify risk
        risk = CommandClassifier.classify(command)
        
        if risk == RiskLevel.CRITICAL:
            return True, "⚠️ CRITICAL: This command may have severe impact", risk
        elif risk == RiskLevel.HIGH:
            return True, "⚠️ HIGH RISK: This command may significantly affect network", risk
        elif risk == RiskLevel.MEDIUM:
            return True, "⚡ MEDIUM RISK: This command will modify configuration", risk
        elif risk == RiskLevel.LOW:
            return True, "✅ LOW RISK: Minor impact expected", risk
        else:
            return True, "ℹ️ INFO: Read-only command", risk
    
    def format_for_agent(self) -> str:
        """Format guardrails status for agent context"""
        lines = ["## Security Guardrails Active\n"]
        
        lines.append(f"- Max iterations per session: **{self.max_iterations}**")
        lines.append(f"- Auto-approve below: **{self.auto_approve_below.value}**")
        lines.append(f"- Pending approvals: **{len(self.pending_plans)}**")
        
        if self.pending_plans:
            lines.append("\n### Pending Plans:")
            for plan_id, plan in list(self.pending_plans.items())[:3]:
                lines.append(f"- `{plan_id}`: {plan.goal} ({plan.overall_risk.value})")
        
        return "\n".join(lines)


# Singleton instance
guardrails = GuardrailsModule()
