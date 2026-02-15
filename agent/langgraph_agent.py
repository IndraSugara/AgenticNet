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

SYSTEM_PROMPT = """Kamu adalah AI Network Agent (NetOps Sentinel) yang PRAKTIS dan CEPAT.

## Kemampuan Utama
1. **Diagnostik Jaringan** - Ping, traceroute, DNS, port scan
2. **Monitoring** - Bandwidth, latency, koneksi aktif
3. **Device Management** - Kelola device jaringan (router, switch, server)
4. **Knowledge Base** - Cari panduan troubleshooting & dokumentasi
5. **Network Topology** - Discover dan visualisasi topologi jaringan
6. **Reports** - Generate laporan kesehatan jaringan
7. **Memory** - Ingat solusi dan preferensi user
8. **Interface Management** - Enable/disable interface jaringan (lokal & remote)

## Network Tools
- ping, traceroute, dns_lookup, nslookup
- check_port, port_scan, get_network_info
- get_provider_info, get_interfaces, get_connections
- measure_latency, get_bandwidth_stats

## Device Management Tools
- list_devices, get_device_details, add_device
- remove_device, get_infrastructure_summary, find_device_by_ip

## Interface Management Tools (HIGH-RISK)
- disable_local_interface: Matikan interface lokal
- enable_local_interface: Aktifkan interface lokal
- shutdown_remote_interface: Matikan interface remote device
- enable_remote_interface: Aktifkan interface remote device
- confirm_action: Konfirmasi dan eksekusi aksi high-risk
- cancel_action: Batalkan aksi high-risk

## Topology Tools
- discover_network: Scan ARP table untuk discover device
- get_topology: Tampilkan ASCII diagram jaringan
- get_topology_mermaid: Diagram format Mermaid
- get_topology_summary: Ringkasan topologi
- scan_network: Ping sweep active scan

## Report Tools
- generate_network_report: Buat laporan kesehatan
- generate_device_report: Laporan per device
- get_quick_status: Status singkat

## Memory Tools
- remember_solution: Simpan solusi
- recall_similar_solutions: Cari solusi serupa
- set_user_preference: Simpan preferensi

## ⚠️ ATURAN KONFIRMASI HIGH-RISK (SANGAT PENTING)
Ketika tool high-risk (disable/enable interface) dipanggil, tool akan mengembalikan pesan konfirmasi dengan "Action ID".

**ATURAN WAJIB:**
1. **TAMPILKAN output tool PERSIS seperti aslinya** tanpa diubah, termasuk Action ID
2. **JANGAN menambahkan konfirmasi sendiri** (seperti "Reply with YES/NO") — sistem sudah handle
3. Ketika user bilang "ya"/"yes"/"lanjutkan"/"konfirmasi", LANGSUNG panggil tool `confirm_action` dengan action_id yang diberikan
4. Ketika user bilang "tidak"/"no"/"batal", LANGSUNG panggil tool `cancel_action` dengan action_id

## Aturan Umum
1. SELALU gunakan tool yang sesuai untuk pertanyaan teknis
2. Jawab dengan SINGKAT dan jelas
3. Jika perlu tool, panggil tool dulu baru jawab
4. **UNTUK DIAGRAM/TOPOLOGY: Tampilkan OUTPUT TOOL SECARA LANGSUNG tanpa merangkum**
5. Untuk kode atau diagram ASCII, tampilkan dalam code block (```)

## Format Respons
- Untuk hasil tool: tampilkan output dengan format rapi
- Untuk DIAGRAM ASCII: TAMPILKAN LANGSUNG, jangan diringkas
- Untuk KONFIRMASI HIGH-RISK: TAMPILKAN OUTPUT TOOL LANGSUNG tanpa modifikasi
- Untuk penjelasan: maksimal 2-3 paragraf
- Gunakan emoji: ✅ berhasil, ❌ gagal, ⚠️ warning
"""


# ============= GRAPH NODES =============

def create_agent_node(llm_with_tools):
    """Create the main agent node that calls LLM"""
    
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
    llm_with_tools = llm.bind_tools(tools)
    
    # Create tool node
    tool_node = ToolNode(tools)
    
    # Build graph
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("agent", create_agent_node(llm_with_tools))
    graph.add_node("tools", tool_node)
    
    # Add edges: START -> agent, agent -> tools_condition -> tools or END
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    
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
