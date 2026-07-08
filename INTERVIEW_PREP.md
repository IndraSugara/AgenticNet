# 🎯 Persediaan Interview — AgenticNet

> Disusun berdasarkan codebase sebenar di `C:\Users\ASUS\agenticNet`. Setiap jawapan disokong oleh implementasi sebenar dalam code.

---

## 🕐 KRONOLOGI #1: Alur Data Penuh (End-to-End Data Flow)

> **"Ceritakan bagaimana sistem kamu bekerja dari awal sampai akhir."**
>
> Ini jawapan paling penting untuk interview. Ceritakan sebagai satu naratif — dari network event → detection → investigation → remediation → learning.

---

### ⏮️ FASE 0: System Startup (apa yang terjadi saat `docker compose up`)

```
docker compose up
    │
    ├──[1]┈▶ Loki container starts (Grafana Loki 3.0)
    │         └─ Listening on port 3100 (HTTP)
    │         └─ TSDB schema, filesystem storage di volume loki-data
    │
    ├──[2]┈▶ OpenTelemetry Collector starts
    │         └─ UDP 514: menerima syslog (RFC5424)
    │         └─ gRPC 4317 / HTTP 4318: menerima OTLP traces
    │         └─ Pipeline: memory_limiter(256MB) → resource → batch(5s/512) → Loki
    │
    ├──[3]┈▶ SNMP Trap Receiver starts (snmptrapd)
    │         └─ UDP 162: menerima SNMP trap dari network devices
    │         └─ handler.sh siap — setiap trap dikonversi ke syslog
    │
    ├──[4]┈▶ AgenticNet container starts (FastAPI + LangGraph)
    │         │
    │         ├─ import semua tools (25+ LangChain tools)
    │         ├─ build_agent_graph():
    │         │   ├─ get_all_tools() → 25+ tools diregistrasi
    │         │   ├─ get_llm_with_fallback() → LLM primary + fallback
    │         │   ├─ llm.bind_tools(tools) → tools di-attach ke LLM
    │         │   └─ StateGraph di-compile dengan checkpointer MemorySaver
    │         │
    │         ├─ lifespan() startup:
    │         │   ├─ health_check_background_task() — poll Ollama tiap 30s
    │         │   ├─ network_monitor_task() — ukur latency+bandwidth tiap 10s
    │         │   ├─ metrics_broadcast_task() — push metrics via WS tiap 5s
    │         │   └─ monitoring.start_collection(interval=10) — CPU/RAM/Disk via psutil
    │         │
    │         └─ NetworkAgent singleton siap → network_agent
    │
    └─ Semua 4 services up, monitoring network bridge aktif
```

---

### ⏭️ FASE 1: Network Event → Ingestion (detik 0)

**Contoh skenario:** Interface GigabitEthernet0/5 di switch Cisco tiba-tiba down.

```
[DETIK 0.000] Switch Cisco IOS menghasilkan log:
    "%LINK-3-UPDOWN: Interface GigabitEthernet0/5, changed state to down"

[DETIK 0.001] Switch mengirim SNMP trap (linkDown) ke UDP 162
    │
    ▼
[DETIK 0.002] snmptrapd container menerima trap di port 162/udp
    │
    ├─ snmptrapd.conf: traphandle default → /usr/local/bin/handler.sh
    │
    ▼
[DETIK 0.003] handler.sh:
    │
    ├─ Baca stdin: hostname="SW-CORE-01", source_ip="192.168.1.10"
    ├─ Baca OID=value pairs dari trap body
    ├─ Bina RFC5424 syslog message:
    │    <133>1 2026-06-30T10:15:00Z SW-CORE-01 snmptrapd - - -
    │    SNMPTRAP host=SW-CORE-01 ip=192.168.1.10
    │    ifIndex=5 ifDescr=GigabitEthernet0/5 ifAdminStatus=down
    │
    ├─ echo ke stdout (untuk Docker logs)
    └─ nc -u -w1 otel-collector 514  ← forward ke OTel via UDP
    │
    ▼
[DETIK 0.005] OpenTelemetry Collector menerima syslog di UDP 514:
    │
    ├─ syslog receiver parsing RFC5424
    ├─ resource processor: promosi hostname→host.name, appname→service.name
    ├─ batch processor: kumpul sampai 5s window atau 512 entries
    └─ loki exporter: push ke http://loki:3100/loki/api/v1/push
    │
    ▼
[DETIK 0.050] Loki menyimpan log entry:
    │
    ├─ Labels: {job="syslog", host.name="SW-CORE-01", service.name="snmptrapd"}
    ├─ Timestamp: 2026-06-30T10:15:00.000000000Z (nanosecond precision)
    └─ Value: "SNMPTRAP host=SW-CORE-01 ip=192.168.1.10 ..."
```

---

### ⏭️ FASE 2: Polling & Detection (detik ~60)

```
[DETIK 60] LokiIngester._ingest_loop() — berjalan tiap 60 saat (configurable)

    ├─ Hitung time window: start = last_ingested_ts, end = now (nanosecond)

    ├─ Query Loki: GET /loki/api/v1/query_range
    │    {job="syslog"} | start=... | end=... | limit=1000 | direction=forward

    ├─ Loki balas dengan 1+ "streams", setiap stream ada "values"
    │    stream: {host.name="SW-CORE-01"}
    │    values: [[ts_ns, "log line text"], [ts_ns, "log line text"], ...]

    ├─ Parse setiap value → list of (host, log_line, timestamp)

    ▼
[DETIK 60.1] DUA jalur paralel dari LokiIngester:

    ┌──▶ JALUR A: _embed_to_chroma(lines)
    │    │
    │    ├─ Batch 20 log lines untuk efisiensi embedding
    │    ├─ Untuk setiap line: bina content (Host + Time + Log)
    │    ├─ OllamaEmbeddings: embed text → vector
    │    └─ ChromaDB collection "network_knowledge":
    │         └─ add_document(title, content, category="network_log", tags=[host, "syslog"])
    │         └─ → Boleh di-semantic-search nanti ("cari log tentang BGP neighbor down")
    │
    └──▶ JALUR B: _route_to_log_watcher(lines)  ← INI YANG PENTING
         │
         └─ Untuk setiap (host, line):
              log_watcher.process_log_line(host="SW-CORE-01", line="%LINK-3-UPDOWN...")
    │
    ▼
[DETIK 60.2] LogWatcher.process_log_line():
    │
    ├─ Cari device config berdasarkan host IP/name
    ├─ Kalau device registered & enabled → lanjut
    │
    └─ _check_line_for_anomalies():
         │
         ├─ Loop 9 anomaly patterns, cek regex satu per satu
         │
         ├─ Pattern "link_down" MATCH!
         │    regex: r"(link.*(down|fail)|interface.*changed state to down|%LINK-\d+-\w*DOWN|...)"
         │    Match: "%LINK-3-UPDOWN: Interface GigabitEthernet0/5, changed state to down"
         │
         └─ First match wins → break (satu log line = satu anomaly)
```

---

### ⏭️ FASE 3: Anomaly Creation & Context Gathering (detik ~60.3)

```
[DETIK 60.3] _create_anomaly():
    │
    ├─ Buat anomaly_id: "anom_000042"
    ├─ Buat DetectedAnomaly dataclass:
    │    id: "anom_000042"
    │    device_ip: "192.168.1.10"
    │    device_name: "SW-CORE-01"
    │    pattern_name: "link_down"
    │    severity: "critical"
    │    description: "Network interface link down detected"
    │    log_line: "%LINK-3-UPDOWN: Interface GigabitEthernet0/5..."
    │    timestamp: "2026-06-30T10:15:00"
    │
    ├─ Simpan ke self._anomalies (max 200, FIFO)
    │
    ├─ [PARALEL A] _store_anomaly_to_knowledge():
    │    └─ ChromaDB: add_document(
    │         title="Incident: Network interface link down on SW-CORE-01",
    │         category="incident",
    │         tags=["192.168.1.10", "link_down", "critical"]
    │       )
    │
    └─ [PARALEL B] alert_manager.create_alert():
         ├─ Severity: "critical"
         ├─ Message: "[Log Anomaly] Network interface link down: %LINK-3-UPDOWN..."
         ├─ Broadcast ke 5 channel: Dashboard, Webhook, Email, Discord, Telegram
         └─ WebSocket push: notifikasi real-time ke dashboard
```

---

### ⏭️ FASE 4: AI Investigation dengan RAG (detik ~60.5)

```
[DETIK 60.5] _trigger_agent(anomaly):
    │
    ├─ [STEP 1] Cari REMEDIATION_RUNBOOKS["link_down"]:
    │    {
    │      "severity_threshold": "critical",
    │      "auto_actions": ["ping", "get_interfaces"],
    │      "requires_confirmation": ["enable_local_interface", "enable_remote_interface"],
    │      "prompt": "Interface link down terdeteksi. Lakukan:\n
    │                 1. Ping device untuk memastikan reachability\n
    │                 2. Cek status semua interface\n
    │                 3. Analisis penyebab (kabel, config, atau hardware)\n
    │                 4. Jika interface bisa di-enable kembali, AJUKAN konfirmasi\n
    │                 5. Jika hardware issue, buat alert..."
    │    }
    │
    ├─ [STEP 2] _search_similar_incidents() → RAG dari ChromaDB:
    │    │
    │    ├─ Query semantic: "Network interface link down %LINK-3-UPDOWN... SW-CORE-01"
    │    ├─ ChromaDB.search(k=3, category="incident"):
    │    │    └─ Result: 2 insiden serupa ditemukan
    │    │       ├─ "Incident: link_down on SW-ACCESS-03" (2 minggu lalu)
    │    │       └─ "Incident: link_down on SW-CORE-01 port Gi0/5" (1 bulan lalu)
    │    │
    │    ├─ ChromaDB.search(k=2, category="solution"):
    │    │    └─ Result: 1 solusi ditemukan
    │    │       └─ "Solution: link_down on SW-CORE-01 — kabel diganti, port di-re-enable"
    │    │
    │    └─ Bina RAG context:
    │         "=== KONTEKS DARI INSIDEN SEBELUMNYA (RAG) ===
    │          📋 Insiden serupa:
    │          1. Incident: link_down on SW-CORE-01 port Gi0/5...
    │          ✅ Solusi yang pernah berhasil:
    │          1. Solution: link_down on SW-CORE-01 — kabel diganti..."
    │
    ├─ [STEP 3] Bina prompt investigasi LENGKAP:
    │    """
    │    [AUTO-REMEDIATION] Anomali terdeteksi pada device SW-CORE-01 (192.168.1.10).
    │    Severity: critical
    │    Tipe: Network interface link down detected
    │    Log: %LINK-3-UPDOWN: Interface GigabitEthernet0/5, changed state to down
    │
    │    === KONTEKS DARI INSIDEN SEBELUMNYA (RAG) ===
    │    [similar incidents + solutions dari ChromaDB]
    │
    │    === RUNBOOK REMEDIASI ===
    │    Interface link down terdeteksi. Lakukan langkah-langkah berikut:
    │    1. Ping device untuk memastikan reachability
    │    2. Cek status semua interface
    │    3. Analisis penyebab (kabel, config, atau hardware)
    │    4. Jika interface bisa di-enable kembali, AJUKAN konfirmasi ke user
    │    5. Jika hardware issue, buat alert dan rekomendasikan tindakan fisik
    │
    │    Instruksi tambahan:
    │    - Gunakan tools berikut untuk investigasi awal: ping, get_interfaces
    │    - Aksi yang MEMERLUKAN konfirmasi user: enable_local_interface, enable_remote_interface
    │    - JANGAN skip konfirmasi untuk aksi high-risk
    │    """
    │
    └─ [STEP 4] network_agent.ainvoke(prompt, thread_id="logwatch-...-anom_000042")
```

---

### ⏭️ FASE 5: LangGraph Agent ReAct Loop (detik ~61-65)

```
[DETIK 61] LangGraph agent mula bekerja — ReAct loop:

┌─────────────────────────────────────────────────────────┐
│  START → agent → tools → agent → tools → agent → END   │
│           ↑                 ↑                           │
│           └─── ReAct loop ──┘                           │
└─────────────────────────────────────────────────────────┘

ITERASI 1 — Agent Node:
    ├─ System prompt (230 lines) prepended ke messages
    ├─ LLM invoke dengan prompt investigasi
    ├─ LLM decide: perlu panggil tool "ping" dulu
    └─ Output: AIMessage with tool_calls=[{name: "ping", args: {host: "192.168.1.10"}}]

ITERASI 1 — Tools Node:
    ├─ ToolNode execute "ping" → NetworkTools.ping("192.168.1.10", count=4)
    ├─ subprocess.run(["ping", "-n", "4", "192.168.1.10"]) → output
    └─ Return: ToolMessage(content="Ping statistics for 192.168.1.10: ... Reply from ...")

ITERASI 2 — Agent Node:
    ├─ LLM terima hasil ping: "Device reachable, latency 2ms"
    ├─ LLM decide: perlu cek interface status → panggil tool "get_interfaces"
    └─ Output: tool_calls=[{name: "get_interfaces", args: {device_ip: "192.168.1.10"}}]

ITERASI 2 — Tools Node:
    ├─ ToolNode execute "get_interfaces"
    ├─ ConnectionManager.execute_on_device():
    │    ├─ _resolve_device("192.168.1.10") → DeviceInfo dari inventory
    │    ├─ CommandTranslator.translate(GET_INTERFACES, CISCO_IOS):
    │    │    "show ip interface brief"
    │    ├─ Netmiko ConnectHandler → SSH ke 192.168.1.10
    │    ├─ conn.send_command("show ip interface brief")
    │    └─ Return output: "Interface      IP-Address     Status   Protocol
    │                       Gi0/1          10.0.0.1       up       up
    │                       Gi0/5          unassigned     down     down  ← INI!"
    └─ Return: ToolMessage(content="Interface Gi0/5: status=down, protocol=down")

ITERASI 3 — Agent Node:
    ├─ LLM analisis:
    │    "Device reachable (ping OK).
    │     Interface Gi0/5 down. Interface lain up.
    │     Berdasarkan RAG context, insiden serupa pernah terjadi
    │     dan solusinya adalah pengecekan kabel fisik.
    │     Kemungkinan penyebab: kabel lepas, port lawan mati, atau hardware failure.
    │
    │     Untuk enable interface kembali, perlu konfirmasi user."
    │
    ├─ LLM propose remediation:
    │    → Panggil tool "enable_remote_interface" untuk minta konfirmasi
    │
    └─ Output: tool_calls=[{name: "enable_remote_interface", ...}]

ITERASI 3 — Tools Node:
    ├─ ToolNode execute "enable_remote_interface"
    ├─ Guardrails check: risk = HIGH, perlu HITL
    ├─ PendingActionsStore.add():
    │    action_id: "a1b2c3d4"
    │    tool_name: "enable_remote_interface"
    │    params: {device: "SW-CORE-01", interface: "Gi0/5"}
    │    expires: now + 300s
    │
    └─ Return: ⚠️ KONFIRMASI DIPERLUKAN
              Action ID: a1b2c3d4

ITERASI 4 — Agent Node:
    ├─ LLM lihat tool result = konfirmasi diperlukan
    ├─ LLM TIDAK auto-execute — ikut <high_risk_operations> rules
    ├─ LLM sampaikan ke user: "Interface Gi0/5 boleh di-enable.
    │    Action ID: a1b2c3d4. Sila konfirmasi."
    └─ No more tool calls → tools_condition = END

[DETIK 65] Agent selesai. Response disimpan.
```

---

### ⏭️ FASE 6: Human-in-the-Loop Approval (detik ~70)

```
[DETIK 65] Investigation result disimpan:
    ├─ self._investigations.append({...})  — max 50
    ├─ self._remediation_history.append({...})  — max 100
    └─ WebSocket push ke dashboard: "investigation completed"

[DETIK 66] Dashboard terima notifikasi via WebSocket:
    ├─ Toast notification: "🚨 Anomaly: link_down on SW-CORE-01 — investigated"
    ├─ Panel "Investigations" update — tunjuk hasil agent
    └─ Action ID "a1b2c3d4" dipaparkan dengan button [Approve] [Reject]

[DETIK 70] Human engineer klik [Approve] di dashboard:
    │
    ├─ Frontend → POST /workflow/confirm {action_id: "a1b2c3d4"}
    ├─ PendingActionsStore.confirm("a1b2c3d4"):
    │    ├─ Cari action dalam store
    │    ├─ Execute: ConnectionManager → SSH ke SW-CORE-01
    │    ├─ conn.send_config_set(["interface Gi0/5", "no shutdown"])
    │    └─ Return: "✅ Interface Gi0/5 enabled successfully"
    │
    └─ Action removed dari pending store
```

---

### ⏭️ FASE 7: Resolution & Learning Loop (detik ~71+)

```
[DETIK 71] _save_investigation_result():
    │
    ├─ Bina content solution:
    │    "Problem: Network interface link down on SW-CORE-01
    │     Log: %LINK-3-UPDOWN: Interface GigabitEthernet0/5...
    │     Investigation: Device reachable via ping. Interface Gi0/5 down.
    │     Interface di-enable kembali setelah konfirmasi. Berhasil."
    │
    └─ ChromaDB: add_document(
         title="Solution: link_down on SW-CORE-01",
         content=...,
         category="solution",
         tags=["192.168.1.10", "link_down", "auto-investigated"]
       )

✅ LEARNING LOOP TERTUTUP:
   Insiden → Detect → Investigate (dengan RAG dari insiden lampau)
   → Remediate → Simpan solution → Future insiden dapat recommendation lebih baik

[DETIK 72+] Scheduler tetap berjalan:
    ├─ Tiap 5s: health check ICMP ping + TCP port probe ke semua device
    ├─ Status change detection: ONLINE↔OFFLINE↔DEGRADED → auto-alert
    └─ Semua metrics disimpan ke SQLite metrics.db (WAL mode)
```

---

### 📊 Ringkasan Alur Data (One-Liner untuk Interview)

> **"Log dari network device mengalir melalui SNMP trap → syslog → OpenTelemetry Collector → Loki. LokiIngester polling Loki setiap 60 saat, meng-embed log ke ChromaDB untuk semantic search dan merutekan setiap log line ke LogWatcher. LogWatcher mendeteksi anomaly via regex (9 pola), mencari insiden serupa dari ChromaDB (RAG), lalu memicu LangGraph agent untuk investigasi otomatis. Agent menggunakan tools (ping, SSH via Netmiko, traceroute, dll.) dalam ReAct loop untuk diagnosis, kemudian mencadangkan remediasi. High-risk actions memerlukan HITL approval. Setelah resolved, solution disimpan kembali ke ChromaDB — menutup learning loop."**

---

## 🏗️ KRONOLOGI #2: Proses Pembangunan Sistem (System Build Chronology)

> **"Bagaimana kamu membangun sistem ini dari awal?"**
>
> Ini naratif pembangunan — dari lapisan paling bawah (tools) ke paling atas (orchestration + UI).

---

### 📐 LAPISAN 1: Foundation — Network Diagnostic Tools

**File:** `tools/network_tools.py`

```
Mulai dari layer paling fundamental: tools yang bisa diagnose jaringan.

PILIHAN TEKNIKAL:
- subprocess (ping, traceroute, nslookup) — platform-aware, Windows & Linux
- socket (check_port, port_scan, DNS lookup) — pure Python, no dependency
- psutil (get_interfaces, get_connections, bandwidth) — comprehensive metrics

MENGAPA:
- Tools ini adalah "mata dan telinga" agent. Tanpa data konkrit, agent
  hanya menebak. Setiap tool return data terstruktur (ToolResult dataclass),
  bukan raw text — supaya agent boleh parse dengan mudah.

HASIL: 13 network tools siap sebagai fondasi.
```

---

### 📐 LAPISAN 2: Multi-Vendor Abstraction

**File:** `tools/vendor_drivers.py`, `tools/unified_commands.py`

```
Network devices dari vendor berbeza guna CLI syntax berbeza.
Perlu abstraction layer supaya agent tidak perlu tahu syntax setiap vendor.

KOMPONEN:
1. UnifiedCommand (Enum) — 18 standard commands:
   GET_INTERFACES, GET_ROUTING_TABLE, GET_ARP_TABLE, PING, TRACEROUTE,
   SHUTDOWN_INTERFACE, NO_SHUTDOWN_INTERFACE, SET_VLAN, dll.

2. CommandTranslator — map UnifiedCommand → vendor-specific syntax:
   Cisco IOS: "show ip interface brief"
   Mikrotik:  "/interface print"
   HP Comware: "display ip interface brief"
   Linux:     "ip -br addr show"

3. DeviceConnection — wrapper satu SSH connection (Netmiko)
   - connect(), disconnect(), execute(), execute_config()
   - read_timeout=60s untuk command lama (show running-config)

4. ConnectionManager (singleton) — connection pool:
   - Max 10 concurrent SSH connections
   - Auto-cleanup idle connections (5 min timeout)
   - Async wrapper: asyncio.to_thread() untuk non-blocking I/O

5. OutputParser — normalisasi output:
   - Regex patterns untuk parse Cisco/Mikrotik interface output
   - NormalizedResult dataclass — standard format across vendors

MENGAPA:
- Agent hanya panggil "GET_INTERFACES on device X"
- Abstraction layer yang translate + execute + parse
- Tambah vendor baru = tambah entry di TRANSLATIONS dict sahaja
```

---

### 📐 LAPISAN 3: Data Persistence & Inventory

**File:** `modules/inventory.py`, `agent/infrastructure.py`, `data/`

```
Dua sumber data device (dual-source dengan fallback):

1. InventoryModule (inventory.py → data/inventory.db):
   - Source of truth untuk network devices
   - Fields: name, ip_address, vendor, role, model, location, ssh_port, credential_id
   - Auto-detect vendor dari hostname pattern (Cisco, Mikrotik, Ubiquiti, Linux)

2. InfrastructureManager (infrastructure.py → data/devices.db):
   - Monitoring-oriented device store
   - Fields: ip, type, ports_to_monitor, check_interval, ssh_username, ssh_password
   - DeviceStatus enum: ONLINE, OFFLINE, DEGRADED, UNKNOWN

3. Dual-source resolution (_resolve_device):
   - Cari di inventory dulu → kalau tak jumpa, fallback ke infrastructure
   - Bridge dua database — device dari mana-mana source boleh di-SSH

DATABASE LAIN:
- metrics.db (WAL mode): metrics_raw (24h), metrics_5min (30d), interface_metrics
- chat_history.db: conversation persistence per thread_id
- conversations.db: LangGraph checkpoint state
- config_backups.db: device config backup storage
- long_term_memory.db: device baselines + history

MENGAPA SQLite (bukan PostgreSQL)?
- Single-node deployment, zero-config, portable
- WAL mode untuk concurrent reads
- Cukup untuk POC/trial — production boleh swap ke PostgreSQL
```

---

### 📐 LAPISAN 4: LangChain Tools (Agent Tools)

**File:** `agent/langchain_tools.py`, `agent/langchain_device_tools.py`, dll.

```
Setiap network tool perlu di-wrap sebagai LangChain Tool
supaya LLM boleh panggil via function calling.

Proses untuk setiap tool:
1. Bina fungsi Python (e.g., def ping(host: str, count: int = 4) -> str)
2. Wrap dengan @tool decorator dari LangChain
3. Berikan name, description dalam Bahasa Indonesia
4. Tambah type hints → auto-generate JSON schema untuk LLM

25+ Agent Tools dikategorikan:
├── Diagnostik: ping, traceroute, dns_lookup, nslookup, check_port, port_scan
├── Monitoring: get_interfaces, get_connections, measure_latency, bandwidth
├── Device CRUD: list_devices, add_device, remove_device
├── Topology: discover_network, get_topology, get_topology_mermaid
├── Report: generate_network_report, get_quick_status
├── Knowledge: search_knowledge, add_knowledge, remember_solution
├── Scheduler: create_schedule, list_schedules, get_alerts
├── Backup: backup_config, restore_config, list_backups
├── CLI Exec: execute_cli, execute_cli_config (HIGH-RISK)
├── Interface Mgmt: disable/enable interface (HIGH-RISK)
└── Log Watch: start_log_watch, get_recent_anomalies

get_all_tools() — aggregate semua tools untuk bind ke LLM
```

---

### 📐 LAPISAN 5: LangGraph Agent

**File:** `agent/langgraph_agent.py`

```
Agent = LLM + Tools + StateGraph + System Prompt

PROSES BUILD:
1. Tentukan state schema:
   class AgentState(TypedDict):
       messages: Annotated[List[BaseMessage], add_messages]
   → LangGraph auto-handle message appending

2. Tulis SYSTEM_PROMPT (230 lines, Bahasa Indonesia):
   - Identity: "NetOps Sentinel", senior network engineer
   - 11 tool categories dengan deskripsi
   - Supported vendors
   - Tool calling rules (kapan guna, kapan tak guna)
   - Troubleshooting strategy (tiered: ping → trace → DNS → analyze)
   - ⚠️ HIGH-RISK rules: SAVE output, COPY Action ID, don't re-prompt
   - Communication style: Bahasa Indonesia default, markdown, emojis
   - Error handling: jangan tunjuk raw stacktrace

3. Build graph topology:
   - Supports tools: START → agent ⇄ tools → END
   - No tools (fallback): START → agent → END

4. Compile dengan checkpointer (MemorySaver)

5. Wrapper class NetworkAgent:
   - invoke() / ainvoke() — sync & async
   - astream() — streaming via astream_events v2
   - get_history() / clear_history() — session management
   - thread_id — multi-user isolation

6. Singleton: network_agent = NetworkAgent(use_memory=True, persistent=True)
```

---

### 📐 LAPISAN 6: LLM dengan Multi-Provider Fallback

**File:** `agent/langchain_llm.py`

```
MASALAH: Model Ollama local kadang down, kadang tak support function calling.
SOLUSI: Provider factory + FallbackLLM wrapper.

1. _PROVIDER_FACTORY registry:
   - ollama: ChatOllama dengan auto-detect ngrok URL (skip browser warning)
   - openai: ChatOpenAI (support OpenAI + compatible endpoints)
   - deepseek: ChatOpenAI pointed ke api.deepseek.com/v1

2. FallbackLLM class:
   - Wrap primary + fallback LLM
   - invoke() → cuba primary, kalau gagal → fallback
   - bind_tools() → bind ke kedua-duanya
   - is_using_fallback property untuk monitoring

3. LLM switching API:
   GET  /agent/models/list   → tunjuk 6 models (Ollama, Kimi K2, GPT-4o, DeepSeek)
   POST /agent/model/switch  → rebuild LangGraph agent dengan model baru

4. create_agent_node() dengan dual LLM:
   - llm_with_tools: LLM yang dah di-bind tools (primary)
   - llm_base: LLM tanpa tools (fallback untuk schema error recovery)
   - Kalau bind_tools gagal → auto fallback ke chat-only mode
```

---

### 📐 LAPISAN 7: Observability Pipeline

**File:** `snmptrapd/`, `otel-config.yaml`, `loki-config.yaml`, `agent/loki_ingester.py`

```
OBSERVABILITY STACK (4 komponen):

1. SNMP Trap Receiver:
   - Dockerfile: Ubuntu + snmptrapd + snmp-mibs-downloader
   - UDP 162 → terima trap dari network devices
   - handler.sh → konversi SNMP trap ke RFC5424 syslog
   - Forward ke OTel Collector via UDP 514

2. OpenTelemetry Collector:
   - Pipeline: syslog receiver → memory_limiter → resource → batch → Loki
   - Promotes hostname/ip ke Loki labels untuk query efficiency
   - Debug exporter untuk troubleshooting

3. Grafana Loki 3.0:
   - TSDB untuk log (optimized untuk time-series text)
   - LogQL query language — cari log dengan label filters
   - Filesystem storage (production: S3/GCS)

4. LokiIngester (bridge ke AI layer):
   - Poll Loki setiap 60s: query_range {job="syslog"}
   - Dua output paralel:
     a. ChromaDB: embed logs untuk semantic search
     b. LogWatcher: real-time anomaly detection
```

---

### 📐 LAPISAN 8: Anomaly Detection & Auto-Remediation

**File:** `agent/log_watcher.py`

```
LOGWATCHER — jantung autonomous operations:

1. 9 Anomaly Patterns (compiled regex):
   link_down, link_flap, auth_failure, system_error, system_warning,
   routing_change, stp_change, hardware_issue (+ catch-all unknown)

2. 8 Remediation Runbooks:
   Setiap pattern ada:
   - severity_threshold: bila nak trigger
   - auto_actions: tools yang auto-execute (ping, get_interfaces, dll.)
   - requires_confirmation: tools yang perlu HITL
   - prompt: arahan lengkap untuk agent

3. ChromaDB RAG Integration:
   - Anomaly → simpan sebagai "incident" di ChromaDB
   - Sebelum trigger agent → search similar past incidents + solutions
   - Selepas resolved → simpan sebagai "solution"
   - → LEARNING LOOP: sistem makin pintar dari masa ke masa

4. Agent Trigger:
   - Bina prompt dari: anomaly + RAG context + runbook
   - network_agent.ainvoke(prompt) — async, non-blocking
   - Investigation disimpan (max 50), remediation history (max 100)
```

---

### 📐 LAPISAN 9: Scheduler & Health Check

**File:** `agent/scheduler.py`, `modules/monitoring.py`

```
DUA MONITORING LAYER:

A. System Monitoring (monitoring.py):
   - psutil: CPU, RAM, Disk, Network I/O tiap 10s
   - SQLite: metrics_raw (24h), metrics_5min (30d)
   - z-score anomaly detection (3σ threshold)
   - Static threshold alerts (CPU>70%, RAM>80%, Disk>80%)

B. Device Health Check (scheduler.py):
   - ICMP ping dulu → kalau gagal, fallback TCP port probe (80, 443, 22)
   - Port monitoring per device (configurable ports)
   - Status transition detection:
     ONLINE→OFFLINE: critical alert
     ONLINE→DEGRADED: warning alert
     OFFLINE→ONLINE: info alert (recovery notification)
   - Async asyncio loop, tiap device ada check interval sendiri
```

---

### 📐 LAPISAN 10: Guardrails & Safety

**File:** `modules/guardrails.py`, `tools/pending_actions.py`

```
SAFETY LAYER — memastikan agent tidak merosakkan network:

1. CommandClassifier (regex risk scoring):
   - CRITICAL: shutdown, reload, format, erase
   - HIGH: config changes, VLAN mods, routing changes
   - MEDIUM: show running-config, debug
   - LOW: show commands, ping, traceroute
   - ALWAYS_BLOCKED: rm -rf, format flash, erase

2. PendingActionsStore:
   - Action ID: UUID4[:8]
   - Auto-expire: 300 saat (5 min)
   - confirm() / cancel() / list_pending()

3. ExecutionPlan:
   - Multi-step plans dengan dependencies
   - Max iterations per session (default 5)
   - Auto-approve below configurable risk threshold (RISK_THRESHOLD=0.7)

4. Rollback generation:
   - shutdown → no shutdown
   - Auto-generated untuk setiap destructive action
```

---

### 📐 LAPISAN 11: FastAPI Web Layer + WebSocket

**File:** `web/main.py`, `web/routes/*.py`, `web/websocket_manager.py`

```
API DESIGN — 9 route modules, 40+ endpoints:

1. web/main.py:
   - FastAPI app dengan lifespan (async context manager)
   - CORS middleware (all origins untuk dev)
   - 3 background tasks dimulai saat startup
   - Jinja2 template untuk dashboard SPA

2. web/websocket_manager.py — ConnectionManager:
   - 3 channels: metrics, notifications, chat
   - broadcast dengan graceful disconnect handling
   - Copy set sebelum iterate (avoid mutation during disconnect)

3. web/routes/:
   ├── health.py      — /health, /monitoring, /network, /security, /llm
   ├── chat.py        — /agent/query, /agent/stream (WS), /ws/metrics
   ├── devices.py     — /inventory CRUD, /device/command
   ├── infrastructure  — /infra/ CRUD, SSH/Telnet exec, /infra/live (WS)
   ├── logs.py        — /logs/app (SSE stream), /logs/loki (LogQL)
   ├── log_watch.py   — LogWatcher control, anomalies, patterns
   ├── models.py      — LLM model list + switch
   ├── workflows.py   — /tools/run, pending actions, workflow stream
   └── guardrails.py  — plan approval, validate command
```

---

### 📐 LAPISAN 12: Docker + Deployment

**File:** `docker-compose.yml`, `Dockerfile`, `snmptrapd/Dockerfile`

```
DEPLOYMENT — 4 services di bridge network "monitoring":

docker-compose.yml:
  services:
    loki:         grafana/loki:3.0.0          — port 3100
    otel-collector: otel/opentelemetry-collector-contrib:0.96.0 — UDP 514, 4317, 4318
    snmptrapd:    custom Dockerfile (Ubuntu)   — UDP 162
    agenticnet:   custom Dockerfile (Python 3.11-slim) — port 8000

MENGAPA 4 SERVICES (bukan monolith):
- Separation of concerns: logging, collection, AI, trap receiver
- Scale independently: Loki boleh scale bila log volume meningkat
- OTel Collector boleh ganti backend (Loki → Elasticsearch) tanpa ubah code
- snmptrapd isolated — kalau SNMP flood, tak affect AI agent

Dockerfile (AgenticNet):
- System deps: iputils-ping, traceroute, dnsutils, iproute2, openssh-client
- Volume: ./data:/app/data → SQLite + ChromaDB persistent
- Healthcheck: curl localhost:8000/health
```

---

### 📐 LAPISAN 13: Dashboard & UI

**File:** `web/templates/dashboard.html` (41KB single-page)

```
DASHBOARD — Real-time SPA dengan WebSocket:

Panel-panel:
├── System Health — CPU/RAM/Disk gauges (update tiap 5s via WS)
├── Network Status — latency, bandwidth, packet loss
├── Device Inventory — list devices dengan status ONLINE/OFFLINE/DEGRADED
├── Anomaly Feed — recent anomalies dengan severity badges
├── Agent Chat — chat interface dengan token-level streaming
├── Investigations — hasil auto-investigation agent
├── Alerts — real-time alert toast notifications
├── Pending Actions — HITL approval buttons
├── Log Viewer — application logs dengan SSE streaming
└── Topology View — Mermaid.js network diagram

Teknologi:
- Server-Sent Events (SSE) untuk log streaming
- WebSocket untuk metrics, alerts, chat
- Vanilla JavaScript (no framework) — minimize dependencies
- Jinja2 server-side rendering untuk initial load
```

---

### 🔄 Lapisan Berinteraksi: Gambaran Penuh

```
                        ┌──────────────────────┐
                        │   NETWORK DEVICES    │
                        │  Cisco/Mikrotik/...  │
                        └────┬────────────┬────┘
                             │            │
                    SNMP Trap│            │ SSH (Netmiko)
                         UDP 162          │ TCP 22
                             │            │
                    ┌────────▼──┐  ┌──────▼───────┐
                    │ SNMPTRAPD │  │ CONNECTION   │
                    │  handler  │  │  MANAGER     │
                    └────┬──────┘  └──────┬───────┘
                         │                │
                    Syslog UDP 514        │
                         │                │
                 ┌───────▼────────┐       │
                 │ OTel COLLECTOR │       │
                 └───────┬────────┘       │
                         │ HTTP 3100      │
                 ┌───────▼────────┐       │
                 │     LOKI       │       │
                 └───────┬────────┘       │
                         │ poll 60s       │
                 ┌───────▼────────┐       │
                 │ LOKI INGESTER  │       │
                 └─┬────────────┬─┘       │
                   │ embed      │ route   │
          ┌────────▼──┐   ┌────▼─────┐   │
          │ CHROMADB  │   │LOGWATCHER│   │
          │  (RAG)    │   │9 patterns│   │
          └────────┬──┘   └────┬─────┘   │
                   │ search     │ trigger │
                   └──┐     ┌──┘         │
                      │     │            │
                 ┌────▼─────▼────┐       │
                 │ LANGGRAPH     │◄──────┘
                 │ AGENT (ReAct) │    gunakan
                 └──────┬───────┘    tools SSH
                        │
                        │ HITL
                 ┌──────▼───────┐
                 │ GUARDRAILS   │
                 │ PENDING ACT. │
                 └──────┬───────┘
                        │
                 ┌──────▼───────┐
                 │  FASTAPI     │──► Dashboard (WS)
                 │  40+ endpoints│──► Discord/Telegram
                 └──────────────┘
```

---

### 🎯 Naratif Interview (2-minit pitch)

Gunakan kronologi di atas untuk bina naratif interview. Pilih salah satu:

**Pilihan A: Cerita dari perspektif DATA FLOW**
> "Saya akan jelaskan aliran data dari satu network event sampai selesai. Bayangkan satu interface di switch Cisco tiba-tiba down. Switch hantar SNMP trap ke receiver kami, yang convert ke syslog dan forward ke OpenTelemetry Collector. Collector batch dan hantar ke Loki untuk storage. Setiap 60 saat, LokiIngester kami polling Loki untuk log baru dan hantar ke LogWatcher. LogWatcher scan 9 anomaly pattern guna compiled regex — bila detect link_down, ia automatik search ChromaDB untuk insiden serupa yang pernah terjadi, kemudian trigger LangGraph agent dengan full context: anomaly + RAG findings + remediation runbook. Agent jalankan ReAct loop — ping device, SSH untuk check interface, analisis — lepas tu cadangkan remediasi. High-risk action macam enable interface perlukan human approval. Bila dah resolved, solution disimpan balik ke ChromaDB — jadi sistem makin pintar."

**Pilihan B: Cerita dari perspektif PEMBANGUNAN**
> "Saya bina sistem ni dari bottom-up. Mulai dengan layer paling asas — network diagnostic tools guna subprocess dan socket. Lepas tu bina multi-vendor abstraction layer dengan Netmiko — satu unified command interface untuk Cisco, Mikrotik, Ubiquiti, Linux. Di atas tu, saya wrap semua tools sebagai LangChain Tools supaya LLM boleh panggil. Kemudian bina LangGraph agent dengan StateGraph, ReAct pattern, dan 230-line system prompt. Saya tambah multi-provider LLM dengan auto-fallback — kalau Ollama down, auto switch ke OpenAI. Untuk observability, saya deploy 4-container Docker stack: SNMP trap receiver → OTel Collector → Loki → AgenticNet. LogWatcher dan RAG system adalah layer autonomous — detect anomaly, search similar past incidents, trigger investigation, simpan solution untuk learning loop. Akhir sekali, semua di-expose melalui FastAPI dengan 40+ endpoints dan WebSocket real-time dashboard."

---

## 📦 KRONOLOGI #3: Inventori Teknikal — Setiap Folder, File, Class, Function, Library

> **"Folder apa ni? File ni buat apa? Kenapa guna library ni?"**
>
> Bahagian ini memetakan **SETIAP komponen teknikal** kepada fasenya dalam aliran data.
> Diguna untuk jawab soalan spesifik tentang peranan setiap fail dan modul.

---

### 📁 STRUKTUR FOLDER & PERANAN

```
C:\Users\ASUS\agenticNet/
│
├── 📁 agent/          (24 files) — OTAK AI: LangGraph agent, LLM, tools, LogWatcher, RAG
├── 📁 tools/          (4 files)  — TANGAN: network commands, SSH, vendor drivers
├── 📁 modules/        (5 files)  — SENSOR: monitoring, inventory, security, guardrails
├── 📁 web/            (13 files) — MUKA: FastAPI, WebSocket, dashboard, routes
├── 📁 snmptrapd/      (3 files)  — TELINGA: SNMP trap receiver container
├── 📁 data/           (runtime)  — PENYIMPANAN: semua SQLite DBs + ChromaDB + logs
│
├── 📄 config.py                  — SETTING PUSAT: semua env vars & konfigurasi
├── 📄 main.py                    — ENTRY POINT: uvicorn server startup
├── 📄 docker-compose.yml         — DEPLOY: 4-container orchestration
├── 📄 Dockerfile                 — IMAGE: Python 3.11-slim container
├── 📄 loki-config.yaml           — LOKI CONFIG: TSDB schema, filesystem storage
├── 📄 otel-config.yaml           — OTEL CONFIG: syslog receiver, batch, Loki exporter
└── 📄 requirements.txt           — DEPENDENCIES: semua Python packages
```

---

### 🟢 FASE 0 STARTUP: Peranan Setiap Komponen Semasa `docker compose up`

#### `docker-compose.yml`
| Elemen | Jenis | Peranan |
|--------|-------|---------|
| `version: "3.9"` | Config | Docker Compose file format version |
| `networks: monitoring` | Network | Bridge network supaya 4 containers boleh berkomunikasi via container name (DNS internal) |
| `volumes: loki-data` | Volume | Named volume — persistent storage untuk log Loki, survive container restart |
| `services: loki` | Service | Container pertama — log storage engine |
| `services: otel-collector` | Service | Container kedua — telemetry pipeline |
| `services: snmptrapd` | Service | Container ketiga — SNMP trap receiver |
| `services: agenticnet` | Service | Container keempat — main AI application |
| `depends_on: condition: service_healthy` | Dependency | AgenticNet hanya start bila Loki dah healthy — avoid race condition |
| `restart: unless-stopped` | Policy | Auto-restart containers kecuali manual stop |
| `logging: json-file, max-size` | Logging | Limit Docker container logs — 10MB × 3 files utk agenticnet |

#### `Dockerfile` (AgenticNet root)
| Elemen | Peranan |
|--------|---------|
| `FROM python:3.11-slim` | Base image — lightweight Python (bukan alpine untuk compatibility) |
| `iputils-ping` | System package — tool `ping` command untuk NetworkTools |
| `traceroute` | System package — tool `traceroute` command |
| `dnsutils` | System package — tool `nslookup`/`dig` command |
| `iproute2` | System package — tool `ip` command (interface management) |
| `openssh-client` | System package — SSH client untuk Netmiko |
| `libssl-dev` | System package — SSL libraries |
| `curl` | System package — untuk Docker healthcheck |

#### `snmptrapd/Dockerfile`
| Elemen | Peranan |
|--------|---------|
| `FROM ubuntu:22.04` | Base image |
| `snmptrapd` | Daemon — listen UDP 162 untuk SNMP traps |
| `snmp` | SNMP client tools |
| `snmp-mibs-downloader` | Download MIB files untuk OID translation |
| `netcat-openbsd` | `nc` command — forward syslog ke OTel via UDP |

#### `config.py`
| Class / Attribute | Jenis | Peranan |
|-------------------|-------|---------|
| `Config` | Class | Singleton configuration object |
| `config.OLLAMA_HOST` | str | LLM endpoint URL (local atau ngrok) |
| `config.OLLAMA_MODEL` | str | Nama model Ollama aktif |
| `config.LLM_FALLBACK_ENABLED` | bool | Toggle auto-fallback ke provider kedua |
| `config.LLM_FALLBACK_PROVIDER` | str | Provider fallback (openai/deepseek) |
| `config.HOST` | str | Bind address FastAPI (0.0.0.0) |
| `config.PORT` | int | Port FastAPI (8000) |
| `config.MAX_REASONING_STEPS` | int | Max ReAct iterations (10) |
| `config.RISK_THRESHOLD` | float | Auto-approve threshold (0.7) |
| `config.loki_url` | str | Loki query endpoint (http://loki:3100) |
| `config.loki_ingest_interval` | int | Polling interval (60s) |
| `.env` file | File | Environment variables — OLLAMA_HOST, API keys, dsb. |

#### `main.py` (root)
| Fungsi / Elemen | Peranan |
|-----------------|---------|
| `uvicorn web.main:app` | Entry point — jalankan FastAPI server |
| *(tidak ada fungsi lain)* | Hanya launch server sahaja |

#### `web/main.py`
| Elemen | Jenis | Peranan |
|--------|-------|---------|
| `lifespan()` | AsyncContextManager | Modern FastAPI lifecycle — ganti deprecated `on_event` |
| `health_check_background_task()` | asyncio.Task | Poll Ollama health tiap 30s — update health cache |
| `network_monitor_task()` | asyncio.Task | Ukur latency + bandwidth tiap 10s — update cached metrics |
| `metrics_broadcast_task()` | asyncio.Task | Push metrics via WebSocket tiap 5s |
| `monitoring.start_collection(10)` | Method | Start system metrics collection (CPU/RAM/Disk via psutil) |
| `FastAPI(title=..., version="2.0.0")` | App | Main application object |
| `CORSMiddleware` | Middleware | Allow all origins untuk development |
| `Jinja2Templates` | Template engine | Render dashboard.html SPA |
| `StaticFiles` | Middleware | Serve /static/ files (CSS, JS, favicon) |
| `app.include_router()` × 9 | Registration | Daftar 9 route modules |
| `templates.TemplateResponse("dashboard.html")` | Route | Serve main dashboard di `/` |

---

### 🔵 FASE 1: Ingestion — Dari Network Event ke Loki

#### `snmptrapd/snmptrapd.conf`
| Konfigurasi | Peranan |
|-------------|---------|
| `authCommunity log,net,execute public` | Accept traps dengan community string "public" — log + net + execute permissions |
| `disableAuthorization yes` | Terima SEMUA traps tanpa auth check |
| `traphandle default /usr/local/bin/handler.sh` | Route SEMUA traps ke handler.sh |
| `doNotLogTraps no` | Log traps ke stdout (untuk `docker logs`) |

#### `snmptrapd/handler.sh`
| Baris | Peranan |
|-------|---------|
| `OTEL_HOST="${OTEL_HOST:-otel-collector}"` | Default value — container name OTel Collector |
| `HOSTNAME=$(head -1)` | Baca baris pertama stdin = hostname penghantar trap |
| `SOURCE_IP=$(head -1)` | Baca baris kedua stdin = source IP |
| `TRAP_BODY=$(cat)` | Baca remaining stdin = OID=value pairs |
| `TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")` | Generate UTC timestamp |
| `<133>1 ...` | RFC5424 format: PRI=133 (facility 16=local0, severity 5=notice) |
| `nc -u -w1 "${OTEL_HOST}" "${OTEL_PORT}"` | Forward syslog ke OTel via UDP, timeout 1s |

#### `otel-config.yaml`
| Section | Peranan |
|---------|---------|
| `receivers: syslog` | Listen UDP 514, parse RFC5424 syslog protocol |
| `receivers: otlp` | Listen gRPC 4317 + HTTP 4318 untuk OTLP traces |
| `processors: memory_limiter` | Hard limit 256MB RAM — prevent OOM |
| `processors: resource` | Promosi `hostname`→`host.name`, `appname`→`service.name` sbg Loki labels |
| `processors: batch` | Batch 5s window atau 512 entries sebelum flush ke exporter |
| `exporters: loki` | Push ke `http://loki:3100/loki/api/v1/push` |
| `exporters: debug` | Print samples ke stdout untuk development debugging |
| `service: pipelines` | Hubungkan receiver → processor → exporter dalam satu pipeline |

#### `loki-config.yaml`
| Section | Peranan |
|---------|---------|
| `schema_config: tsdb` | Time-series database schema (v13) — optimized untuk log |
| `storage_config: filesystem` | Simpan data di `/loki` directory (Docker volume) |
| `ingester: chunk_block_size: 262144` | 256KB chunk size |
| `ingester: chunk_idle_period: 30m` | Flush chunk selepas 30 min idle |
| `limits_config: max_entries_limit_per_query: 5000` | Batasi query results |
| `compactor: working_directory` | Compaction directory untuk TSDB |

---

### 🟡 FASE 2: Polling — LokiIngester Bridge

#### `agent/loki_ingester.py`
| Class / Method | Jenis | Peranan |
|----------------|-------|---------|
| `LokiIngester` | Class | Background service — bridge antara Loki ↔ ChromaDB + LogWatcher |
| `self._running` | bool | Flag untuk graceful start/stop |
| `self._last_ingested_ts` | int | Nanosecond timestamp — avoid re-ingesting old logs |
| `self._total_ingested` | int | Counter — total log lines processed |
| `self._interval_seconds` | int | Polling interval (default 60s, configurable) |
| `start()` | Method | Start background ingestion loop |
| `stop()` | Method | Cancel background task gracefully |
| `_ingest_loop()` | Method | `while self._running: fetch → process → sleep` |
| `_fetch_and_process()` | Method | **Fungsi utama**: query Loki → parse results → route |
| `httpx.AsyncClient` | HTTP client | Async HTTP ke Loki API (non-blocking) |
| `GET /loki/api/v1/query_range` | API | LogQL query: `{job="syslog"}` with start/end time range |
| `_embed_to_chroma(lines)` | Method | JALUR A: Batch 20 lines → embed via Ollama → simpan ke ChromaDB `network_knowledge` collection, category=`network_log` |
| `_route_to_log_watcher(lines)` | Method | JALUR B: Setiap line → `log_watcher.process_log_line(host, line)` |
| `get_status()` | Method | Return status untuk API endpoint `/logs/loki/ingest` |
| `loki_ingester = LokiIngester()` | Singleton | Global instance |

**Library `httpx`**: Async HTTP client — lebih laju dari `requests` untuk polling loop. Support `AsyncClient` dengan connection pooling dan timeout.

---

### 🟠 FASE 3: Anomaly Detection — LogWatcher

#### `agent/log_watcher.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `AnomalyPattern` | @dataclass | Satu pola anomali — name, pattern (regex), severity, description |
| `AnomalyPattern.compiled` | re.Pattern | Compiled regex — pre-compiled untuk performance (skip recompile setiap kali) |
| `DEFAULT_PATTERNS` | List | 9 built-in anomaly patterns |
| `REMEDIATION_RUNBOOKS` | Dict | 8 runbooks — setiap pattern ada auto_actions, requires_confirmation, prompt |
| `DetectedAnomaly` | @dataclass | Satu insiden dikesan — id, device_ip, severity, log_line, timestamp |
| `DeviceWatchConfig` | @dataclass | Per-device config — enabled, auto_trigger_agent, auto_remediate |
| `LogWatcher` | Class | **JANTUNG DETEKSI**: anomaly detection + agent triggering |
| `self._patterns` | List[AnomalyPattern] | Active patterns (boleh tambah custom via API) |
| `self._anomalies` | List[DetectedAnomaly] | Buffer — max 200 recent anomalies (FIFO) |
| `self._investigations` | List[dict] | Buffer — max 50 investigation results |
| `self._remediation_history` | List[dict] | Buffer — max 100 remediation records |
| `self._agent_callback` | Callable | Callback ke LangGraph agent — dipanggil bila anomaly dikesan |
| `add_device(device_ip)` | Method | Daftar device untuk anomaly monitoring |
| `process_log_line(host, line)` | Method | **ENTRY POINT**: dipanggil oleh LokiIngester, check setiap line |
| `_check_line_for_anomalies()` | Method | Iterate 9 patterns, first match wins → break |
| `_create_anomaly()` | Method | Buat DetectedAnomaly + simpan + alert + ChromaDB |
| `_store_anomaly_to_knowledge()` | Method | Embed anomaly ke ChromaDB sbg "incident" document |
| `_search_similar_incidents()` | Method | **RAG**: Cari insiden serupa + solusi lampau dari ChromaDB |
| `_trigger_agent()` | Method | **AUTO-TRIGGER**: Bina prompt penuh → `network_agent.ainvoke()` |
| `_save_investigation_result()` | Method | Simpan hasil agent ke ChromaDB sbg "solution" |
| `get_status()` | Method | API: status watcher (running, devices, total anomalies) |
| `get_anomalies()` | Method | API: recent anomalies dengan filter |
| `get_patterns()` | Method | API: senarai anomaly patterns |
| `get_investigations()` | Method | API: investigation results |
| `log_watcher = LogWatcher()` | Singleton | Global instance |

**Library `re` (Python stdlib)**: Compiled regex — `re.compile(pattern, re.IGNORECASE)` pre-compile untuk elak compile overhead setiap kali check. 9 patterns × potentially thousands of log lines = performance critical.

---

### 🟣 FASE 4: RAG Context — ChromaDB Knowledge Base

#### `agent/rag_knowledge.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `KnowledgeEntry` | @dataclass | Satu dokumen pengetahuan — title, content, category, tags |
| `KnowledgeEntry.to_document()` | Method | Convert ke `langchain_core.documents.Document` |
| `NetworkKnowledgeBase` | Class | **VEKTOR STORE**: ChromaDB wrapper dengan embedding + search |
| `self._embeddings` | OllamaEmbeddings | Model embedding — guna Ollama model utk generate vector |
| `self._vectorstore` | Chroma | Collection `network_knowledge` — persistent di `data/chroma_db/` |
| `add_document(title, content, category, tags)` | Method | Tambah satu dokumen → auto-embed → simpan vector |
| `add_documents(documents)` | Method | Batch insert — banyak dokumen sekaligus |
| `search(query, k, category)` | Method | **SEMANTIC SEARCH**: cari dokumen relevan berdasarkan makna (bukan keyword) |
| `search_with_scores(query, k)` | Method | Search + relevance scores |
| `get_context_for_query(query, k)` | Method | Format search results sbg RAG context string |
| `count_documents()` | Method | Total dokumen dalam collection |
| `initialize_with_defaults()` | Method | Pre-seed 5 dokumen default network knowledge |
| `get_default_knowledge()` | Function | Return 5 default documents (troubleshooting, Mikrotik, ports, latency, security) |
| `get_knowledge_base()` | Function | Singleton accessor — lazy init |

**Categories dalam ChromaDB:**
| Category | Contoh | Peranan |
|----------|--------|---------|
| `troubleshooting` | "Troubleshooting Koneksi Internet" | Panduan langkah demi langkah |
| `documentation` | "Konfigurasi Router Mikrotik Basic" | Rujukan teknikal |
| `guide` | "Best Practice Keamanan Jaringan" | Standard & policy |
| `network_log` | Log dari LokiIngester | Raw logs untuk semantic search |
| `incident` | Anomaly dari LogWatcher | Insiden untuk pattern matching masa depan |
| `solution` | Investigation result | Solusi terverifikasi — learning loop |

**Library `langchain_chroma`**: Integrasi ChromaDB dengan LangChain ecosystem. `Chroma` class handle connection, collection management, embedding pipeline.
**Library `langchain_community.embeddings.OllamaEmbeddings`**: Guna model Ollama untuk generate text embeddings — tak perlu external API (fully local).

---

### 🔴 FASE 5: Agent Execution — LangGraph ReAct Loop

#### `agent/langgraph_agent.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `AgentState(TypedDict)` | Type | State schema: `messages: Annotated[List[BaseMessage], add_messages]` |
| `add_messages` | Reducer | Auto-append new messages ke state list (bukan replace) |
| `SYSTEM_PROMPT` | str | 230-line prompt — identity, 11 tool categories, vendor support, tool rules, high-risk protocol, communication style |
| `create_agent_node(llm_with_tools, llm_base)` | Function | **FACTORY**: Create agent node function — prepend system prompt, call LLM, handle schema errors |
| `agent_node(state) -> AgentState` | Inner Function | Dipanggil setiap kali graph masuk "agent" node |
| `llm_with_tools.invoke(messages)` | Method | LLM call DENGAN tools — LLM decide nak panggil tool mana |
| `llm_base.invoke(messages)` | Method | Fallback LLM call TANPA tools — untuk model yang tak support JSON schema |
| `build_agent_graph(checkpointer)` | Function | **GRAPH BUILDER**: assemble StateGraph dengan agent + tools nodes |
| `get_all_tools()` | Function | Kumpul semua 25+ tools dari 11 modul |
| `get_llm_with_fallback()` | Function | Dapatkan LLM primary + optional fallback |
| `llm.bind_tools(tools)` | Method | Attach tools sbg function calling capability ke LLM |
| `StateGraph(AgentState)` | Class | Directed graph container |
| `graph.add_node("agent", ...)` | Method | Tambah "agent" node |
| `graph.add_node("tools", ToolNode(tools))` | Method | Tambah "tools" node — auto-execute tools dari LangGraph |
| `graph.add_edge(START, "agent")` | Method | Entry → agent |
| `graph.add_conditional_edges("agent", tools_condition)` | Method | Route: ada tool_calls? → "tools" : END |
| `graph.add_edge("tools", "agent")` | Method | Balik ke agent selepas tools execute |
| `graph.compile(checkpointer)` | Method | Compile graph — return Runnable |
| `NetworkAgent` | Class | **HIGH-LEVEL WRAPPER**: invoke, streaming, session management |
| `self.checkpointer` | MemorySaver | In-memory conversation state storage |
| `self.graph` | CompiledGraph | Compiled LangGraph agent |
| `self._default_thread` | str | Default thread_id = "default" |
| `_get_config(thread_id)` | Method | Build config dict: thread_id + recursion_limit=25 |
| `invoke(query, thread_id)` | Method | Synchronous agent call |
| `ainvoke(query, thread_id)` | Method | **Async agent call** — digunakan oleh LogWatcher |
| `astream(query, thread_id)` | Method | Async generator — yield tokens untuk WebSocket streaming |
| `astream_events(version="v2")` | API | LangGraph streaming API v2 — token-level events |
| `get_history(thread_id)` | Method | Return conversation history dari checkpointer |
| `clear_history(thread_id)` | Method | Clear thread state |
| `network_agent = NetworkAgent(True, True)` | Singleton | **GLOBAL AGENT INSTANCE** |

**Key Libraries:**
| Library | Peranan |
|---------|---------|
| `langgraph.graph.StateGraph` | Build directed stateful graph untuk agent workflow |
| `langgraph.graph.START, END` | Special sentinel nodes |
| `langgraph.graph.message.add_messages` | Auto-append reducer untuk message list |
| `langgraph.prebuilt.ToolNode` | Auto-execute tool calls dari LLM response |
| `langgraph.prebuilt.tools_condition` | Conditional edge — detect tool_calls dalam last message |
| `langgraph.checkpoint.memory.MemorySaver` | In-memory checkpoint storage |
| `langchain_core.messages.*` | Message types: SystemMessage, HumanMessage, AIMessage, ToolMessage |

---

### 🔴 FASE 5 (sambungan): Tool Execution — Network Tools & SSH

#### `tools/network_tools.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `ToolResult` | @dataclass | Standardized return: success(bool), output(str), error(str) |
| `NetworkTools` | Class | **13 NETWORK DIAGNOSTIC TOOLS** |
| `NetworkTools.is_windows` | bool | Platform detection — guna `platform.system()` |
| `ping(host, count)` | Method | `subprocess.run(['ping', '-n'/'4', count, host])` — 30s timeout |
| `traceroute(host)` | Method | `subprocess.run(['tracert','-d'/ 'traceroute','-n', host])` — 60s timeout |
| `dns_lookup(hostname)` | Method | `socket.gethostbyname_ex()` — pure Python DNS |
| `nslookup(domain)` | Method | `subprocess.run(['nslookup', domain])` — system DNS tool |
| `check_port(host, port)` | Method | `socket.connect_ex()` — 5s timeout |
| `port_scan(host, ports)` | Method | Scan 16 common ports — 1s timeout each |
| `get_network_info()` | Method | `socket.gethostname()` + `ipconfig /all` |
| `get_interfaces()` | Method | `psutil.net_if_addrs()` + `net_if_stats()` + `net_io_counters(pernic=True)` |
| `get_connections(kind)` | Method | `psutil.net_connections()` — max 50 |
| `measure_latency(hosts)` | Method | TCP connect port 443 — ukur RTT |
| `get_bandwidth_stats()` | Method | `psutil.net_io_counters()` diff over 1 second |
| `get_provider_info()` | Method | HTTP `ip-api.com/json/` → fallback `ipinfo.io/json` |
| `disable_interface(name)` | Method | ⚠️ HIGH-RISK: `netsh interface set disable` / `ip link set down` |
| `enable_interface(name)` | Method | ⚠️ HIGH-RISK: `netsh interface set enable` / `ip link set up` |
| `network_tools` | Singleton | Global NetworkTools instance |

**Libraries:**
| Library | Peranan |
|---------|---------|
| `subprocess` | Run system commands (ping, traceroute, nslookup, netsh) |
| `socket` | TCP/UDP operations, DNS resolution, port probing |
| `platform` | Detect Windows vs Linux untuk command syntax |
| `psutil` | System metrics — network I/O, connections, interfaces |
| `urllib.request` | HTTP calls ke IP info APIs |

#### `tools/vendor_drivers.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `NETMIKO_AVAILABLE` | bool | Flag — Netmiko installed? Kalau tak, SSH disabled |
| `CommandResult` | @dataclass | Standardized SSH result: success, output, error, execution_time |
| `UnifiedCommand` | Enum | **18 unified commands** — GET_INTERFACES, GET_ROUTING_TABLE, SHUTDOWN_INTERFACE, ... |
| `CommandTranslator` | Class | **TRANSLATION ENGINE**: UnifiedCommand → vendor-specific CLI |
| `TRANSLATIONS` | Dict[VendorType, Dict[UnifiedCommand, str]] | **5 vendors × 18 commands** translation matrix |
| `translate(cmd, vendor, params)` | ClassMethod | Look up translation + substitute parameters |
| `is_write_operation(cmd)` | ClassMethod | Check if command = SHUTDOWN/NO_SHUTDOWN/SET_VLAN |
| `DeviceConnection` | Class | **SINGLE SSH CONNECTION** ke satu device |
| `DeviceConnection.connection` | Netmiko ConnectHandler | Active SSH session |
| `connect()` | Method | `ConnectHandler(**params)` — establish SSH |
| `disconnect()` | Method | `connection.disconnect()` |
| `execute(command, use_textfsm)` | Method | `connection.send_command()` — read timeout 60s |
| `execute_config(commands)` | Method | `connection.send_config_set()` — config mode |
| `ConnectionManager` | Class | **CONNECTION POOL** — max 10 concurrent SSH |
| `self._pool` | Dict[str, DeviceConnection] | Active connections indexed by IP |
| `self._lock` | asyncio.Lock | Thread-safe pool access |
| `get_connection(device)` | Method | Get/create connection — auto cleanup idle >5min |
| `execute_on_device(ip, unified_cmd, params)` | Method | Full flow: resolve→translate→connect→execute→return |
| `execute_raw(ip, raw_command)` | Method | Execute raw CLI tanpa translation |
| `close_all()` | Method | Disconnect semua connections |
| `_resolve_device(ip_or_name)` | Function | **BRIDGE**: cari device dari inventory → fallback infrastructure |
| `connection_manager` | Singleton | Global ConnectionManager instance |

**Library `netmiko`**: Multi-vendor SSH library built on Paramiko. `ConnectHandler` auto-detect device type dan handle prompt detection, pagination (`--More--`), config mode entry/exit.

#### `tools/unified_commands.py`
| Element | Peranan |
|---------|---------|
| `OutputParser` | Parse raw CLI output → structured `NormalizedResult` dataclass |
| `RegexParser` | Vendor-specific regex patterns untuk interfaces, ping stats, CPU/memory |
| `TextFSM support` | Template-based parsing untuk output jadual (optional) |
| `unified_commands` singleton | High-level API: `get_interfaces()`, `get_cpu_memory()`, `shutdown_interface()`, etc. |

#### `agent/langchain_tools.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `@tool` decorator | LangChain | Wrap Python function → LangChain Tool dengan name, description, args_schema |
| `ping(host, count)` | Tool | LangChain wrapper → `network_tools.ping()` |
| `traceroute(host)` | Tool | LangChain wrapper → `network_tools.traceroute()` |
| `check_port(host, port)` | Tool | LangChain wrapper |
| `port_scan(host, ports)` | Tool | LangChain wrapper |
| `dns_lookup(hostname)` | Tool | LangChain wrapper |
| `nslookup(domain)` | Tool | LangChain wrapper |
| `get_network_info()` | Tool | LangChain wrapper |
| `get_provider_info()` | Tool | LangChain wrapper |
| `get_interfaces()` | Tool | LangChain wrapper |
| `get_connections()` | Tool | LangChain wrapper |
| `measure_latency(hosts)` | Tool | LangChain wrapper |
| `get_bandwidth_stats()` | Tool | LangChain wrapper |
| `disable_local_interface(name)` | Tool | ⚠️ HIGH-RISK: Tambah ke PendingActionsStore, return Action ID |
| `enable_local_interface(name)` | Tool | ⚠️ HIGH-RISK: Tambah ke pending store |
| `shutdown_remote_interface(ip, iface)` | Tool | ⚠️ HIGH-RISK: Remote interface shutdown via SSH |
| `enable_remote_interface(ip, iface)` | Tool | ⚠️ HIGH-RISK: Remote interface enable via SSH |
| `execute_cli(ip, cmd)` | Tool | ⚠️ HIGH-RISK: Execute CLI pada remote device |
| `execute_cli_config(ip, cmds)` | Tool | ⚠️ HIGH-RISK: Execute config commands via SSH |
| `confirm_action(action_id)` | Tool | **HITL**: Confirm & execute pending action |
| `cancel_action(action_id)` | Tool | **HITL**: Cancel pending action |
| `get_all_tools()` | Function | **AGGREGATOR**: Kumpul tools dari 11 modul + cache |
| `_TOOLS_CACHE` | Global | Module-level cache — elak repeated dynamic imports |

**Library `langchain_core.tools.tool`**: Decorator yang auto-generate JSON Schema dari Python type hints. LLM guna schema ni untuk structured tool calling.

#### `agent/langchain_llm.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `_PROVIDER_FACTORY` | Dict | Registry: "ollama"→_create_ollama_llm, "openai"→_create_openai_llm, "deepseek"→_create_deepseek_llm |
| `_create_ollama_llm()` | Function | `ChatOllama(model, base_url, temperature=0.7, timeout=45s)` |
| `_create_openai_llm()` | Function | `ChatOpenAI(model, api_key, base_url)` |
| `_create_deepseek_llm()` | Function | `ChatOpenAI` pointed ke `api.deepseek.com/v1` |
| `FallbackLLM` | Class | **RESILIENCE WRAPPER**: primary + fallback LLM |
| `FallbackLLM.invoke()` | Method | Try primary → catch error → retry fallback |
| `FallbackLLM.bind_tools()` | Method | Bind tools ke kedua-dua primary & fallback |
| `FallbackLLM.is_using_fallback` | Property | Monitor sama ada fallback sedang aktif |
| `get_llm_with_fallback()` | Function | Create primary LLM + optional FallbackLLM wrapper |

**Libraries:**
| Library | Peranan |
|---------|---------|
| `langchain_ollama.ChatOllama` | Ollama LLM interface — support tool calling via `bind_tools()` |
| `langchain_openai.ChatOpenAI` | OpenAI-compatible LLM — guna untuk OpenAI & DeepSeek |
| `httpx.HTTPTransport` | Custom HTTP transport dengan ngrok header bypass |

---

### 🟤 FASE 6: Human-in-the-Loop — Guardrails

#### `tools/pending_actions.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `PendingAction` | @dataclass | Satu pending action: action_id, tool_name, params, description, risk_reason |
| `PendingAction.action_id` | str | UUID4[:8] — 8-char unique ID |
| `PendingAction.expires_at` | float | created_at + 300s — auto-expire 5 minit |
| `PendingAction.is_expired` | Property | `time.time() > self.expires_at` |
| `PendingAction.is_valid` | Property | Not expired, not cancelled, not confirmed |
| `PendingActionsStore` | Class | **PENDING STORE** — in-memory dict dengan auto-cleanup |
| `self._actions` | Dict[str, PendingAction] | Active pending actions indexed by action_id |
| `self._executors` | Dict[str, Callable] | Registered executor functions per tool_name |
| `register_executor(name, fn)` | Method | Daftar executor function |
| `add(tool_name, params, desc, risk)` | Method | Add pending action → return PendingAction dengan action_id |
| `get(action_id)` | Method | Retrieve + auto-check expiry |
| `confirm(action_id)` | Method | Confirm → mark confirmed → execute via registered executor |
| `cancel(action_id)` | Method | Cancel → mark cancelled |
| `list_pending()` | Method | Return all valid (unexpired) pending actions |
| `_cleanup_expired()` | Method | Remove expired actions dari store |
| `pending_store` | Singleton | Global PendingActionsStore instance |

**Library `uuid`**: Generate `uuid4()` — random UUID untuk action ID yang unik dan unpredictable (security: tak boleh diteka).

#### `modules/guardrails.py`
| Element | Jenis | Peranan |
|---------|-------|---------|
| `CommandClassifier` | Class | Regex-based risk scoring untuk semua commands |
| `ExecutionPlan` | Class | Multi-step execution plan dengan approval workflow |
| `GuardrailsModule` | Class | Enforce: max iterations, auto-approve threshold, HITL, rollback |
| `RISK_THRESHOLD=0.7` | Config | Auto-approve commands below this risk score |

---

### ⚪ FASE 7: Monitoring — Background Health Checks

#### `modules/monitoring.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `SystemMetrics` | @dataclass | Snapshot: cpu_percent, memory_gb, disk_gb, network_io, process_count |
| `InterfaceMetrics` | @dataclass | Per-interface: bytes_sent/recv, packets, errors_in/out, drops_in/out |
| `MonitoringModule` | Class | **SYSTEM MONITOR**: collect + store + detect anomaly |
| `self._metrics_history` | List | Last 1000 metric points untuk z-score calculation |
| `start_collection(interval)` | Method | Start background thread — collect metrics setiap interval |
| `_collect_metrics()` | Method | Guna `psutil` untuk CPU, RAM, disk, network I/O |
| `detect_anomaly(value)` | Method | z-score vs 50-point rolling window, threshold 3σ |
| `_store_metrics(metrics)` | Method | INSERT ke `metrics.db`: `metrics_raw` table |
| `_rollup_5min()` | Method | Aggregate raw → 5-min averages → `metrics_5min` table |
| `monitoring` | Singleton | Global MonitoringModule instance |

**Library `psutil`**: Cross-platform system metrics — CPU percent, virtual memory, disk usage, network I/O counters, interface stats.

#### `agent/scheduler.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `MonitoringScheduler` | Class | **DEVICE HEALTH CHECK LOOP** |
| `self._running` | bool | Flag untuk start/stop |
| `self._min_interval` | int | Minimum check interval = 10s |
| `_monitoring_loop()` | Method | `while self._running: iterate devices → check → sleep 5s` |
| `_check_device(device)` | Method | Check satu device — detect status change (ONLINE↔OFFLINE↔DEGRADED) |
| `_perform_health_check(device)` | Method | ICMP ping → kalau gagal, TCP fallback (port 80, 443, 22) → port monitoring |
| `_icmp_ping(host)` | Method | Real ICMP ping via system ping command |
| `_check_port(host, port)` | Method | TCP connect probe |
| `_trigger_alert()` | Method | Alert pada status transition (ONLINE→OFFLINE=critical, dsb.) |
| `check_now(device_id)` | Method | On-demand check satu device |
| `check_all_now()` | Method | Check semua devices sekaligus via `asyncio.gather` |
| `scheduler` | Singleton | Global MonitoringScheduler instance |

#### `agent/alerting.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `AlertSeverity` | Enum | INFO, WARNING, CRITICAL |
| `AlertChannel` | Enum | DASHBOARD, WEBHOOK, EMAIL, DISCORD, TELEGRAM |
| `Alert` | @dataclass | Satu alert record — id, device, severity, message, acknowledged |
| `AlertManager` | Class | **MULTI-CHANNEL ALERTING** |
| `create_alert(...)` | Method | Create alert + broadcast ke semua channels |
| `acknowledge_alert(id)` | Method | Mark alert as acknowledged |
| `resolve_alert(id)` | Method | Mark alert as resolved |
| `_broadcast_discord(alert)` | Method | Discord webhook — rich embed, color-coded severity |
| `_broadcast_telegram(alert)` | Method | Telegram bot API — markdown-formatted message |
| `alert_manager` | Singleton | Max 500 alerts in memory |

**Library `aiohttp`**: Async HTTP client — untuk Discord/Telegram/Webhook API calls tanpa blocking.

---

### ⚪ FASE 7: Dashboard & Web Layer

#### `web/websocket_manager.py`
| Class / Element | Jenis | Peranan |
|-----------------|-------|---------|
| `ConnectionManager` | Class | **WEBSOCKET HUB**: manage multiple channels |
| `self.connections` | Dict[str, Set[WebSocket]] | 3 channels: "metrics", "notifications", "chat" |
| `broadcast(channel, data)` | Method | Send JSON ke semua connections dalam channel |
| `broadcast_metrics(data)` | Method | Push metrics ke dashboard |
| `broadcast_notification(data)` | Method | Push alert notification |
| `broadcast_alert(severity, title, msg)` | Method | Push alert dengan severity badge |

#### `web/routes/health.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/health` | GET | System health: ollama_connected, uptime, tool count |
| `/monitoring/metrics` | GET | CPU/RAM/Disk metrics |
| `/monitoring/metrics/history` | GET | Historical metrics dari metrics.db |
| `/network/latency` | GET | Cached latency ke common hosts |
| `/network/bandwidth` | GET | Cached bandwidth stats |
| `/security/status` | GET | Security compliance status |
| `/llm/info` | GET | LLM provider info (model, provider, fallback status) |
| `health_check_background_task()` | Function | Poll Ollama `/api/tags` tiap 30s |
| `network_monitor_task()` | Function | Measure latency+bandwidth tiap 10s |
| `metrics_broadcast_task()` | Function | Push metrics via WebSocket tiap 5s |

#### `web/routes/chat.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/agent/query` | POST | Send query ke agent, return response |
| `/agent/stream` | WebSocket | Token-level streaming chat |
| `/ws/metrics` | WebSocket | Push metrics stream |
| `/agent/conversations/{thread_id}` | GET | Conversation history |
| `/agent/conversations/{thread_id}` | DELETE | Clear conversation |
| `/agent/conversations/query` | POST | Query dengan thread_id spesifik |

#### `web/routes/infrastructure.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/infra/devices` | GET/POST | List / Add devices |
| `/infra/devices/{id}` | GET/PUT/DELETE | CRUD single device |
| `/infra/monitoring/start` | POST | Start scheduler |
| `/infra/monitoring/stop` | POST | Stop scheduler |
| `/infra/execute` | POST | Execute raw command via SSH |
| `/infra/terminal` | WebSocket | Interactive terminal session |
| `/infra/live` | WebSocket | Real-time device state stream |
| `/infra/alerts` | GET | Alert list |

#### `web/routes/logs.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/logs/app` | GET | Application log viewer |
| `/logs/app/stream` | SSE | Server-Sent Events — streaming log tail |
| `/logs/loki` | GET | Loki LogQL queries |
| `/logs/loki/recent` | GET | Recent logs dari Loki |
| `/logs/loki/hosts` | GET | Known hosts in Loki |
| `/logs/loki/ingest` | POST/GET | Control LokiIngester start/stop/status |

#### `web/routes/log_watch.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/logs/watch/start` | POST | Start LogWatcher |
| `/logs/watch/stop` | POST | Stop LogWatcher |
| `/logs/watch/status` | GET | LogWatcher status |
| `/logs/anomalies` | GET | Recent anomalies (with filter) |
| `/logs/patterns` | GET | List anomaly patterns |
| `/logs/investigations` | GET/POST | Get / clear investigations |

#### `web/routes/workflows.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/tools/run` | POST | Execute a single tool |
| `/tools/pending` | GET | List pending actions |
| `/tools/confirm` | POST | Confirm pending action |
| `/tools/cancel` | POST | Cancel pending action |
| `/workflow/create` | POST | Create execution plan |
| `/workflow/stream` | WebSocket | Stream workflow execution |

#### `web/routes/guardrails.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/guardrails/plan` | POST | Create approval plan |
| `/guardrails/pending` | GET | List pending approvals |
| `/guardrails/approve/{id}` | POST | Approve plan/step |
| `/guardrails/reject/{id}` | POST | Reject plan/step |
| `/guardrails/validate` | POST | Validate command safety |
| `/guardrails/status` | GET | Guardrails system status |

#### `web/routes/models.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/agent/models/list` | GET | List 6 available LLM models |
| `/agent/model/switch` | POST | Switch active model → rebuild LangGraph agent |

#### `web/routes/devices.py`
| Route | Method | Peranan |
|-------|--------|---------|
| `/inventory` | GET/POST | List / Add devices |
| `/inventory/{id}` | DELETE | Remove device |
| `/device/command` | POST | Execute command on device |
| `/device/{ip}/interfaces` | GET | Get device interfaces |
| `/device/{ip}/cpu` | GET | Get device CPU |
| `/device/{ip}/routing` | GET | Get routing table |
| `/device/{ip}/arp` | GET | Get ARP table |
| `/device/{ip}/logs` | GET | Get device logs |

---

### 📊 RINGKASAN: Component-to-Phase Mapping

| Fase | Component Utama | Folder/File Terlibat |
|------|----------------|---------------------|
| **0. Startup** | Docker, FastAPI, LangGraph build | `docker-compose.yml`, `Dockerfile`, `web/main.py`, `agent/langgraph_agent.py`, `agent/langchain_tools.py`, `agent/langchain_llm.py` |
| **1. Ingestion** | SNMP trap → syslog → OTel → Loki | `snmptrapd/` (handler.sh, snmptrapd.conf), `otel-config.yaml`, `loki-config.yaml` |
| **2. Polling** | LokiIngester bridge | `agent/loki_ingester.py` |
| **3. Detection** | LogWatcher anomaly scan | `agent/log_watcher.py` (DEFAULT_PATTERNS, process_log_line, _check_line_for_anomalies) |
| **4. RAG Context** | ChromaDB semantic search | `agent/rag_knowledge.py` (search, _search_similar_incidents) |
| **5. Agent Loop** | LangGraph ReAct + tool execution | `agent/langgraph_agent.py`, `tools/network_tools.py`, `tools/vendor_drivers.py`, `agent/langchain_tools.py` |
| **6. HITL** | Pending actions + Guardrails | `tools/pending_actions.py`, `modules/guardrails.py`, `web/routes/workflows.py` |
| **7. Learning** | ChromaDB solution storage | `agent/log_watcher.py` (_save_investigation_result), `agent/rag_knowledge.py` |

---

## 🔧 KRONOLOGI #4: Library & Kemampuan Terminal/CLI — "Tools ni pakai apa?"

> **"Tools kamu pakai library apa? Macam mana dia boleh execute command dekat device?"**
>
> Ini adalah penjelasan TEKNIKAL tentang library yang menjadi tulang belakang setiap kemampuan terminal/CLI/execution dalam sistem.

---

### 🧬 LAPISAN 1: Python Standard Library — Asas Semua Execution

Python stdlib memberi 3 modul utama untuk interaksi dengan sistem operasi dan rangkaian. **Zero external dependency.**

#### `subprocess` — Menjalankan Command Sistem

```
subprocess.run([command], capture_output=True, text=True, timeout=N)
```

| Kegunaan | Command Dijalankan | Tool |
|----------|-------------------|------|
| Ping ke host | `ping -n 4 192.168.1.1` (Windows) / `ping -c 4 192.168.1.1` (Linux) | `ping()` |
| Trace route | `tracert -d 8.8.8.8` (Windows) / `traceroute -n 8.8.8.8` (Linux) | `traceroute()` |
| DNS query | `nslookup google.com` | `nslookup()` |
| Interface disable | `netsh interface set interface "Wi-Fi" disable` (Windows) | `disable_interface()` |
| Interface enable | `netsh interface set interface "Wi-Fi" enable` (Windows) | `enable_interface()` |
| IP link down | `sudo ip link set eth0 down` (Linux) | `disable_interface()` |
| ICMP ping (scheduler) | `ping -n 1 -w 3000 192.168.1.1` | `_icmp_ping()` |

```python
# Contoh sebenar dari network_tools.py
def ping(self, host: str, count: int = 4) -> ToolResult:
    if self.is_windows:
        cmd = ["ping", "-n", str(count), host]
    else:
        cmd = ["ping", "-c", str(count), host]

    result = subprocess.run(
        cmd,
        capture_output=True,   # Tangkap stdout + stderr
        text=True,              # Output sbg string (bukan bytes)
        timeout=30              # Jangan hang > 30 saat
    )
    return ToolResult(
        success=result.returncode == 0,
        output=result.stdout,
        error=result.stderr
    )
```

**Kenapa `subprocess`, bukan library networking khas?**
- `ping` dan `traceroute` perlukan ICMP — Python tak ada built-in ICMP library
- System command sudah teruji bertahun-tahun — lebih reliable dari re-implement sendiri
- Platform detection (`platform.system()`) handle Windows vs Linux syntax secara automatik

---

#### `socket` — Operasi Rangkaian Tahap Rendah (Low-Level)

```
socket.socket(AF_INET, SOCK_STREAM) → connect_ex() → check port
socket.gethostbyname_ex() → DNS resolution
```

| Kegunaan | Operasi | Tool |
|----------|---------|------|
| DNS lookup | `socket.gethostbyname_ex(hostname)` — resolve domain ke IP | `dns_lookup()` |
| Port check | `socket.socket().connect_ex((host, port))` — TCP handshake | `check_port()` |
| Port scan | Loop 16 common ports, connect_ex() setiap port | `port_scan()` |
| Latency measure | TCP connect ke port 443, ukur RTT | `measure_latency()` |
| Local IP | `socket.gethostbyname(socket.gethostname())` | `get_network_info()` |
| TCP fallback ping | Kalau ICMP blocked → TCP connect port 80/443/22 | `_check_port()` |

```python
# Contoh sebenar - port checking
def check_port(self, host: str, port: int, timeout: float = 5.0) -> ToolResult:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)                    # Jangan hang > 5s
    result = sock.connect_ex((host, port))      # 0 = open, !=0 = closed
    sock.close()
    if result == 0:
        return ToolResult(True, f"Port {port} is OPEN on {host}")
    else:
        return ToolResult(False, f"Port {port} is CLOSED on {host}")
```

**Kenapa `socket` handal?**
- `connect_ex()` return immediately dengan status — tak perlu try/except macam `connect()`
- Pure Python, tak perlu subprocess overhead — lebih laju untuk scan banyak port
- `gethostbyname_ex()` guna OS DNS resolver — sama behaviour dengan aplikasi lain

---

#### `asyncio` — Async I/O untuk Non-Blocking Operations

```
asyncio.create_task() → concurrent execution tanpa thread overhead
asyncio.to_thread() → pindah blocking I/O ke thread pool
asyncio.gather() → parallel execution
```

| Kegunaan di Code | Fail/Fungsi |
|------------------|-------------|
| LogWatcher trigger agent (non-blocking) | `network_agent.ainvoke()` — async, tak block detection loop |
| LokiIngester polling loop | `while self._running: fetch → process → await asyncio.sleep(60)` |
| Scheduler health check loop | `while self._running: iterate → await asyncio.sleep(5)` |
| SSH connection (thread offload) | `await asyncio.to_thread(conn.connect)` — Netmiko blocking → thread pool |
| SSH execute command | `await asyncio.to_thread(conn.execute, cmd)` |
| Ping subprocess (thread offload) | `await asyncio.to_thread(_do_ping)` — subprocess blocking → thread pool |
| Background tasks (lifespan) | `asyncio.create_task(health_check_background_task())` |
| Concurrent health checks | `asyncio.gather(*[check_device(d) for d in devices])` |

```python
# Contoh sebenar dari scheduler.py - async dengan thread offload
async def _icmp_ping(self, host: str, timeout: float = 3.0) -> tuple:
    def _do_ping():
        # subprocess.run BLOCKING → tak sesuai untuk async event loop
        result = subprocess.run(['ping', '-n', '1', '-w', str(int(timeout*1000)), host],
                                capture_output=True, text=True, timeout=timeout+2)
        return True, parse_latency(result.stdout) if result.returncode == 0 else (False, -1)

    return await asyncio.to_thread(_do_ping)  # ← Offload ke thread pool!
```

**Kenapa `asyncio.to_thread()` penting?**
- `subprocess.run()` dan Netmiko `send_command()` adalah **blocking I/O**
- Kalau run direct dalam event loop → block semua concurrent operations
- `asyncio.to_thread()` pindah ke thread pool → event loop terus berjalan

---

### 🧬 LAPISAN 2: Netmiko + Paramiko — SSH ke Network Devices

#### `netmiko` (v4.2.0+) — Multi-Vendor SSH Library

```
ConnectHandler → establish SSH session
send_command() → execute CLI command, auto-handle pagination
send_config_set() → enter config mode, apply commands, exit
```

**Ini library PALING PENTING untuk kemampuan terminal SSH ke network devices.**

| Keupayaan | Bagaimana Netmiko Melakukannya |
|-----------|-------------------------------|
| SSH connection | `ConnectHandler(**params)` — auto-detect device type, handle login prompt |
| Command execution | `send_command(cmd, read_timeout=60)` — hantar command, tunggu prompt balik |
| Config mode | `send_config_set([cmd1, cmd2, ...])` — auto `config t`, apply, `exit` |
| Pagination | Auto-detect `--More--` dan hantar space — tak perlu manual |
| Prompt detection | Regex-based prompt matching — tahu bila command dah selesai |
| Error handling | `NetmikoTimeoutException`, `NetmikoAuthenticationException` — spesifik |

```python
# Contoh sebenar dari vendor_drivers.py
class DeviceConnection:
    def connect(self) -> bool:
        params = inventory.get_connection_params(self.device)
        # params contoh: {
        #     'device_type': 'cisco_ios',
        #     'host': '192.168.1.10',
        #     'username': 'admin',
        #     'password': 'password',
        #     'port': 22
        # }
        self.connection = ConnectHandler(**params)      # ← Netmiko auto-detect device
        self.connected = True
        return True

    def execute(self, command: str) -> CommandResult:
        output = self.connection.send_command(           # ← Netmiko execute
            command,
            use_textfsm=False,
            read_timeout=60                              # Timeout 60s untuk command panjang
        )
        return CommandResult(success=True, output=output)

    def execute_config(self, commands: List[str]) -> CommandResult:
        output = self.connection.send_config_set(commands)  # ← Netmiko config mode
        return CommandResult(success=True, output=output)
```

**Netmiko device_type mapping dalam code:**
| Vendor | device_type | Netmiko Driver Class |
|--------|------------|---------------------|
| Cisco IOS | `cisco_ios` | `CiscoIosSSH` |
| Cisco NXOS | `cisco_nxos` | `CiscoNxosSSH` |
| Mikrotik | `mikrotik_routeros` | `MikrotikRouterOsSSH` |
| Ubiquiti | `ubiquiti_edge` | `UbiquitiEdgeSSH` |
| HP Comware | `hp_comware` | `HPComwareSSH` |
| Linux | `linux` | `LinuxSSH` (generic) |

---

#### `paramiko` (v3.4.0+) — Low-Level SSH (dependency Netmiko)

```
Paramiko adalah foundation — Netmiko dibina di atasnya.
```

| Paramiko Component | Digunakan Oleh |
|-------------------|---------------|
| `paramiko.SSHClient` | Netmiko — establish SSH transport |
| `paramiko.Channel` | Netmiko — stdin/stdout/stderr untuk CLI interaction |
| `paramiko.AutoAddPolicy` | Netmiko — auto-accept host keys |
| Key exchange, encryption | Semua SSH traffic — AES, RSA, ECDSA |

**Kenapa pakai Netmiko (bukan Paramiko direct)?**
- Paramiko = SSH protocol sahaja. Anda perlu handle prompt detection, pagination, config mode sendiri.
- Netmiko = Paramiko + 50+ vendor handlers + prompt management + error types.
- Kalau guna Paramiko direct, you'd need ~500 lines code untuk apa yang Netmiko buat dalam 5 lines.

---

### 🧬 LAPISAN 3: psutil — System Metrics & Network Monitoring

#### `psutil` (v5.9.0+) — Cross-Platform System Metrics

```
psutil.net_if_addrs() → IP addresses per interface
psutil.net_if_stats() → interface status (up/down, speed, MTU)
psutil.net_io_counters(pernic=True) → traffic counters per interface
psutil.net_connections() → active TCP/UDP connections
psutil.cpu_percent() → CPU usage
psutil.virtual_memory() → RAM usage
psutil.disk_usage() → Disk usage
```

| Kegunaan | psutil Function | Digunakan Di |
|----------|----------------|--------------|
| List interfaces | `net_if_addrs()` + `net_if_stats()` | `get_interfaces()` → NetworkTools |
| Interface traffic | `net_io_counters(pernic=True)` | `get_interfaces()` |
| Bandwidth usage | `net_io_counters()` diff over 1s | `get_bandwidth_stats()` |
| Active connections | `net_connections(kind='inet')` | `get_connections()` |
| CPU monitoring | `cpu_percent(interval=None)` | `monitoring.py` — background 10s collection |
| RAM monitoring | `virtual_memory()` | `monitoring.py` |
| Disk monitoring | `disk_usage('/')` | `monitoring.py` |
| Process count | `pids()` | `monitoring.py` |

```python
# Contoh sebenar dari network_tools.py
def get_interfaces(self) -> Dict[str, Any]:
    import psutil
    addrs = psutil.net_if_addrs()              # IP addresses
    stats = psutil.net_if_stats()              # up/down, speed, MTU
    io_counters = psutil.net_io_counters(pernic=True)  # traffic stats

    for iface, addrs_list in addrs.items():
        stat = stats.get(iface)
        io = io_counters.get(iface)
        iface_info = {
            "name": iface,
            "is_up": stat.isup if stat else False,
            "speed": stat.speed if stat else 0,
            "mtu": stat.mtu if stat else 0,
            "bytes_sent": io.bytes_sent if io else 0,
            "bytes_recv": io.bytes_recv if io else 0,
            "errors_in": io.errin if io else 0,    # ← CRC errors, etc.
            "errors_out": io.errout if io else 0,
        }
```

**Kenapa psutil (bukan parse `/proc/net/dev` atau `ipconfig`)?**
- Cross-platform — Windows, Linux, macOS dari satu API
- Structured data — return Python dict/list, bukan raw text
- No subprocess overhead — direct system call (C extension)
- Real-time counters — boleh calculate rate (bytes/sec)

---

### 🧬 LAPISAN 4: textfsm + ntc-templates — CLI Output Parsing

#### `textfsm` (v1.1.3+) + `ntc-templates` (v4.0.0+)

```
Raw CLI output → TextFSM template → Structured JSON
```

**Masalah:** Setiap vendor punya format output CLI yang berbeza.

```
Cisco "show ip interface brief":
  GigabitEthernet0/1    10.0.0.1    YES manual up     up
  GigabitEthernet0/5    unassigned  YES unset  down   down

Mikrotik "/interface print":
  #   NAME     TYPE     MTU   ACTUAL-MTU  RUNNING  DISABLED
  0   ether1   ether    1500  1500        true     false
  1   ether2   ether    1500  1500        true     true    ← DISABLED!
```

**Tanpa TextFSM:** Kena tulis regex parser untuk setiap vendor × setiap command = ~100+ regex patterns.

**Dengan TextFSM + ntc-templates:** Guna pre-built templates dari komuniti Network to Code.

```
Cisco "show ip interface brief" + ntc-templates → 
[
  {"interface": "GigabitEthernet0/1", "ip_address": "10.0.0.1", "status": "up", "protocol": "up"},
  {"interface": "GigabitEthernet0/5", "ip_address": "unassigned", "status": "down", "protocol": "down"}
]
```

```python
# Implementasi dalam unified_commands.py
class OutputParser:
    @classmethod
    def parse(cls, output: str, vendor: VendorType, command_type: str):
        # 1. Cuba TextFSM dulu (ntc-templates)
        if TEXTFSM_AVAILABLE:
            parsed = cls._parse_with_textfsm(output, vendor, command_type)
            if parsed:
                return parsed

        # 2. Fallback ke regex patterns (built-in)
        return cls._parse_with_regex(output, command_type)
```

| Parser Method | Bila Digunakan |
|---------------|---------------|
| `parse_interfaces()` | `GET_INTERFACES` — Cisco / Mikrotik / Linux |
| `parse_cpu_memory()` | `GET_CPU_LOAD` — CPU dan memory dari output CLI |
| `_parse_with_regex()` | Fallback — 5 built-in regex patterns |

---

### 🧬 LAPISAN 5: httpx + aiohttp — Async HTTP Client

#### `httpx` — HTTP Client Modern dengan Async Support

```
httpx.AsyncClient → connection pooling, timeout, retry
```

| Kegunaan | HTTP Call | Fail |
|----------|-----------|------|
| Loki query | `GET /loki/api/v1/query_range` | `loki_ingester.py` — polling log baru |
| Loki health check | `GET /ready` | Docker healthcheck internal |
| IP info API | `GET http://ip-api.com/json/` | `get_provider_info()` |
| IP info fallback | `GET https://ipinfo.io/json` | `get_provider_info()` |
| Ollama API | `GET /api/tags` (model list) | `health.py` — background health check |
| Webhook alerts | `POST <webhook_url>` | `alerting.py` — Discord, Telegram |

```python
# Contoh sebenar dari loki_ingester.py
async with httpx.AsyncClient(timeout=15) as client:
    resp = await client.get(
        f"{loki_url}/loki/api/v1/query_range",
        params={
            "query": '{job="syslog"}',
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": "1000",
            "direction": "forward",
        }
    )
    data = resp.json()
```

**Kenapa `httpx` (bukan `requests`)?**
- `requests` = blocking sahaja — tak boleh guna dalam async event loop
- `httpx` = async + sync API, connection pooling, HTTP/2 support
- Interface hampir sama dengan `requests` — mudah belajar

---

### 🧬 LAPISAN 6: urllib — Standard Library HTTP

#### `urllib.request` — Built-in HTTP (Zero Dependency)

```
urllib.request.urlopen() → HTTP GET tanpa external dependency
```

Digunakan untuk `get_provider_info()` — tak perlu install apa-apa.

```python
# Contoh dari network_tools.py
url = "http://ip-api.com/json/?fields=status,..."
req = urllib.request.Request(url, headers={"User-Agent": "NetworkAgent/1.0"})
with urllib.request.urlopen(req, timeout=10) as response:
    data = json.loads(response.read().decode())
```

---

### 📊 Matriks Penuh: Setiap Library → Setiap Kemampuan

| Library | Type | Kemampuan | Tool / Modul |
|---------|------|-----------|-------------|
| **subprocess** | Python stdlib | Execute system binary (ping, traceroute, nslookup, netsh, ip) | `NetworkTools` semua tools |
| **socket** | Python stdlib | TCP connect, DNS resolve, port probing | `dns_lookup`, `check_port`, `port_scan`, `measure_latency` |
| **asyncio** | Python stdlib | Async I/O, thread offload, concurrent tasks | Semua async operations |
| **platform** | Python stdlib | Detect OS untuk command syntax | `NetworkTools.is_windows` |
| **re** | Python stdlib | Regex parsing CLI output | `OutputParser` |
| **uuid** | Python stdlib | Generate unique Action ID | `PendingActionsStore` |
| **json** | Python stdlib | Serialize/deserialize data | Semua API responses |
| **urllib** | Python stdlib | HTTP GET tanpa dependency | `get_provider_info()` |
| | | | |
| **netmiko** | External | SSH ke 50+ network device types | `DeviceConnection`, `ConnectionManager` |
| **paramiko** | External | Low-level SSH protocol | (dependency netmiko) |
| **textfsm** | External | Parse CLI output → structured data | `OutputParser._parse_with_textfsm()` |
| **ntc-templates** | External | 500+ pre-built TextFSM templates | `OutputParser` (planned) |
| **napalm** | External | High-level network automation API | Listed in requirements |
| | | | |
| **psutil** | External | System metrics, network stats, connections | `NetworkTools.get_interfaces/get_connections/get_bandwidth_stats`, `monitoring.py` |
| **httpx** | External | Async HTTP client | `LokiIngester`, `get_provider_info()` |
| **aiohttp** | External | Async HTTP (webhook calls) | `AlertManager` |
| | | | |
| **langgraph** | External | StateGraph agent orchestration | `build_agent_graph()` |
| **langchain** | External | LLM abstraction, tool binding | `get_llm_with_fallback()`, `@tool` decorator |
| **chromadb** | External | Vector database untuk RAG | `NetworkKnowledgeBase` |
| **fastapi** | External | HTTP API framework | `web/main.py`, semua routes |
| **uvicorn** | External | ASGI server | `main.py` |
| **jinja2** | External | HTML template rendering | `dashboard.html` |
| **websockets** | External | WebSocket protocol | `ConnectionManager` |
| **pydantic** | External | Data validation | FastAPI request/response models |
| **python-dotenv** | External | Load .env variables | `config.py` |
| **rich** | External | Terminal formatting | Logging output |
| **openai** | External | OpenAI/DeepSeek API client | `langchain_openai` |

---

### 🔗 Chain of Execution: Dari Agent Prompt → CLI Command di Device

```
1. User / LogWatcher trigger investigation
   ↓
2. LangGraph Agent decide: "Saya perlu check interface"
   ↓
3. LLM output: tool_calls=[{name: "get_interfaces", args: {device_ip: "192.168.1.10"}}]
   ↓                         ↓
   ↓                   [langchain_core.tools.tool]
   ↓                   @tool decorator — JSON Schema dari type hints
   ↓
4. ToolNode execute tool "get_interfaces"                    ← [langgraph.prebuilt.ToolNode]
   ↓
5. LangChain tool wrapper → panggil UnifiedCommandExecutor   ← [agent/langchain_tools.py]
   ↓
6. ConnectionManager.execute_on_device(ip, GET_INTERFACES)   ← [tools/vendor_drivers.py]
   ├── _resolve_device(ip) → cari di inventory.db / devices.db
   ├── CommandTranslator.translate(GET_INTERFACES, CISCO_IOS) → "show ip interface brief"
   └── get_connection(device) → dapatkan/sedia SSH connection
   ↓
7. DeviceConnection.connect()                                ← [tools/vendor_drivers.py]
   └── ConnectHandler(device_type='cisco_ios', host=...,     ← [NETMIKO]
                       username=..., password=...)
       └── paramiko.SSHClient.connect()                      ← [PARAMIKO]
           └── TCP 22 → SSH handshake → established
   ↓
8. asyncio.to_thread(conn.execute, "show ip interface brief") ← [asyncio]
   └── Netmiko send_command("show ip interface brief")       ← [NETMIKO]
       ├── Hantar command ke device via SSH channel
       ├── Tunggu output (read_timeout=60s)
       ├── Handle --More-- pagination
       └── Detect prompt → command selesai
   ↓
9. OutputParser.parse_interfaces(raw_output, CISCO_IOS)      ← [tools/unified_commands.py]
   ├── Split lines, skip header
   ├── Parse: GigabitEthernet0/5 → unassigned → down → down
   └── Return: [{"name": "Gi0/5", "ip": null, "status": "down", "protocol": "down"}]
   ↓
10. NormalizedResult(success=True, data={interfaces: [...]}) ← return ke agent
   ↓
11. LLM terima ToolMessage dengan structured data → analisis → next action
```

---

### 💡 Kenapa Pilihan Library Ini?

| Kenapa Ini | Bukan Ini | Sebab |
|-----------|-----------|-------|
| **Netmiko** | Ansible/nornir | Agent perlu interactive, bukan declarative. Ansible untuk config management, Netmiko untuk ad-hoc commands |
| **subprocess** | Scapy | ping/traceroute tak perlu packet crafting. subprocess guna system binary yang sudah production-tested |
| **psutil** | Parsing /proc | Cross-platform (Windows + Linux). Satu API untuk semua OS |
| **TextFSM** | Manual regex | NTC-Templates ada 500+ pre-built parsers. Jimat masa development |
| **httpx** | requests | Async support — tak block event loop. requests hanya sync |
| **asyncio.to_thread** | Thread manually | Python thread pool managed — elak resource leak |
| **ChromaDB** | Pinecone/Weaviate | Open source, local deployment, no API key needed |
| **Ollama** | OpenAI only | Boleh run fully local — no internet dependency untuk inference |
| **SQLite** | PostgreSQL | Single-node deployment, zero config, portable (satu file) |
| **Loki** | Elasticsearch | Designed khusus untuk logs, lebih ringan dari Elasticsearch, LogQL > Lucene untuk log query |

---

---

## 📋 Ringkasan CV vs Realiti Code

| Claim CV | Realiti Code | Status |
|----------|-------------|--------|
| 30+ network tools | ~25 agent tools + 13 network tools + vendor drivers | ✅ Tepat |
| 8+ pola anomali | 9 built-in anomaly patterns | ✅ Tepat |
| 30+ REST API endpoints | 9 route modules × 3-10 endpoints = 40+ endpoints | ✅ Tepat |
| 4 Docker services | Loki, OTel Collector, SNMP Trap Receiver, AgenticNet | ✅ Tepat |
| Multi-vendor (Cisco, Juniper, MikroTik, Ruijie) | Cisco IOS, Cisco NXOS, MikroTik, Ubiquiti, HP Comware, Linux via Netmiko | ⚠️ Juniper & Ruijie tidak ada dalam code — perlu justify |

---

## 🔴 TOPIK 1: LangGraph Agent Architecture

### Soalan 1: "Explain the LangGraph agent architecture you built."

**Jawapan (Bahasa Inggeris — untuk interview):**

> I built a ReAct (Reasoning + Acting) agent using LangGraph's `StateGraph`. The architecture has two nodes:
>
> 1. **`agent` node** — The LLM-calling node. It invokes the LLM with tools bound via `bind_tools()`. If tool binding fails (some models don't support JSON schema), it automatically falls back to a plain chat LLM without tools.
> 2. **`tools` node** — A `ToolNode` from `langgraph.prebuilt` that executes the actual network tools.
>
> **Flow:**
> ```
> START → agent → [conditional: any tool_calls?]
>                      → YES → tools → agent (loop)
>                      → NO  → END
> ```
>
> The state is a `TypedDict` with an `Annotated[List[BaseMessage], add_messages]` field — LangGraph's built-in message reducer handles appending automatically.
>
> **Key design decisions:**
> - **Recursion limit: 25** — prevents infinite loops
> - **Tool binding fallback** — if a model doesn't support function calling, the graph degrades gracefully to START → agent → END
> - **Singleton pattern** — `NetworkAgent(use_memory=True, persistent=True)` created at module level
> - **Memory** — Uses `MemorySaver` (in-memory checkpointer) for development; designed to switch to `SqliteSaver` for production
> - **Thread isolation** — Each conversation gets a `thread_id` for session-level state separation
> - **Streaming** — `astream()` uses LangGraph's `astream_events` v2 API for token-level streaming to the WebSocket

**📍 Code reference:** `agent/langgraph_agent.py` baris ~15-120

---

### Soalan 2: "How does the system handle LLM failures or models that don't support tool calling?"

**Jawapan:**

> I implemented a **multi-layer fallback strategy**:
>
> **Layer 1 — Tool Binding Fallback:**
> When creating the agent node with `create_agent_node()`, if `bind_tools()` throws an error, the system catches it and falls back to a plain LLM invocation without tools. The graph automatically switches to a simplified topology (START → agent → END).
>
> **Layer 2 — Provider Fallback (`FallbackLLM` class):**
> A custom wrapper class in `langchain_llm.py` that wraps two LLM instances (primary + fallback). On `invoke()` or `ainvoke()` failure, it automatically retries with the fallback provider. Configurable via:
> - `LLM_FALLBACK_ENABLED=true`
> - `LLM_FALLBACK_PROVIDER` (e.g., OpenAI → Ollama, or DeepSeek → OpenAI)
>
> **Layer 3 — Model Switching API:**
> The `/agent/model/switch` endpoint allows runtime model switching. The LangGraph agent is rebuilt with the new model without restarting the server.

**📍 Code reference:** `agent/langgraph_agent.py` `create_agent_node()`, `agent/langchain_llm.py` `FallbackLLM` class

---

### Soalan 3: "What is the system prompt design? How do you control the agent's behavior?"

**Jawapan:**

> The system prompt (~230 lines, in Indonesian/Malay) defines the agent as **"NetOps Sentinel"** — a senior network engineer persona. It covers:
>
> 1. **Identity & role** — senior network engineer with expertise in LAN/WAN/SDN
> 2. **11 tool categories** with descriptions (network diagnostics, device config, topology, backup, monitoring, log investigation, remediation, knowledge base, intelligence, alerting, long-term memory)
> 3. **Supported vendors** — Cisco IOS/NXOS, Mikrotik RouterOS, Ubiquiti EdgeRouter, Linux
> 4. **Tool calling rules** — use appropriate tools, don't guess, verify before acting
> 5. **Troubleshooting strategy** — tiered investigation (Layer 1 → 2 → 3)
> 6. **High-risk operation protocol** — SAVE intent first, copy-paste Action IDs, do NOT re-prompt after confirmation
> 7. **Communication style** — default Bahasa Indonesia, markdown formatting, emojis
> 8. **Error handling** — retry patterns, when to escalate

**📍 Code reference:** `agent/langgraph_agent.py` `SYSTEM_PROMPT` variable

---

## 🔴 TOPIK 2: Observability & Anomaly Detection

### Soalan 4: "Explain your observability pipeline. How do you go from network events to automated remediation?"

**Jawapan:**

> The pipeline has 5 stages:
>
> **Stage 1 — Collect:**
> - SNMP traps via `snmptrapd` (UDP 162) → converted to RFC5424 syslog by `handler.sh`
> - Application logs via Python `logging` with rotating file handler
> - System metrics via `psutil` (CPU, RAM, disk, network I/O) every 10 seconds
>
> **Stage 2 — Aggregate:**
> - Syslog forwarded to OpenTelemetry Collector via UDP 514
> - OTel Collector batches (5s window, up to 512 entries) and exports to Loki
> - Application logs and metrics stored in SQLite (WAL mode) + Loki
>
> **Stage 3 — Store:**
> - **Loki** (Grafana Loki 3.0) — TSDB schema, filesystem storage, in-memory ring — for syslog/structured logs
> - **SQLite** — `metrics.db` (raw, 5min rollup, interface metrics), 24h retention for raw, 30d for rollups
> - **ChromaDB** — vector embeddings of anomalies and solutions for RAG
>
> **Stage 4 — Detect:**
> - **LogWatcher** — 9 regex-based anomaly patterns (explained below)
> - **Monitoring module** — z-score anomaly detection (3σ threshold) + static thresholds
> - **Scheduler** — health checks every 5s (ICMP ping, TCP port fallback for ICMP-blocked hosts)
>
> **Stage 5 — Respond:**
> - LogWatcher auto-triggers LangGraph agent with investigation prompt
> - Agent uses tools (SSH, ping, traceroute, topology) to diagnose
> - Remediation runbooks define auto_actions + actions that need confirmation
> - High-risk actions require HITL approval via pending_actions store
> - Results saved back to ChromaDB as "solution" documents → learning loop

**📍 Code reference:** `agent/log_watcher.py`, `modules/monitoring.py`, `snmptrapd/handler.sh`, `otel-config.yaml`

---

### Soalan 5: "What are the 8+ anomaly patterns you detect?"

**Jawapan:**

> Actually there are **9 built-in patterns** in the LogWatcher:

| # | Pattern | Regex Trigger | Severity |
|---|---------|--------------|----------|
| 1 | **link_down** | `[Ll]ink.*[Dd]own\|interface.*down\|port.*down` | Critical |
| 2 | **link_flap** | `[Ff]lap\|[Uu]p.*[Dd]own.*[Uu]p\|repeated.*[Uu]p.*[Dd]own` | Warning |
| 3 | **auth_failure** | `[Aa]uth.*[Ff]ail\|[Ll]ogin.*[Ff]ail\|[Uu]nauthorized\|AAA.*fail` | High |
| 4 | **system_error** | `[Ee]rror\|[Cc]ritical\|[Ff]atal\|segfault\|kernel.*panic` | Critical |
| 5 | **system_warning** | `[Ww]arning\|[Dd]egrad\|thresh\|limit.*reached` | Warning |
| 6 | **routing_change** | `[Bb][Gg][Pp].*change\|[Oo][Ss][Pp][Ff].*[Dd]own\|[Rr]oute.*[Cc]hange\|[Nn]eighbor.*[Dd]own` | High |
| 7 | **stp_change** | `[Ss][Tt][Pp].*[Cc]hange\|[Ss]panning.*[Tt]ree\|[Tt]opology.*[Cc]hange` | Warning |
| 8 | **hardware_issue** | `[Hh]ardware.*[Ff]ail\|temperature.*high\|[Ff]an.*[Ff]ail\|[Pp]ower.*[Ff]ail` | Critical |
| 9 | *(Bonus)* **unknown** — catch-all for events that don't match but cross severity thresholds |

> Each pattern has:
> - **Regex trigger** — for log matching
> - **Severity level** — for alert prioritization
> - **Auto-actions** — safe automated responses (e.g., gather interface status, check neighbors)
> - **Confirmation-required actions** — dangerous actions needing HITL (e.g., shut/no-shut interface)
> - **Investigation prompt template** — fed to the LangGraph agent
> - **Remediation runbook** — step-by-step resolution procedure

**📍 Code reference:** `agent/log_watcher.py` — `ANOMALY_PATTERNS` dictionary

---

### Soalan 6: "How does the LogWatcher trigger automated investigation?"

**Jawapan:**

> When LogWatcher detects an anomaly:
>
> 1. **Anomaly record created** with timestamp, pattern, source, raw log, severity
> 2. **ChromaDB similarity search** — finds similar past incidents and their solutions (RAG)
> 3. **Investigation prompt assembled** — combines: anomaly details + similar past incidents + remediation runbook + context about affected device
> 4. **LangGraph agent invoked** asynchronously with `ainvoke()`:
>    ```python
>    investigation_prompt = f"""
>    Anomaly detected: {pattern} on {device}
>    Raw log: {log_line}
>    Similar past incidents: {similar_incidents}
>    Runbook: {runbook}
>    Investigate and recommend remediation.
>    """
>    result = await network_agent.ainvoke(investigation_prompt, thread_id=thread_id)
>    ```
> 5. **Agent uses tools** — SSH into device, check interface status, ping neighbors, check routing table, etc.
> 6. **Findings stored** as "investigation" document in ChromaDB with remediation steps
> 7. **If auto-remediation available** → execute immediately
> 8. **If confirmation needed** → push to pending_actions store, notify dashboard via WebSocket, wait for HITL approval
> 9. **Learning loop** — resolved investigation saved as "solution" → future similar incidents get better recommendations

**📍 Code reference:** `agent/log_watcher.py` — `_investigate_anomaly()`, `_trigger_remediation()`

---

## 🔴 TOPIK 3: FastAPI + WebSocket Real-time Dashboard

### Soalan 7: "Tell me about your API architecture. How many endpoints? How is it structured?"

**Jawapan:**

> The FastAPI application has **9 route modules**, each handling a domain:
>
> | Router | Prefix | Purpose | Key Endpoints |
> |--------|--------|---------|--------------|
> | `health.py` | `/health`, `/monitoring`, `/network`, `/security`, `/llm` | System health & metrics | Health check, CPU/RAM/disk metrics, latency, bandwidth, security compliance status, LLM provider info |
> | `chat.py` | `/agent` | AI agent interaction | POST query, GET conversations, DELETE thread, WebSocket streaming chat, WebSocket metrics push |
> | `devices.py` | `/inventory`, `/device` | Device inventory CRUD | CRUD inventory, execute command on device, get interfaces/CPU/routing/ARP/logs |
> | `infrastructure.py` | `/infra` | Infrastructure management | Device CRUD, start/stop monitoring, alerts CRUD, SSH/Telnet exec, terminal panel, WebSocket live state, config export/import |
> | `logs.py` | `/logs` | Log management | Application log viewer (SSE streaming), Loki LogQL queries, Loki ingestion pipeline control |
> | `log_watch.py` | `/logs` | Log watching & anomaly | Start/stop watcher, get anomalies, get patterns, get/post investigations |
> | `models.py` | `/agent` | LLM model management | List available models, switch active model (rebuilds LangGraph agent) |
> | `workflows.py` | `/tools`, `/workflow` | Tool execution | Run tool, pending actions CRUD, confirm/cancel, workflow create, WebSocket workflow stream |
> | `guardrails.py` | `/guardrails` | Safety & approval | Create execution plan, approve/reject, validate command, get status |
>
> **Total: 40+ endpoints** including REST, SSE, and WebSocket endpoints.
>
> **Design patterns:**
> - CORS middleware (all origins)
> - Lifespan context manager for startup/shutdown (modern FastAPI pattern)
> - Background asyncio tasks for: Ollama health polling (30s), network monitoring (10s), metrics broadcast (5s)
> - WebSocket Manager singleton with 3 channels: `metrics`, `notifications`, `chat`

**📍 Code reference:** `web/main.py`, semua file dalam `web/routes/`

---

### Soalan 8: "How does the WebSocket real-time dashboard work?"

**Jawapan:**

> The system uses **3 WebSocket channels** managed by a `ConnectionManager`:
>
> **Channel 1 — `/ws/metrics` (Metrics):**
> - Background task pushes system metrics (CPU, RAM, disk, network) every 5 seconds
> - JSON payload with timestamp, metric name, value
> - Used by dashboard gauges and charts
>
> **Channel 2 — Notifications:**
> - Push alerts, anomalies, status changes
> - `broadcast_alert(severity, title, message)` method
> - Used for real-time alert toasts in dashboard
>
> **Channel 3 — `/agent/stream` (Chat):**
> - Token-level streaming of agent responses using `astream_events` v2
> - Client sends query → agent processes → tokens streamed back in real-time
> - Shows the agent's "thinking" process as it calls tools
>
> **Infrastructure Live WebSocket (`/infra/live`):**
> - Sends full initial state (devices, summary, top 10 alerts) on connect
> - Every 5 seconds sends delta update (summary, devices, alert count, monitoring status)
> - Used by the infrastructure management panel
>
> ```python
> class ConnectionManager:
>     def __init__(self):
>         self.connections: Dict[str, Set[WebSocket]] = {
>             "metrics": set(),
>             "notifications": set(),
>             "chat": set(),
>         }
>
>     async def broadcast(self, channel: str, data: dict):
>         # Copy set before iteration to avoid mutation during disconnect
>         for ws in set(self.connections[channel]):
>             try:
>                 await ws.send_json(data)
>             except WebSocketDisconnect:
>                 self.connections[channel].discard(ws)
> ```

**📍 Code reference:** `web/websocket_manager.py`, `web/routes/infrastructure.py`

---

## 🔴 TOPIK 4: Docker & Deployment

### Soalan 9: "Explain your Docker Compose setup. What are the 4 services and how do they communicate?"

**Jawapan:**

> The system runs on a **`monitoring` bridge network** with 4 services:

```
┌─────────────────────────────────────────────────────┐
│                 monitoring network                    │
│                                                       │
│  ┌──────────┐    UDP:514     ┌──────────────┐        │
│  │ SNMP Trap│ ─────────────→ │  OpenTelemetry│        │
│  │ Receiver │                │   Collector   │        │
│  │ (UDP 162)│                │ (4317, 4318)  │        │
│  └──────────┘                └──────┬───────┘        │
│                                     │ HTTP:3100       │
│                                     ↓                 │
│                              ┌──────────┐            │
│                              │   Loki   │            │
│                              │  (3100)  │            │
│                              └──────────┘            │
│                                     ↑                 │
│                                     │ HTTP:3100       │
│                              ┌──────────────┐        │
│                              │  AgenticNet   │        │
│                              │   (8000)      │        │
│                              └──────────────┘        │
└─────────────────────────────────────────────────────┘
```

> **Service 1 — Loki** (`grafana/loki:3.0.0`)
> - TSDB time-series database for logs
> - Receives from OTel Collector via HTTP
> - Healthcheck: `GET /ready`
> - Volume: `loki-data` for persistence
>
> **Service 2 — OpenTelemetry Collector** (`otel/opentelemetry-collector-contrib:0.96.0`)
> - Receives: syslog (UDP 514), OTLP (gRPC 4317, HTTP 4318)
> - Processor pipeline: memory_limiter (256MB) → resource detection → batch (5s/512) → Loki export
> - Promotes `hostname` → `host.name`, `appname` → `service.name` as Loki labels
>
> **Service 3 — SNMP Trap Receiver** (custom Dockerfile)
> - Ubuntu 22.04 + `snmptrapd` + `snmp-mibs-downloader`
> - Listens on UDP 162 for SNMP traps
> - `handler.sh` converts traps to RFC5424 syslog → forwards to OTel via netcat
> - Environment: `OTEL_HOST=otel-collector`, `OTEL_PORT=514`
>
> **Service 4 — AgenticNet** (custom Dockerfile)
> - Python 3.11-slim, FastAPI on port 8000
> - System deps: `iputils-ping`, `traceroute`, `dnsutils`, `iproute2`, `openssh-client`, `curl`
> - Volume: `./data:/app/data` for SQLite + ChromaDB persistence
> - Healthcheck: `curl -f http://localhost:8000/health`
> - Depends on: Loki (healthy)

**📍 Code reference:** `docker-compose.yml`, `Dockerfile`, `snmptrapd/Dockerfile`

---

## 🔴 TOPIK 5: Multi-Vendor Support

### Soalan 10: "How do you support multiple network vendors?"

**Jawapan:**

> I used **Netmiko** (a Python library built on Paramiko) for SSH connections, plus a **command translation layer**:
>
> **Layer 1 — Netmiko device_type mapping:**
> ```python
> VENDOR_DRIVER_MAP = {
>     "cisco_ios":      CiscoIosDriver,
>     "cisco_nxos":     CiscoNxosDriver,
>     "mikrotik":       MikrotikDriver,
>     "ubiquiti":       UbiquitiDriver,
>     "hp_comware":     ComwareDriver,
>     "linux":          LinuxDriver,
> }
> ```
>
> **Layer 2 — Command translation (`CommandTranslator`):**
> Maps `UnifiedCommand` enum values to vendor-specific CLI. Example:
> ```python
> # Unified: GET_INTERFACES
> # Cisco IOS:    "show ip interface brief"
> # Cisco NXOS:   "show ip interface brief"
> # Mikrotik:     "/interface print"
> # HP Comware:   "display ip interface brief"
> # Linux:        "ip -br addr show"
> ```
>
> **Layer 3 — Output parsing (`OutputParser`):**
> Regex and TextFSM-based parsers normalize vendor output into `NormalizedResult` dataclass. Example: Cisco interface output and Mikrotik interface output both produce the same structured format with `name`, `ip`, `status`, `protocol` fields.
>
> **Layer 4 — Connection pooling:**
> `ConnectionManager` maintains up to 10 concurrent SSH connections with 5-minute idle timeout. This avoids repeated SSH handshake overhead.
>
> **⚠️ Honest note about CV:** The CV mentions Juniper & Ruijie but the code currently supports Cisco IOS, Cisco NXOS, Mikrotik RouterOS, Ubiquiti EdgeRouter, HP Comware, and Linux. If asked about Juniper/Ruijie specifically, I can explain:
> - Netmiko supports Juniper (`juniper_junos`) and Ruijie (`ruijie_os`) device types
> - Adding them requires: (1) adding translations to `CommandTranslator`, (2) adding regex patterns to `OutputParser`, (3) registering in `VENDOR_DRIVER_MAP`
> - The architecture is designed to be extensible — new vendor = new driver class + command mapping

**📍 Code reference:** `tools/vendor_drivers.py`, `tools/unified_commands.py`

---

### Soalan 11: "How do you handle high-risk operations like shutting down an interface?"

**Jawapan:**

> I implemented a **Human-in-the-Loop (HITL) guardrails system**:
>
> **Step 1 — Risk Classification:**
> `CommandClassifier` (regex-based) assigns risk levels:
> - CRITICAL: shutdown, reload, format, erase, write erase
> - HIGH: config changes, VLAN modifications, routing changes
> - MEDIUM: show running-config, debug commands
> - LOW: show commands, ping, traceroute
> - ALWAYS_BLOCKED: rm -rf, format, erase flash
>
> **Step 2 — Pending Actions Store:**
> Before execution, dangerous commands are saved with:
> - `action_id` (UUID4[:8])
> - Tool name, parameters, description
> - Risk reason
> - 5-minute auto-expiry
>
> **Step 3 — Approval Workflow:**
> 1. Agent proposes action → action saved as pending
> 2. Dashboard notified via WebSocket
> 3. Human reviews and clicks Approve/Reject
> 4. On approve → executor runs the command
> 5. On reject/timeout → action discarded, rollback commands generated (e.g., if action was `shutdown`, rollback = `no shutdown`)
>
> **Step 4 — Execution Plan (`ExecutionPlan`):**
> For multi-step operations, a plan with ordered steps is created. Each step can be approved individually or the whole plan approved at once. Configurable max iterations per session (default 5).
>
> ```python
> class PendingAction:
>     action_id: str        # UUID4[:8]
>     tool_name: str        # e.g., "shutdown_interface"
>     params: Dict          # e.g., {"device": "SW-CORE-01", "interface": "Gi0/5"}
>     description: str      # Human-readable
>     risk_reason: str      # Why it's risky
>     created_at: float     # Auto-expires after 300s
> ```

**📍 Code reference:** `tools/pending_actions.py`, `modules/guardrails.py`

---

## 🔴 TOPIK 6: Database & Storage

### Soalan 12: "What databases do you use and why?"

**Jawapan:**

> I use a **polyglot persistence** approach — different databases for different needs:

| Database | Technology | Use Case | Why |
|----------|-----------|----------|-----|
| **Device Inventory** | SQLite (`inventory.db`) | Source of truth for network devices | ACID, portable, zero-config |
| **Infrastructure Devices** | SQLite (`devices.db`) | Monitoring target list | Same DB engine, separate concerns |
| **Metrics Time-Series** | SQLite (`metrics.db`) | CPU/RAM/disk/network metrics | WAL mode, 24h raw retention, 5min rollups (30d) |
| **Chat History** | SQLite (`chat_history.db`) | Conversation persistence | Simple key-value with timestamp |
| **LangGraph Checkpoints** | MemorySaver / SQLite (`conversations.db`) | Agent state persistence | In-memory for dev, SQLite for prod |
| **Vector Store (RAG)** | ChromaDB (`chroma_db/`) | Anomaly embeddings, knowledge base | Semantic search for similar incidents |
| **Logs** | Grafana Loki | Structured logs (syslog, app logs) | TSDB optimized for logs, LogQL query language |
| **Config Backups** | SQLite (`config_backups.db`) | Device configuration backups | BLOB storage for config files |

> **Key design decisions:**
> - SQLite everywhere for operational data — no need for PostgreSQL/MySQL in a single-node deployment
> - WAL mode for concurrent reads during writes
> - ChromaDB for the "learning loop" — each resolved incident becomes training data for future incidents
> - Loki for log aggregation — integrates with the Grafana ecosystem if needed

**📍 Code reference:** `data/` directory, `config.py`, `agent/rag_knowledge.py`

---

## 🔴 TOPIK 7: RAG & Learning Loop

### Soalan 13: "How does the RAG (Retrieval-Augmented Generation) system work?"

**Jawapan:**

> The RAG system uses **ChromaDB** as the vector store with **Ollama embeddings**:
>
> **Knowledge Base (`network_knowledge` collection):**
> - 5 default documents pre-seeded: internet troubleshooting, Mikrotik basic config, common ports, latency troubleshooting, security best practices
> - Categories: `troubleshooting`, `documentation`, `guide`, `network_log`, `incident`, `solution`
>
> **Ingestion pipeline:**
> 1. `LokiIngester` polls Loki every 60 seconds for new logs
> 2. New log entries are embedded via Ollama and stored in ChromaDB
> 3. This enables semantic search over historical logs ("find me logs about BGP neighbor flapping")
>
> **Learning loop:**
> 1. Anomaly detected → stored as "incident" document in ChromaDB
> 2. On investigation → similarity search finds similar past incidents + their solutions
> 3. Agent uses this context to make better decisions
> 4. After resolution → findings saved as "solution" document
> 5. Future similar incidents get better recommendations → system improves over time
>
> ```python
> # Simplified flow
> anomaly = detect_anomaly(log_line)
> similar = chroma_collection.query(anomaly.description, n_results=5)
> prompt = f"""
> New incident: {anomaly}
> Similar past incidents: {similar}
> Known solutions: {[s.solution for s in similar if s.type == 'solution']}
> Investigate and recommend remediation.
> """
> result = await agent.ainvoke(prompt)
> ```

**📍 Code reference:** `agent/rag_knowledge.py`, `agent/loki_ingester.py`, `agent/log_watcher.py`

---

## 🔴 TOPIK 8: Security & Guardrails

### Soalan 14: "What security measures did you implement?"

**Jawapan:**

> Several layers of security:
>
> 1. **Command Classification** — regex-based risk scoring for all device commands
> 2. **Human-in-the-Loop** — high-risk actions require explicit human approval
> 3. **Action Expiry** — pending actions auto-expire after 5 minutes (prevents stale approvals)
> 4. **Rollback Generation** — for every destructive action, a rollback command is prepared
> 5. **Session Limits** — max iterations per agent session (configurable, default 5)
> 6. **Credential Management** — SSH credentials stored in SQLite (design note: should use vault in production)
> 7. **Security Compliance Module** — maps configurations to CIS, NIST, ISO 27001 frameworks
> 8. **Risk Threshold** — configurable `RISK_THRESHOLD=0.7`, auto-approve below this threshold
> 9. **Always Blocked** patterns — regex for `rm -rf`, `format`, `erase flash` — never executable
>
> **What I'd improve for production:**
> - HashiCorp Vault for secrets
> - JWT/OAuth for API authentication (currently open for dev)
> - Audit logging for all HITL decisions
> - RBAC for different operator roles

**📍 Code reference:** `modules/guardrails.py`, `modules/security.py`, `tools/pending_actions.py`

---

## 🎯 SOALAN UMUM (Behavioral)

### "What was the hardest technical challenge?"

> **Jawapan cadangan:** Getting LangGraph tool binding to work reliably across multiple LLM providers. Different models have different levels of function-calling support. Ollama models sometimes don't support it at all. OpenAI and DeepSeek have slightly different JSON schema expectations. The solution was the `create_agent_node()` function with try/except around `bind_tools()` + the `FallbackLLM` wrapper class for provider-level resilience. This means the system degrades gracefully rather than crashing.

### "What would you do differently?"

> **Jawapan cadangan:**
> 1. Use PostgreSQL instead of SQLite for better concurrency (SQLite struggles with concurrent writes from multiple services)
> 2. Add proper authentication (JWT/OAuth2) — currently open for development
> 3. Add comprehensive tests — currently minimal test coverage
> 4. Use Redis for the pending actions store instead of in-memory dict (survives restarts)
> 5. Add support for NETCONF/RESTCONF alongside SSH for modern devices
> 6. Implement proper CI/CD pipeline

### "How does this compare to commercial solutions like Datadog, SolarWinds, or Cisco DNA Center?"

> **Jawapan cadangan:**
> - AgenticNet is an **autonomous** system — it doesn't just alert, it investigates and remediates
> - Commercial tools focus on visibility; AgenticNet focuses on **closed-loop automation**
> - The LLM integration means it can handle **novel situations** — not just pre-programmed responses
> - However: commercial tools have better scalability, polished UIs, vendor support, and compliance certifications
> - Position it as a "proof of concept for AI-driven network operations" rather than a Datadog replacement

---

## 📊 STATISTIK UNTUK JAWAPAN INTERVIEW

| Metrik | Nilai |
|--------|-------|
| Bahasa pengaturcaraan | Python 3.11 |
| Framework AI | LangGraph + LangChain |
| LLM providers | 3 (Ollama, OpenAI, DeepSeek) |
| Agent tools | 25+ |
| Network tools | 13 (ping, traceroute, DNS, port scan, etc.) |
| Anomaly patterns | 9 |
| REST API endpoints | 40+ |
| WebSocket channels | 4 |
| Docker services | 4 |
| Databases | 7 SQLite DBs + ChromaDB + Loki |
| Vendors supported | 6 device types via Netmiko |
| LOC (anggaran) | ~15,000+ lines of Python |

---

## ⚡ KEYWORDS UNTUK DIGUNAKAN DALAM INTERVIEW

- **ReAct agent** — Reasoning + Acting loop
- **StateGraph** — LangGraph's directed graph execution
- **Tool binding** — LangChain's `bind_tools()` for function calling
- **HITL** — Human-in-the-Loop guardrails
- **RAG** — Retrieval-Augmented Generation via ChromaDB
- **Observability pipeline** — SNMP → syslog → OTel → Loki
- **Polyglot persistence** — multiple databases for different needs
- **Closed-loop automation** — detect → investigate → remediate
- **Vendor-agnostic** — unified command interface across vendors
- **Graceful degradation** — fallback when models don't support features
- **Learning loop** — past solutions improve future responses

---

## 🚨 POTENTIAL "GOTCHA" QUESTIONS

1. **"You mention Juniper and Ruijie but I don't see them in your code?"**
   → Jujur: code belum implement, tapi Netmiko support kedua-duanya. Architecture designed to be extensible — tambah vendor = tambah driver class + command mapping je.

2. **"How do you handle concurrent agent requests?"**
   → Singleton `NetworkAgent` with thread_id isolation. LangGraph `MemorySaver` is thread-safe for reads. For production, need async checkpointer (SqliteSaver async) or Redis.

3. **"Where's the test coverage?"**
   → Ada `test_langgraph.py` (unit test untuk graph), `test_multi_llm.py` (LLM switching test), `test_api.js` (API smoke test). Mengaku: test coverage rendah, ini area untuk improvement.

4. **"How do you scale this to 1000 devices?"**
   → Current: single-node architecture. For scale: (1) Redis for state, (2) Celery/RQ for distributed tool execution, (3) PostgreSQL for inventory, (4) Multiple agent workers behind a load balancer, (5) Kafka for event streaming between services.

5. **"Why not use Ansible/nornir for network automation?"**
   → AgenticNet complements Ansible. Ansible is good for declarative config management. AgenticNet is for autonomous incident response — it decides WHAT to do (via LLM reasoning), then executes via SSH. Ansible could be integrated as a tool in the agent's toolkit.

---

*Disusun dari codebase sebenar AgenticNet — Jun 2026*
