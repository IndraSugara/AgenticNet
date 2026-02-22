"""
LangChain Remediation Tools

Tools for the agent to interact with remediation runbooks and
track remediation actions. Used during autonomous log watcher remediation.

Inspired by OpenClaw's autonomous workflow execution.
"""
from langchain_core.tools import tool
from typing import Optional


@tool
def get_remediation_runbook(anomaly_type: str) -> str:
    """
    Get the remediation runbook for a specific anomaly type.
    
    Args:
        anomaly_type: The anomaly pattern name (e.g., 'link_down', 'auth_failure', 'link_flap')
    
    Returns:
        Remediation instructions and allowed actions
    """
    from agent.log_watcher import REMEDIATION_RUNBOOKS
    
    runbook = REMEDIATION_RUNBOOKS.get(anomaly_type)
    if not runbook:
        available = ", ".join(REMEDIATION_RUNBOOKS.keys())
        return f"No runbook found for '{anomaly_type}'. Available types: {available}"
    
    result = f"=== Runbook: {anomaly_type} ===\n"
    result += f"Severity Threshold: {runbook['severity_threshold']}\n\n"
    result += f"Instructions:\n{runbook['prompt']}\n\n"
    result += f"Auto-execute (low-risk): {', '.join(runbook['auto_actions'])}\n"
    if runbook['requires_confirmation']:
        result += f"Requires confirmation: {', '.join(runbook['requires_confirmation'])}\n"
    else:
        result += "No high-risk actions in this runbook.\n"
    
    return result


@tool
def record_remediation_result(
    anomaly_id: str,
    device_ip: str,
    action_taken: str,
    success: bool,
    details: str = ""
) -> str:
    """
    Record the result of a remediation action for tracking and learning.
    
    Args:
        anomaly_id: The anomaly ID that was remediated
        device_ip: IP address of the device
        action_taken: Description of the action performed
        success: Whether the remediation was successful
        details: Additional details about the outcome
    
    Returns:
        Confirmation of the recorded result
    """
    from agent.log_watcher import log_watcher
    from datetime import datetime
    
    record = {
        "anomaly_id": anomaly_id,
        "device_ip": device_ip,
        "action_taken": action_taken,
        "success": success,
        "details": details,
        "timestamp": datetime.now().isoformat(),
    }
    
    log_watcher._remediation_history.append(record)
    
    # Keep max 100 records
    if len(log_watcher._remediation_history) > 100:
        log_watcher._remediation_history = log_watcher._remediation_history[-100:]
    
    status = "✅ Berhasil" if success else "❌ Gagal"
    return f"Remediation recorded: {status} — {action_taken} on {device_ip}"


@tool
def get_remediation_history(device_ip: Optional[str] = None, limit: int = 10) -> str:
    """
    Get history of past remediation actions for a device or all devices.
    
    Args:
        device_ip: Optional device IP to filter by. If None, returns all.
        limit: Maximum number of records to return (default: 10)
    
    Returns:
        Past remediation actions with outcomes
    """
    from agent.log_watcher import log_watcher
    
    history = log_watcher._remediation_history.copy()
    
    if device_ip:
        history = [h for h in history if h.get("device_ip") == device_ip]
    
    if not history:
        target = f" for {device_ip}" if device_ip else ""
        return f"No remediation history found{target}."
    
    history = history[-limit:]
    
    lines = [f"=== Remediation History ({len(history)} records) ==="]
    for h in history:
        status = "✅" if h.get("success", True) else "❌"
        lines.append(
            f"\n{status} [{h.get('timestamp', 'N/A')}] "
            f"Device: {h.get('device_ip', 'N/A')}\n"
            f"  Pattern: {h.get('pattern', h.get('anomaly_id', 'N/A'))}\n"
            f"  Action: {h.get('action_taken', h.get('agent_response', 'N/A')[:200])}"
        )
    
    return "\n".join(lines)


def get_remediation_tools() -> list:
    """Get all remediation tools"""
    return [
        get_remediation_runbook,
        record_remediation_result,
        get_remediation_history,
    ]
