"""
Application Log Viewer Routes

REST API endpoints for viewing AgenticNet application logs from the dashboard.
"""
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import Optional
import asyncio
import os

from agent.logging_config import read_log_lines, LOG_FILE

router = APIRouter()


@router.get("/logs/app")
async def get_app_logs(
    level: Optional[str] = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    search: Optional[str] = Query(None, description="Text search filter"),
    limit: int = Query(100, ge=1, le=500, description="Max entries to return")
):
    """Get application log entries with optional filtering."""
    logs = read_log_lines(level=level, search=search, limit=limit)
    return {
        "logs": logs,
        "total": len(logs),
        "log_file": LOG_FILE
    }


@router.get("/logs/app/stream")
async def stream_app_logs():
    """SSE stream for real-time log tailing."""
    async def event_generator():
        if not os.path.exists(LOG_FILE):
            yield f"data: {{}}\n\n"
            return
        
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            # Seek to end of file
            f.seek(0, 2)
            
            while True:
                line = f.readline()
                if line:
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"
                else:
                    await asyncio.sleep(1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
