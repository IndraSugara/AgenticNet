"""
LangChain Network Intelligence Tools

Tools for the agent to query and update the network intelligence system,
giving the agent awareness of what's "normal" and what happened before.

Inspired by OpenClaw's adaptive memory and context carryover.
"""
import json
from langchain_core.tools import tool
from typing import Optional


@tool
def save_diagnostic_result(
    device_ip: str,
    event_type: str,
    data: str,
    severity: str = "info"
) -> str:
    """
    Save a diagnostic or investigation result to network intelligence memory.
    Call this after completing an investigation or remediation to build device history.
    
    Args:
        device_ip: IP address of the device
        event_type: Type of event (e.g., 'latency_spike', 'interface_down', 'auth_failure', 
                    'remediation_success', 'health_check', 'investigation')
        data: Description of the findings (plain text or JSON string)
        severity: Severity level ('info', 'warning', 'critical')
    
    Returns:
        Confirmation that the result was saved
    """
    from agent.long_term_memory import long_term_memory
    
    # Try to parse as JSON dict, otherwise wrap as string
    try:
        event_data = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        event_data = {"description": str(data)}
    
    event_id = long_term_memory.record_event(
        device_ip=device_ip,
        event_type=event_type,
        event_data=event_data,
        severity=severity,
        source="agent"
    )
    
    return f"✅ Diagnostic result saved (event #{event_id}) for {device_ip} — type: {event_type}"


@tool
def query_device_history(
    device_ip: str,
    event_type: Optional[str] = None,
    limit: int = 10
) -> str:
    """
    Query the history of past events/diagnostics for a device.
    Use this to check what happened to a device before (previous issues, remediations, etc.)
    
    Args:
        device_ip: IP address of the device
        event_type: Optional filter by event type (e.g., 'interface_down', 'latency_spike')
        limit: Maximum number of records to return (default: 10)
    
    Returns:
        Past events and diagnostics for the device
    """
    from agent.long_term_memory import long_term_memory
    
    history = long_term_memory.get_device_history(device_ip, event_type, limit)
    
    if not history:
        filter_text = f" of type '{event_type}'" if event_type else ""
        return f"No event history found for {device_ip}{filter_text}."
    
    lines = [f"=== Event History for {device_ip} ({len(history)} records) ==="]
    for event in history:
        severity_emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(
            event["severity"], "📌"
        )
        lines.append(
            f"\n{severity_emoji} [{event['created_at']}] {event['event_type']}"
            f"\n  Source: {event['source']}"
            f"\n  Data: {json.dumps(event['event_data'], indent=2)[:300]}"
        )
    
    return "\n".join(lines)


@tool
def get_network_baseline(
    device_ip: str,
    metric: str
) -> str:
    """
    Get the learned "normal" baseline for a device metric.
    The system learns baselines automatically from past measurements.
    
    Args:
        device_ip: IP address of the device
        metric: Metric type (e.g., 'latency', 'bandwidth_in', 'bandwidth_out', 'cpu', 'memory')
    
    Returns:
        Baseline value, thresholds, and sample count
    """
    from agent.long_term_memory import long_term_memory
    
    baseline = long_term_memory.get_baseline(device_ip, metric)
    
    if not baseline:
        return (
            f"No baseline found for {device_ip} / {metric}. "
            f"Use check_anomaly_against_baseline to start building a baseline."
        )
    
    return (
        f"=== Baseline: {device_ip} / {metric} ===\n"
        f"Normal value: {baseline['baseline_value']:.2f}\n"
        f"Threshold low: {baseline['threshold_low']:.2f}\n"
        f"Threshold high: {baseline['threshold_high']:.2f}\n"
        f"Samples: {baseline['sample_count']}\n"
        f"Last updated: {baseline['updated_at']}"
    )


@tool
def check_anomaly_against_baseline(
    device_ip: str,
    metric: str,
    current_value: float
) -> str:
    """
    Check if a current metric value is anomalous compared to the learned baseline.
    Also updates the baseline with this new measurement for future reference.
    
    Args:
        device_ip: IP address of the device
        metric: Metric type (e.g., 'latency', 'bandwidth_in', 'bandwidth_out')
        current_value: The current measured value
    
    Returns:
        Whether the value is anomalous and comparison details
    """
    from agent.long_term_memory import long_term_memory
    
    # Check against baseline
    result = long_term_memory.is_anomalous(device_ip, metric, current_value)
    
    # Update baseline with new measurement (learning)
    long_term_memory.update_baseline(device_ip, metric, current_value)
    
    if result["anomalous"]:
        return (
            f"🚨 ANOMALI TERDETEKSI: {device_ip} / {metric}\n"
            f"Current: {current_value}\n"
            f"Baseline: {result.get('baseline_value', 'N/A'):.2f}\n"
            f"Range: {result.get('threshold_low', 0):.2f} - {result.get('threshold_high', 0):.2f}\n"
            f"Reason: {result['reason']}\n"
            f"(Baseline updated with this measurement)"
        )
    else:
        baseline_info = f" (baseline: {result.get('baseline_value', 'N/A')})" if result.get('baseline_value') else ""
        return (
            f"✅ Normal: {device_ip} / {metric} = {current_value}{baseline_info}\n"
            f"{result['reason']}\n"
            f"(Baseline updated with this measurement)"
        )


def get_intelligence_tools() -> list:
    """Get all network intelligence tools"""
    return [
        save_diagnostic_result,
        query_device_history,
        get_network_baseline,
        check_anomaly_against_baseline,
    ]
