"""
Agent Core - ODRVA Cycle Implementation

Observe → Reason → Decide → Act → Verify

Optimized with async LLM calls and timeout handling per phase.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
from datetime import datetime
import json
import asyncio

from agent.llm_client import llm_client, LLMClient
from agent.transparency import transparency, TransparencyModule, DecisionRecord
from config import config


class CyclePhase(Enum):
    """ODRVA Cycle phases"""
    OBSERVE = "observe"
    REASON = "reason"
    DECIDE = "decide"
    ACT = "act"
    VERIFY = "verify"


@dataclass
class CycleContext:
    """Context passed through the ODRVA cycle"""
    query: str
    observations: List[str] = field(default_factory=list)
    reasoning: str = ""
    decision: Optional[DecisionRecord] = None
    action_result: str = ""
    verification: str = ""
    blocked: bool = False
    block_reason: str = ""
    # New: timing info
    phase_times: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None


class NetworkAgent:
    """
    Agentic AI Network Infrastructure Operator
    
    Implements the mandatory ODRVA cycle:
    - Observe: Gather data and context
    - Reason: Analyze situation and options
    - Decide: Choose action with justification
    - Act: Execute carefully (with risk checks)
    - Verify: Validate results
    
    Optimized with:
    - Async LLM calls
    - Per-phase timeouts
    - Progress callbacks
    """
    
    # Default timeout per phase (seconds) - Reduced for faster responses
    PHASE_TIMEOUTS = {
        CyclePhase.OBSERVE: 30,
        CyclePhase.REASON: 30,
        CyclePhase.DECIDE: 30,
        CyclePhase.ACT: 60,
        CyclePhase.VERIFY: 30,
    }
    
    def __init__(
        self, 
        llm: LLMClient = None, 
        transparency_module: TransparencyModule = None
    ):
        self.llm = llm or llm_client
        self.transparency = transparency_module or transparency
        self.tools: Dict[str, Callable] = {}
        self.current_phase = CyclePhase.OBSERVE
        self.history: List[CycleContext] = []
        self._progress_callback: Optional[Callable] = None
        
    def register_tool(self, name: str, func: Callable, description: str = ""):
        """Register a tool that the agent can use"""
        self.tools[name] = {
            "function": func,
            "description": description
        }
    
    def set_progress_callback(self, callback: Callable[[CyclePhase, str], None]):
        """Set callback for progress updates during cycle"""
        self._progress_callback = callback
    
    async def _notify_progress(self, phase: CyclePhase, status: str):
        """Notify progress callback if set"""
        if self._progress_callback:
            try:
                if asyncio.iscoroutinefunction(self._progress_callback):
                    await self._progress_callback(phase, status)
                else:
                    self._progress_callback(phase, status)
            except Exception:
                pass  # Ignore callback errors
    
    async def quick_response(self, query: str) -> str:
        """
        Quick response mode with LLM-driven tool selection
        LLM decides which tools to call based on understanding the query
        """
        # Build tools description for LLM with parameter info
        tools_desc = """- ping: Cek konektivitas ke host (params: host)
- traceroute: Trace route ke host (params: host)
- dns_lookup: DNS lookup (params: hostname)
- check_port: Cek port tertentu (params: host, port)
- port_scan: Scan port umum (params: host)
- get_network_info: Info jaringan lokal (no params)
- get_provider_info: Info ISP/provider internet (no params)
- nslookup: Query DNS (params: domain)
- get_interfaces: List network interfaces (no params)
- get_connections: List koneksi aktif (no params)
- measure_latency: Ukur latency (no params)
- get_bandwidth_stats: Statistik bandwidth (no params)"""
        
        # Ask LLM to select tools AND extract parameters
        tool_selection_prompt = f"""Kamu adalah Network Agent. Pilih tool yang tepat dan extract parameter dari pertanyaan.

Pertanyaan: {query}

Tools:
{tools_desc}

Format JSON (WAJIB):
{{"tools": [{{"name": "tool_name", "params": {{"host": "value"}}}}], "reason": "alasan"}}

Contoh:
- "ping google.com" → {{"tools": [{{"name": "ping", "params": {{"host": "google.com"}}}}], "reason": "cek konektivitas"}}
- "scan port localhost" → {{"tools": [{{"name": "port_scan", "params": {{"host": "localhost"}}}}], "reason": "cek port terbuka"}}
- "cek ISP" → {{"tools": [{{"name": "get_provider_info", "params": {{}}}}], "reason": "info provider"}}

DEFAULTS jika tidak disebutkan: host=localhost, domain=google.com
Jika tidak butuh tool: {{"tools": [], "reason": "pertanyaan umum"}}"""

        try:
            response = await self.llm.chat_async(
                [{"role": "user", "content": tool_selection_prompt}],
                timeout=300
            )
            content = response['message']['content']
            
            # Parse tool selection
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                selection = json.loads(json_match.group())
                selected_tools = selection.get("tools", [])
                
                # Execute selected tools with parameters
                tool_results = []
                for tool_info in selected_tools:
                    # Handle both formats: string or dict
                    if isinstance(tool_info, str):
                        tool_name = tool_info
                        params = {}
                    else:
                        tool_name = tool_info.get("name", tool_info) if isinstance(tool_info, dict) else str(tool_info)
                        params = tool_info.get("params", {}) if isinstance(tool_info, dict) else {}
                    
                    if tool_name in self.tools:
                        result = await self._execute_tool(tool_name, params)
                        tool_results.append((tool_name, result))
                
                # If tools were executed, format results
                if tool_results:
                    response_text = "## Hasil Eksekusi\n\n"
                    for tool_name, result in tool_results:
                        response_text += f"### {tool_name}\n"
                        if isinstance(result, dict):
                            if result.get('success'):
                                if 'output' in result:
                                    response_text += f"```\n{result['output'][:800]}\n```\n"
                                else:
                                    for k, v in result.items():
                                        if k not in ['success', 'raw']:
                                            response_text += f"- **{k}**: {v}\n"
                            else:
                                response_text += f"❌ Error: {result.get('error', 'Unknown')}\n"
                        else:
                            response_text += f"{result}\n"
                        response_text += "\n"
                    return response_text
                
                # No tools selected - answer directly
                return await self._direct_answer(query)
            
        except Exception as e:
            # Fallback to direct answer on error
            pass
        
        return await self._direct_answer(query)
    
    async def _direct_answer(self, query: str) -> str:
        """Direct LLM answer when no tools needed"""
        prompt = f"""Jawab pertanyaan ini dengan SINGKAT (max 2-3 kalimat).
Pertanyaan: {query}
Tools tersedia: {', '.join(self.tools.keys()) if self.tools else 'tidak ada'}
Jawab langsung tanpa format verbose."""
        
        try:
            response = await self.llm.chat_async(
                [{"role": "user", "content": prompt}],
                timeout=300
            )
            return response['message']['content']
        except Exception as e:
            return f"Error: {e}"
    
    async def _execute_tool(self, tool_name: str, params: dict) -> dict:
        """Execute a registered tool and return results"""
        if tool_name not in self.tools:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        
        try:
            tool_func = self.tools[tool_name]['function']
            # Check if async
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**params)
            else:
                # Run sync function in thread pool
                result = await asyncio.to_thread(tool_func, **params)
            return result if isinstance(result, dict) else {"success": True, "output": str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _is_simple_query(self, query: str) -> bool:
        """Check if query is simple and can use quick response with tools"""
        action_keywords = [
            'ping', 'status', 'cek', 'check', 'scan', 'info',
            'traceroute', 'dns', 'lookup', 'koneksi', 'connection',
            'jaringan', 'network', 'port', 'provider', 'internet'
        ]
        query_lower = query.lower()
        
        # Use quick mode for action-oriented queries
        for kw in action_keywords:
            if kw in query_lower:
                return True
        return False
    
    async def process(self, query: str) -> CycleContext:
        """
        Process a query through the full ODRVA cycle
        
        Args:
            query: User query or task
            
        Returns:
            CycleContext with all phase results
        """
        ctx = CycleContext(query=query)
        start_time = datetime.now()
        
        try:
            # === PHASE 1: OBSERVE ===
            self.current_phase = CyclePhase.OBSERVE
            await self._notify_progress(CyclePhase.OBSERVE, "starting")
            phase_start = datetime.now()
            ctx = await self._observe(ctx)
            ctx.phase_times["observe"] = (datetime.now() - phase_start).total_seconds()
            
            # === PHASE 2: REASON ===
            self.current_phase = CyclePhase.REASON
            await self._notify_progress(CyclePhase.REASON, "starting")
            phase_start = datetime.now()
            ctx = await self._reason(ctx)
            ctx.phase_times["reason"] = (datetime.now() - phase_start).total_seconds()
            
            # === PHASE 3: DECIDE ===
            self.current_phase = CyclePhase.DECIDE
            await self._notify_progress(CyclePhase.DECIDE, "starting")
            phase_start = datetime.now()
            ctx = await self._decide(ctx)
            ctx.phase_times["decide"] = (datetime.now() - phase_start).total_seconds()
            
            # Check if action should be blocked
            if ctx.blocked:
                self.history.append(ctx)
                return ctx
            
            # === PHASE 4: ACT ===
            self.current_phase = CyclePhase.ACT
            await self._notify_progress(CyclePhase.ACT, "starting")
            phase_start = datetime.now()
            ctx = await self._act(ctx)
            ctx.phase_times["act"] = (datetime.now() - phase_start).total_seconds()
            
            # === PHASE 5: VERIFY ===
            self.current_phase = CyclePhase.VERIFY
            await self._notify_progress(CyclePhase.VERIFY, "starting")
            phase_start = datetime.now()
            ctx = await self._verify(ctx)
            ctx.phase_times["verify"] = (datetime.now() - phase_start).total_seconds()
            
        except Exception as e:
            ctx.error = str(e)
            ctx.action_result = f"❌ Error during {self.current_phase.value}: {e}"
        
        self.history.append(ctx)
        return ctx
    
    async def _observe(self, ctx: CycleContext) -> CycleContext:
        """
        OBSERVE phase: Gather context and data
        """
        observe_prompt = f"""## PHASE: OBSERVE (Pengumpulan Data)

Query pengguna: {ctx.query}

Tugas:
1. Identifikasi intent dari query ini
2. Tentukan informasi apa yang dibutuhkan
3. List data yang perlu dikumpulkan

Format respons (singkat dan padat):
- Intent: [intent]
- Informasi yang dibutuhkan: [list]
- Data points yang dikumpulkan: [list]
"""
        
        timeout = self.PHASE_TIMEOUTS[CyclePhase.OBSERVE]
        response = await self.llm.chat_async(
            [{"role": "user", "content": observe_prompt}],
            timeout=timeout
        )
        ctx.observations.append(response['message']['content'])
        
        return ctx
    
    async def _reason(self, ctx: CycleContext) -> CycleContext:
        """
        REASON phase: Analyze and think through options
        """
        reason_prompt = f"""## PHASE: REASON (Analisis)

Query: {ctx.query}

Observasi:
{chr(10).join(ctx.observations)}

Tugas:
1. Analisis situasi berdasarkan observasi
2. Identifikasi opsi yang tersedia
3. Evaluasi dampak setiap opsi terhadap: Availability, Security, Performance
4. Identifikasi dependencies dan blast radius

Format respons sebagai analisis terstruktur yang singkat.
"""
        
        timeout = self.PHASE_TIMEOUTS[CyclePhase.REASON]
        response = await self.llm.chat_async(
            [{"role": "user", "content": reason_prompt}],
            timeout=timeout
        )
        ctx.reasoning = response['message']['content']
        
        return ctx
    
    async def _decide(self, ctx: CycleContext) -> CycleContext:
        """
        DECIDE phase: Make transparent decision
        """
        decide_prompt = f"""## PHASE: DECIDE (Keputusan)

Query: {ctx.query}

Observasi:
{chr(10).join(ctx.observations)}

Analisis:
{ctx.reasoning}

{self.transparency.format_for_llm()}

Tugas:
1. Pilih tindakan terbaik
2. Berikan output dalam format JSON yang diminta
3. Jika risiko tinggi dan data tidak cukup, set risk_level ke "high" atau "critical"
"""
        
        timeout = self.PHASE_TIMEOUTS[CyclePhase.DECIDE]
        response = await self.llm.chat_async(
            [{"role": "user", "content": decide_prompt}],
            timeout=timeout
        )
        content = response['message']['content']
        
        # Try to parse decision JSON
        try:
            # Extract JSON from response
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                decision_data = json.loads(content[json_start:json_end])
                
                record = self.transparency.create_record(
                    decision=decision_data.get('decision', ''),
                    technical_reasoning=decision_data.get('technical_reasoning', ''),
                    assumptions=decision_data.get('assumptions', []),
                    risks_and_tradeoffs=decision_data.get('risks_and_tradeoffs', []),
                    consequences_if_not_done=decision_data.get('consequences_if_not_done', ''),
                    conservative_alternatives=decision_data.get('conservative_alternatives', []),
                    risk_level=decision_data.get('risk_level', 'low')
                )
                ctx.decision = record
                
                # Check if action should be blocked
                if self.transparency.should_block_action(record.risk_level):
                    ctx.blocked = True
                    ctx.block_reason = f"⛔ Aksi diblokir karena risk level: {record.risk_level}. Diperlukan validasi manual."
                    record.action_blocked = True
        except json.JSONDecodeError:
            # If JSON parsing fails, create a basic record
            ctx.decision = self.transparency.create_record(
                decision=content,
                technical_reasoning="Could not parse structured decision",
                risk_level="medium"
            )
        
        return ctx
    
    async def _act(self, ctx: CycleContext) -> CycleContext:
        """
        ACT phase: Execute the decided action
        """
        if ctx.blocked:
            ctx.action_result = ctx.block_reason
            return ctx
        
        act_prompt = f"""## PHASE: ACT (Eksekusi)

Keputusan: {ctx.decision.decision if ctx.decision else 'No decision'}

Alasan: {ctx.decision.technical_reasoning if ctx.decision else 'N/A'}

Berikan langkah-langkah eksekusi yang detail dan singkat.
Jika ada perintah yang perlu dijalankan, format sebagai code block.

PENTING: Jangan eksekusi perintah destruktif. Hanya berikan rekomendasi.
"""
        
        timeout = self.PHASE_TIMEOUTS[CyclePhase.ACT]
        response = await self.llm.chat_async(
            [{"role": "user", "content": act_prompt}],
            timeout=timeout
        )
        ctx.action_result = response['message']['content']
        
        return ctx
    
    async def _verify(self, ctx: CycleContext) -> CycleContext:
        """
        VERIFY phase: Validate results
        """
        verify_prompt = f"""## PHASE: VERIFY (Validasi)

Aksi yang dilakukan:
{ctx.action_result}

Tugas:
1. Evaluasi apakah aksi berhasil
2. Identifikasi masalah potensial
3. Rekomendasikan tindak lanjut jika diperlukan
4. Berikan status: SUCCESS / PARTIAL / FAILED / BLOCKED

Format respons (singkat):
- Status: [status]
- Evaluasi: [evaluasi]
- Tindak lanjut: [rekomendasi]
"""
        
        timeout = self.PHASE_TIMEOUTS[CyclePhase.VERIFY]
        response = await self.llm.chat_async(
            [{"role": "user", "content": verify_prompt}],
            timeout=timeout
        )
        ctx.verification = response['message']['content']
        
        return ctx
    
    def format_response(self, ctx: CycleContext) -> str:
        """Format the full cycle response for display"""
        sections = []
        
        # Header
        sections.append("# Network Infrastructure Agent Response\n")
        
        # Show timing if available
        if ctx.phase_times:
            total_time = sum(ctx.phase_times.values())
            sections.append(f"*Completed in {total_time:.1f}s*\n")
        
        # Error check
        if ctx.error:
            sections.append(f"\n## ❌ Error\n{ctx.error}")
            return "\n".join(sections)
        
        # Observations
        sections.append("## OBSERVE\n")
        for obs in ctx.observations:
            sections.append(obs)
        
        # Reasoning
        sections.append("\n## REASON\n")
        sections.append(ctx.reasoning)
        
        # Decision
        sections.append("\n## DECIDE\n")
        if ctx.decision:
            sections.append(ctx.decision.to_markdown())
        
        # Blocked check
        if ctx.blocked:
            sections.append(f"\n## ACTION BLOCKED\n{ctx.block_reason}")
        else:
            # Action
            sections.append("\n## ACT\n")
            sections.append(ctx.action_result)
            
            # Verification
            sections.append("\n## VERIFY\n")
            sections.append(ctx.verification)
        
        return "\n".join(sections)


# Create singleton agent instance
agent = NetworkAgent()
