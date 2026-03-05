# ============================================================
# AgenticNet — Dockerfile
# Agentic AI Network Infrastructure Operator
# ============================================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# --- System dependencies ---
# iputils-ping  : ping command
# traceroute    : traceroute command
# dnsutils      : nslookup, dig
# iproute2      : ip link set (interface management)
# openssh-client: SSH for netmiko/paramiko
# libssl-dev    : SSL support for paramiko
# curl          : useful for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
        iputils-ping \
        traceroute \
        dnsutils \
        iproute2 \
        openssh-client \
        libssl-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Copy application source ---
COPY . .

# --- Create data directory (will be overridden by volume mount) ---
RUN mkdir -p /app/data/chroma_db /app/data/logs /app/data/reports

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entry point
CMD ["python", "main.py"]
