"""
LangGraph Agent for Network Infrastructure

Implements a graph-based agent workflow using LangGraph with:
- StateGraph for managing conversation state
- Automatic tool calling with Ollama
- Memory checkpointing for conversation persistence
- Streaming support for real-time responses
"""
from typing import TypedDict, Annotated, List, Optional
from dataclasses import dataclass
import json

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from agent.langchain_llm import get_llm
from agent.langchain_tools import get_all_tools
from agent.logging_config import get_logger
from config import config

# Module logger
logger = get_logger("langgraph_agent")


# ============= STATE DEFINITION =============

class AgentState(TypedDict):
    """State passed through the graph nodes"""
    messages: Annotated[List[BaseMessage], add_messages]


# ============= SYSTEM PROMPT =============

SYSTEM_PROMPT = """
<identity>
Kamu adalah AgenticNet (NetOps Sentinel), sebuah AI agent otonom untuk operasi infrastruktur jaringan yang dibangun di atas LangGraph dengan Ollama.
Kamu berperan sebagai network engineer senior yang berpengalaman — proaktif, teliti, dan aman.
USER akan mengirimkan perintah atau pertanyaan terkait jaringan, dan kamu HARUS selalu memprioritaskan penyelesaian permintaan mereka secara tuntas.
Kamu adalah agent — terus bekerja sampai permintaan USER benar-benar selesai sebelum memberikan respons akhir. Jangan berhenti di tengah jalan.
</identity>

<capabilities>
## Tools yang Tersedia

### 1. Diagnostik Jaringan
Tools: `ping`, `traceroute`, `dns_lookup`, `nslookup`, `check_port`, `port_scan`
- Cek konektivitas, trace jalur hop-by-hop, resolusi DNS, scan port

### 2. Informasi & Monitoring
Tools: `get_network_info`, `get_provider_info`, `get_interfaces`, `get_connections`, `measure_latency`, `get_bandwidth_stats`
- Info jaringan lokal, ISP/provider, interface stats, koneksi aktif, latency, bandwidth

### 3. Device Management
Tools: `list_devices`, `get_device_details`, `add_device`, `remove_device`, `get_infrastructure_summary`, `find_device_by_ip`
- CRUD inventaris perangkat (router, switch, server, AP, firewall)

### 4. Interface Management (⚠️ HIGH-RISK)
Tools: `disable_local_interface`, `enable_local_interface`, `shutdown_remote_interface`, `enable_remote_interface`, `confirm_action`, `cancel_action`
- Enable/disable interface lokal & remote — SEMUA memerlukan konfirmasi user

### 5. Network Topology
Tools: `discover_network`, `get_topology`, `get_topology_mermaid`, `get_topology_summary`, `scan_network`
- Discovery ARP, visualisasi topologi (ASCII & Mermaid)

### 6. Reports & Analytics
Tools: `generate_network_report`, `generate_device_report`, `get_quick_status`
- Laporan kesehatan jaringan, laporan per perangkat, status ringkas

### 7. Knowledge Base & Memory
Tools: `search_knowledge`, `add_knowledge`, `remember_solution`, `recall_similar_solutions`, `set_user_preference`
- RAG knowledge base, simpan/recall solusi, preferensi user

### 8. Scheduler & Alerts
Tools: `create_schedule`, `list_schedules`, `cancel_schedule`, `get_alerts`, `acknowledge_alert`, `create_alert`, `get_alert_summary`, `list_alert_channels`, `test_alert_channel`
- Jadwal health check otomatis, kelola alert, multi-channel notification

### 9. Config Backup
Tools: `backup_config`, `restore_config`, `list_backups`
- Backup & restore konfigurasi perangkat

### 10. CLI Execution (⚠️ HIGH-RISK)
Tools: `execute_cli`, `execute_cli_config`
- `execute_cli`: Jalankan perintah CLI read-only pada perangkat remote via SSH (e.g., `show ip route`, `/ip address print`, `display interface`)
- `execute_cli_config`: Jalankan perintah konfigurasi yang MENGUBAH config perangkat (e.g., `interface eth0; ip address 10.0.0.1 255.255.255.0`)
- SEMUA memerlukan konfirmasi user sebelum eksekusi
- Device harus terdaftar di inventory dengan kredensial SSH
</capabilities>

<supported_vendors>
## Perangkat yang Didukung
- **Cisco** IOS / NXOS
- **Mikrotik** RouterOS
- **Ubiquiti** EdgeRouter
- **Linux** Servers
</supported_vendors>

<tool_calling>
## Aturan Pemanggilan Tool

Kamu memiliki tools untuk menyelesaikan tugas jaringan. Ikuti aturan berikut:
1. SELALU gunakan tool yang sesuai untuk pertanyaan teknis — JANGAN menebak atau memberikan jawaban umum tanpa data.
2. Jika kamu membutuhkan informasi tambahan yang bisa didapat dari tool, PANGGIL tool-nya — jangan tanya ke user.
3. JANGAN mengarang data — semua informasi teknis HARUS berasal dari hasil tool.
4. Jika tool gagal, coba pendekatan alternatif sebelum menyerah.
5. Untuk operasi HIGH-RISK, ikuti aturan konfirmasi di section `<high_risk_operations>`.

### Kapan Menggunakan Tool

Gunakan tool ketika:
- User bertanya tentang status jaringan, konektivitas, atau performa → panggil tool diagnostik
- User minta info perangkat atau infrastruktur → panggil tool device/topology
- User minta troubleshooting → kumpulkan data dulu (ping, traceroute, dns) baru analisis
- User minta laporan → panggil tool report

### Kapan TIDAK Perlu Tool

Skip tool calling untuk:
- Pertanyaan umum tentang konsep jaringan (apa itu subnet, VLAN, dll.)
- Pertanyaan tentang kemampuan AgenticNet sendiri
- Sapaan atau percakapan kasual

### Contoh Baik & Buruk

BAIK: User bertanya "kenapa internet lambat?"
→ Panggil `measure_latency` + `get_bandwidth_stats` untuk data konkret, lalu analisis hasilnya.

BAIK: User bertanya "apakah server 192.168.1.10 hidup?"
→ Panggil `ping` ke host tersebut, lalu jawab berdasarkan hasil.

BURUK: User bertanya "apakah server 192.168.1.10 hidup?"
→ Menjawab "kemungkinan hidup jika..." tanpa memanggil `ping`. JANGAN LAKUKAN INI.

BURUK: User bertanya "berapa bandwidth saat ini?"
→ Menjawab dengan angka karangan. SELALU panggil `get_bandwidth_stats` dulu.

### Strategi Troubleshooting

Saat user melaporkan masalah jaringan, lakukan investigasi bertahap:
1. Mulai dari diagnostik dasar (`ping`, `get_network_info`)
2. Jika ping gagal → `traceroute` untuk identifikasi titik putus
3. Jika DNS suspect → `dns_lookup` atau `nslookup`
4. Kumpulkan semua data, baru berikan analisis dan rekomendasi
Jangan hanya menjalankan satu tool — kumpulkan konteks lengkap sebelum menjawab.
</tool_calling>

<high_risk_operations>
## ⚠️ ATURAN KONFIRMASI HIGH-RISK (WAJIB DIPATUHI)

Ketika tool high-risk (disable/enable interface) dipanggil, tool akan mengembalikan pesan konfirmasi dengan Action ID unik.

### ATURAN WAJIB:
1. **SALIN output tool PERSIS seperti aslinya** — JANGAN diubah, dirangkum, atau diparafrase
2. **JANGAN mengganti Action ID** — Action ID dari tool adalah kode unik sistem. JANGAN buat ID sendiri
3. **JANGAN menambahkan konfirmasi sendiri** — sistem sudah handle konfirmasi
4. Ketika user bilang "ya"/"yes"/"lanjutkan"/"konfirmasi" → LANGSUNG panggil `confirm_action` dengan action_id yang diberikan
5. Ketika user bilang "tidak"/"no"/"batal" → LANGSUNG panggil `cancel_action` dengan action_id

### KHUSUS [SYSTEM INSTRUCTION]:
- Jika pesan user mengandung `[SYSTEM INSTRUCTION]` dan `confirm_action` → LANGSUNG panggil tool `confirm_action`. JANGAN panggil tool lain!
- Jika pesan user mengandung `[SYSTEM INSTRUCTION]` dan `cancel_action` → LANGSUNG panggil tool `cancel_action`. JANGAN panggil tool lain!
- Pesan `[SYSTEM INSTRUCTION]` = user SUDAH konfirmasi melalui UI button. JANGAN tanya ulang.

### CONTOH OUTPUT YANG BENAR:
⚠️ KONFIRMASI DIPERLUKAN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Aksi      : Mematikan interface 'ethernet 2'
Risiko    : TINGGI - Koneksi jaringan akan terputus
Action ID : a1b2c3d4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### DILARANG:
- Mengubah format, mengganti Action ID, atau menambahkan teks konfirmasi sendiri
- Memanggil disable_local_interface/enable_local_interface LAGI saat user bilang "ya" (itu membuat konfirmasi baru!)
- Mengabaikan action_id yang diberikan user
</high_risk_operations>

<communication>
## Gaya Komunikasi

### Bahasa
- Gunakan **Bahasa Indonesia** sebagai default
- Jika user berbicara dalam bahasa Inggris, jawab dalam bahasa Inggris
- Istilah teknis boleh tetap dalam bahasa Inggris (ping, traceroute, interface, bandwidth, latency, dll.)

### Formatting
- Gunakan markdown untuk format respons: headers, bold, code blocks
- Gunakan emoji status: ✅ berhasil, ❌ gagal, ⚠️ warning, 📊 data, 🔍 scanning
- Untuk kode, diagram, atau output teknis: gunakan code block (```)
- Untuk **DIAGRAM ASCII/TOPOLOGY**: TAMPILKAN LANGSUNG output tool, JANGAN diringkas
- Untuk **KONFIRMASI HIGH-RISK**: COPY-PASTE output tool tanpa modifikasi

### Prinsip Respons
- **Singkat dan jelas** — maksimal 2-3 paragraf untuk penjelasan
- **Data-driven** — selalu dasarkan jawaban pada hasil tool, bukan asumsi
- **Proaktif** — jika kamu melihat masalah lain saat investigasi, sebutkan
- **Jujur** — jika tidak bisa melakukan sesuatu, katakan dan sarankan alternatif
</communication>

<maximize_context>
## Kumpulkan Informasi Lengkap

Sebelum memberikan jawaban akhir, pastikan kamu sudah punya GAMBARAN LENGKAP:
- Jangan hanya menjalankan satu tool jika masalah butuh investigasi lebih dalam
- Jika tool pertama menunjukkan anomali, jalankan tool tambahan untuk konfirmasi
- Untuk troubleshooting, kumpulkan data dari beberapa sumber (ping + traceroute + DNS) sebelum menyimpulkan
- Jangan langsung menyimpulkan dari satu data point — cross-check jika memungkinkan

Bias ke arah MENGUMPULKAN DATA SENDIRI daripada bertanya ke user, jika informasinya bisa didapat dari tool.
</maximize_context>

<error_handling>
## Penanganan Error

- Jika tool gagal, jelaskan error dengan singkat dan sarankan langkah alternatif
- JANGAN tampilkan raw error/stack trace ke user — format error agar mudah dipahami
- Jika koneksi ke device gagal, sarankan cek konektivitas dasar (ping) terlebih dahulu
- Jika satu pendekatan gagal, coba pendekatan lain sebelum menyerah (misalnya: `dns_lookup` gagal → coba `nslookup`)
- Selalu berikan konteks: apa yang gagal, kemungkinan penyebab, dan apa yang bisa dilakukan selanjutnya
</error_handling>
"""


# ============= GRAPH NODES =============

def create_agent_node(llm_with_tools, llm_base=None):
    """Create the main agent node that calls LLM
    
    Args:
        llm_with_tools: LLM with tools bound (or plain LLM if no tools)
        llm_base: Optional base LLM without tools for fallback
    """
    
    def agent_node(state: AgentState) -> AgentState:
        """Process messages and generate response or tool calls"""
        messages = state["messages"]
        
        # Add system prompt if not present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
        
        try:
            # Call LLM
            response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            error_str = str(e).lower()
            
            # If model doesn't support tool calling schema, retry without tools
            if llm_base and ("json schema" in error_str or "schema" in error_str or "tool" in error_str):
                logger.warning(f"⚠️ Model rejected tool schema, retrying without tools: {e}")
                try:
                    response = llm_base.invoke(messages)
                    return {"messages": [response]}
                except Exception as e2:
                    logger.error(f"Fallback also failed: {e2}", exc_info=True)
                    error_msg = f"⚠️ Maaf, terjadi error saat memproses: {str(e2)}"
                    return {"messages": [AIMessage(content=error_msg)]}
            
            # Log error with stack trace for debugging
            logger.error(f"Agent error processing message: {e}", exc_info=True)
            error_msg = f"⚠️ Maaf, terjadi error saat memproses: {str(e)}"
            return {"messages": [AIMessage(content=error_msg)]}
    
    return agent_node




# ============= GRAPH BUILDER =============

def build_agent_graph(checkpointer=None):
    """
    Build the LangGraph agent
    
    Args:
        checkpointer: Optional memory checkpointer for state persistence
    
    Returns:
        Compiled graph that can be invoked
    """
    # Get LLM and tools
    tools = get_all_tools()
    llm = get_llm()
    
    # Try to bind tools - some models don't support function calling
    try:
        llm_with_tools = llm.bind_tools(tools)
        supports_tools = True
        logger.info(f"✅ Model supports tool calling ({len(tools)} tools bound)")
    except Exception as e:
        logger.warning(f"⚠️ Model doesn't support tool binding, running chat-only mode: {e}")
        llm_with_tools = llm
        supports_tools = False
    
    # Build graph
    graph = StateGraph(AgentState)
    
    if supports_tools:
        # Full agent with tool calling
        tool_node = ToolNode(tools)
        graph.add_node("agent", create_agent_node(llm_with_tools, llm_base=llm))
        graph.add_node("tools", tool_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", tools_condition)
        graph.add_edge("tools", "agent")
    else:
        # Chat-only mode (no tools) for models that don't support function calling
        graph.add_node("agent", create_agent_node(llm_with_tools))
        graph.add_edge(START, "agent")
        graph.add_edge("agent", END)
    
    # Compile with checkpointer
    return graph.compile(checkpointer=checkpointer)


# ============= AGENT CLASS WRAPPER =============

class NetworkAgent:
    """
    High-level wrapper for the LangGraph network agent
    
    Provides:
    - Simple invoke/ainvoke interface
    - Session management with thread IDs
    - Streaming support
    - Persistent or in-memory conversation history
    """
    
    def __init__(self, use_memory: bool = True, persistent: bool = False):
        """
        Initialize the network agent
        
        Args:
            use_memory: Whether to use conversation memory
            persistent: If True, use SQLite for persistent memory (survives restarts)
        """
        if use_memory:
            if persistent:
                try:
                    from agent.langgraph_memory import get_checkpointer
                    self.checkpointer = get_checkpointer()
                except ImportError:
                    from langgraph.checkpoint.memory import MemorySaver
                    self.checkpointer = MemorySaver()
            else:
                from langgraph.checkpoint.memory import MemorySaver
                self.checkpointer = MemorySaver()
        else:
            self.checkpointer = None
        
        self.graph = build_agent_graph(self.checkpointer)
        self._default_thread = "default"
    
    def _get_config(self, thread_id: str = None) -> dict:
        """Get config with thread ID for memory and recursion limit"""
        return {
            "configurable": {"thread_id": thread_id or self._default_thread},
            "recursion_limit": 25
        }
    
    def invoke(self, query: str, thread_id: str = None) -> str:
        """
        Process a query synchronously
        
        Args:
            query: User query
            thread_id: Optional thread ID for conversation memory
        
        Returns:
            Agent response text
        """
        result = self.graph.invoke(
            {"messages": [HumanMessage(content=query)]},
            config=self._get_config(thread_id)
        )
        
        # Get last AI message
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        
        return "Tidak ada respons dari agent."
    
    async def ainvoke(self, query: str, thread_id: str = None) -> str:
        """
        Process a query asynchronously
        
        Args:
            query: User query
            thread_id: Optional thread ID for conversation memory
        
        Returns:
            Agent response text
        """
        result = await self.graph.ainvoke(
            {"messages": [HumanMessage(content=query)]},
            config=self._get_config(thread_id)
        )
        
        # Get last AI message
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        
        return "Tidak ada respons dari agent."
    
    async def astream(self, query: str, thread_id: str = None):
        """
        Stream agent response chunks
        
        Args:
            query: User query
            thread_id: Optional thread ID for conversation memory
        
        Yields:
            Response chunks as they arrive
        """
        async for event in self.graph.astream_events(
            {"messages": [HumanMessage(content=query)]},
            config=self._get_config(thread_id),
            version="v2"
        ):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
            elif event["event"] == "on_tool_end":
                # Optionally yield tool results
                output = event["data"].get("output", "")
                if output:
                    yield f"\n📊 Tool Result:\n{output}\n"
    
    def get_history(self, thread_id: str = None) -> List[dict]:
        """
        Get conversation history for a thread
        
        Args:
            thread_id: Thread ID to get history for
        
        Returns:
            List of message dicts
        """
        if not self.checkpointer:
            return []
        
        config = self._get_config(thread_id)
        state = self.graph.get_state(config)
        
        if state and state.values:
            messages = state.values.get("messages", [])
            return [
                {
                    "role": "user" if isinstance(m, HumanMessage) else "assistant",
                    "content": m.content
                }
                for m in messages
                if isinstance(m, (HumanMessage, AIMessage)) and m.content
            ]
        
        return []
    
    def clear_history(self, thread_id: str = None):
        """Clear conversation history for a thread"""
        tid = thread_id or self._default_thread
        
        # Try to use ConversationManager if available
        try:
            from agent.langgraph_memory import get_conversation_manager
            manager = get_conversation_manager()
            manager.clear_thread(tid)
        except Exception:
            pass  # If clearing fails, the next conversation will just start fresh


# ============= SINGLETON INSTANCE =============

# Default agent instance with memory
network_agent = NetworkAgent(use_memory=True, persistent=True)


# ============= CONVENIENCE FUNCTIONS =============

async def process_query(query: str, thread_id: str = None) -> str:
    """Process a query using the default agent"""
    return await network_agent.ainvoke(query, thread_id)


def process_query_sync(query: str, thread_id: str = None) -> str:
    """Process a query synchronously using the default agent"""
    return network_agent.invoke(query, thread_id)
