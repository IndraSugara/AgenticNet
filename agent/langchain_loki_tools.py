"""
LangChain Loki Tool for AgenticNet

Allows the LangGraph agent to query network logs from Loki
using LogQL — the query language for Loki.
"""
import time
from typing import Optional

import httpx
from langchain_core.tools import tool

from agent.logging_config import get_logger

logger = get_logger("loki_tool")


def _get_loki_url() -> str:
    try:
        from config import config
        return getattr(config, "loki_url", None) or "http://loki:3100"
    except Exception:
        return "http://loki:3100"


@tool
def query_loki(logql: str, since_minutes: int = 10, limit: int = 100) -> str:
    """
    Query network device logs dari Loki menggunakan LogQL.

    Gunakan tool ini untuk:
    - Melihat log terbaru dari device tertentu
    - Mencari error atau event tertentu di log
    - Menginvestigasi anomaly berdasarkan log historis

    Args:
        logql: LogQL query string. Contoh:
               '{job="syslog"}' — semua log
               '{job="syslog"} |= "error"' — filter error
               '{job="syslog", "host.name"="router1"}' — device tertentu
               '{job="syslog"} |~ "BGP|OSPF"' — routing events
               '{job="syslog"} |= "LOGIN FAILED"' — auth failures
        since_minutes: Rentang waktu mundur dari sekarang (default: 10 menit)
        limit: Jumlah maksimal log entries yang dikembalikan (default: 100)

    Returns:
        Log entries yang cocok, atau pesan error jika Loki tidak tersedia
    """
    loki_url = _get_loki_url()
    end_ts = int(time.time())
    start_ts = end_ts - (since_minutes * 60)

    params = {
        "query": logql,
        "start": str(start_ts),
        "end": str(end_ts),
        "limit": str(limit),
        "direction": "backward",
    }

    try:
        response = httpx.get(
            f"{loki_url}/loki/api/v1/query_range",
            params=params,
            timeout=15,
        )

        if response.status_code == 400:
            return f"❌ LogQL syntax error: {response.text}"
        if response.status_code != 200:
            return f"❌ Loki error {response.status_code}: {response.text[:300]}"

        data = response.json()
        results = data.get("data", {}).get("result", [])

        if not results:
            return f"ℹ️ Tidak ada log yang cocok untuk query: `{logql}` dalam {since_minutes} menit terakhir."

        lines = []
        total = 0
        for stream in results:
            labels = stream.get("stream", {})
            host = labels.get("host.name", labels.get("hostname", "unknown"))
            for ts_ns, log_line in stream.get("values", []):
                ts_sec = int(ts_ns) / 1e9
                ts_human = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_sec))
                lines.append(f"[{ts_human}] {host}: {log_line}")
                total += 1

        if not lines:
            return f"ℹ️ Tidak ada log entries dalam {since_minutes} menit terakhir."

        # Sort by time (newest first since direction=backward)
        header = f"📋 {total} log entries (query: `{logql}`, last {since_minutes}min):\n"
        return header + "\n".join(lines[:limit])

    except httpx.ConnectError:
        return (
            f"⚠️ Tidak bisa connect ke Loki ({loki_url}). "
            "Pastikan container Loki berjalan (`docker compose ps`)."
        )
    except Exception as e:
        return f"❌ Error querying Loki: {str(e)}"


@tool
def get_loki_status() -> str:
    """
    Cek apakah Loki tersedia dan berapa banyak log yang tersimpan.

    Returns:
        Status Loki dan statistik log
    """
    loki_url = _get_loki_url()
    try:
        resp = httpx.get(f"{loki_url}/ready", timeout=5)
        if resp.status_code == 200:
            # Also get label values to show available hosts
            labels_resp = httpx.get(f"{loki_url}/loki/api/v1/labels", timeout=5)
            labels = []
            if labels_resp.status_code == 200:
                labels = labels_resp.json().get("data", [])

            return (
                f"✅ Loki tersedia di {loki_url}\n"
                f"Available labels: {', '.join(labels) if labels else 'none'}\n\n"
                f"Contoh query:\n"
                f'  {{job="syslog"}} — semua log\n'
                f'  {{job="syslog"}} |= "error" — filter error\n'
                f'  {{job="syslog", "host.name"="router1"}} — device tertentu'
            )
        else:
            return f"⚠️ Loki merespons dengan status {resp.status_code}"
    except httpx.ConnectError:
        return f"❌ Loki tidak bisa dijangkau di {loki_url}"
    except Exception as e:
        return f"❌ Error checking Loki: {str(e)}"


def get_loki_tools() -> list:
    """Get all Loki-related tools."""
    return [query_loki, get_loki_status]
