"""
LangChain Report Tools

Tools for generating network reports via the agent.
"""
from langchain_core.tools import tool

from agent.report_generator import report_generator


@tool
def generate_network_report(period: str = "today") -> str:
    """
    Generate a network health report.
    
    Args:
        period: Report period - today, week, or month
    
    Returns:
        Markdown formatted network report
    """
    try:
        report = report_generator.generate_network_health_report(period)
        return report
    except Exception as e:
        return f"❌ Error generating report: {str(e)}"


@tool
def generate_device_report(device_id: str) -> str:
    """
    Generate a detailed report for a specific device.
    
    Args:
        device_id: Device ID or IP address
    
    Returns:
        Device-specific report
    """
    try:
        report = report_generator.generate_device_report(device_id)
        return report
    except Exception as e:
        return f"❌ Error generating device report: {str(e)}"


@tool
def generate_weekly_summary() -> str:
    """
    Generate a weekly network summary report.
    
    Returns:
        Weekly summary report
    """
    try:
        report = report_generator.generate_weekly_summary()
        return report
    except Exception as e:
        return f"❌ Error generating weekly summary: {str(e)}"


@tool
def save_report_to_file(report_content: str, report_name: str) -> str:
    """
    Save a report to a file.
    
    Args:
        report_content: The report content (markdown)
        report_name: Name for the report file
    
    Returns:
        Path to saved file
    """
    try:
        filepath = report_generator.save_report(
            content=report_content,
            name=report_name,
            format="md"
        )
        return f"✅ Report saved to: {filepath}"
    except Exception as e:
        return f"❌ Error saving report: {str(e)}"


@tool
def export_report_pdf(period: str = "today") -> str:
    """
    Generate and export a network report as PDF.
    
    Args:
        period: Report period - today, week, or month
    
    Returns:
        Path to PDF file or error message
    """
    try:
        # Generate markdown report first
        report = report_generator.generate_network_health_report(period)
        
        # Try to export to PDF
        filename = f"network_report_{period}.pdf"
        filepath = report_generator.export_to_pdf(report, filename)
        
        if filepath:
            return f"""✅ PDF Report Generated

**File:** {filepath}

The report has been saved as a PDF document."""
        else:
            # Fallback - save as markdown
            filepath = report_generator.save_report(report, f"network_report_{period}", "md")
            return f"""⚠️ PDF export not available (ReportLab not installed)

Report saved as Markdown instead:
**File:** {filepath}

Install `reportlab` for PDF support: `pip install reportlab`"""
    except Exception as e:
        return f"❌ Error exporting PDF: {str(e)}"


@tool
def get_quick_status() -> str:
    """
    Get a quick one-line network status summary.
    
    Returns:
        Brief status summary
    """
    try:
        from agent.infrastructure import infrastructure
        from agent.alerts import alert_manager
        
        devices = infrastructure.list_devices()
        online = sum(1 for d in devices if d.status and d.status.value == "online")
        offline = sum(1 for d in devices if d.status and d.status.value == "offline")
        
        alerts = alert_manager.get_unacknowledged_count()
        
        status = []
        
        # Overall health indicator
        if offline == 0 and alerts == 0:
            status.append("✅ All systems healthy")
        elif offline > 0:
            status.append(f"❌ {offline} device(s) offline")
        if alerts > 0:
            status.append(f"🚨 {alerts} unacked alert(s)")
        
        return f"**Quick Status:** {' | '.join(status)} | {online}/{len(devices)} devices online"
    except Exception as e:
        return f"❌ Error: {str(e)}"


def get_report_tools() -> list:
    """Get all report-related tools"""
    return [
        generate_network_report,
        generate_device_report,
        generate_weekly_summary,
        save_report_to_file,
        export_report_pdf,
        get_quick_status,
    ]
