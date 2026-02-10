"""
Workflow Planner

Autonomous task planning with:
- Goal decomposition into actionable steps
- Tool selection based on requirements
- Dynamic re-planning on failures
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import re

from agent.llm_client import llm_client
from agent.workflow import Workflow, WorkflowStep


@dataclass
class PlanStep:
    """A planned step before workflow creation"""
    name: str
    description: str
    tool: str
    params: Dict[str, Any]
    depends_on: List[str] = None


class WorkflowPlanner:
    """
    Autonomous Workflow Planner
    
    Uses LLM to:
    - Decompose goals into actionable steps
    - Select appropriate tools
    - Build dependency graphs
    - Re-plan on failures
    """
    
    PLANNING_PROMPT = """Kamu adalah Network Infrastructure Planner. Tugasmu adalah membuat rencana eksekusi untuk goal berikut.

## Goal
{goal}

## Tools yang Tersedia
{tools_schema}

## Instruksi
1. Analisis goal dan tentukan langkah-langkah yang diperlukan
2. Pilih tools yang sesuai untuk setiap langkah
3. Tentukan dependencies antar langkah jika ada
4. Berikan output dalam format JSON

## Format Output (HARUS JSON VALID)
{{
  "analysis": "analisis singkat dari goal",
  "steps": [
    {{
      "name": "nama langkah",
      "description": "deskripsi singkat",
      "tool": "nama_tool",
      "params": {{"param1": "value1"}},
      "depends_on": []
    }}
  ]
}}

PENTING:
- Gunakan HANYA tools yang tersedia
- Params harus sesuai dengan yang dibutuhkan tool
- depends_on berisi list nama langkah yang harus selesai dulu
- Buat langkah-langkah yang efisien dan to-the-point
"""

    TOOLS_SCHEMA = """
- ping: Cek konektivitas ke host
  params: {host: "IP atau hostname", count: 4}
  
- dns_lookup: Lookup DNS untuk domain
  params: {hostname: "domain"}
  
- port_scan: Scan port pada host
  params: {host: "IP atau hostname", ports: [list port] atau null untuk default}
  
- check_port: Cek port spesifik
  params: {host: "IP", port: nomor_port}
  
- traceroute: Trace route ke host
  params: {host: "IP atau hostname"}
  
- get_network_info: Info jaringan lokal
  params: {}
  
- get_provider_info: Info ISP/provider (IP publik, nama ISP, lokasi, AS number)
  params: {}
  
- nslookup: Query DNS
  params: {domain: "domain"}
  
- get_interfaces: List network interfaces
  params: {}
  
- get_connections: List koneksi aktif
  params: {}
  
- measure_latency: Ukur latency ke beberapa host
  params: {hosts: [list host] atau null untuk default}
  
- get_bandwidth_stats: Statistik bandwidth
  params: {}
"""

    def __init__(self, llm=None):
        self.llm = llm or llm_client
    
    async def plan(self, goal: str, context: Dict[str, Any] = None) -> Workflow:
        """
        Create a workflow plan from a goal
        
        Args:
            goal: The goal to achieve
            context: Additional context for planning
            
        Returns:
            Workflow with planned steps
        """
        # Create planning prompt
        prompt = self.PLANNING_PROMPT.format(
            goal=goal,
            tools_schema=self.TOOLS_SCHEMA
        )
        
        # Get LLM response
        response = await self.llm.chat_async(
            [{"role": "user", "content": prompt}],
            timeout=600
        )
        
        content = response.get("message", {}).get("content", "")
        
        # Parse the plan
        plan_data = self._parse_plan(content)
        
        # Create workflow
        workflow = Workflow(goal=goal)
        
        # Add steps to workflow
        step_name_to_id = {}
        for i, step_data in enumerate(plan_data.get("steps", [])):
            # Resolve depends_on from names to IDs
            depends_on = []
            for dep_name in step_data.get("depends_on", []):
                if dep_name in step_name_to_id:
                    depends_on.append(step_name_to_id[dep_name])
            
            step_id = workflow.add_step(
                name=step_data.get("name", f"Step {i+1}"),
                tool=step_data.get("tool", ""),
                params=step_data.get("params", {}),
                description=step_data.get("description", ""),
                depends_on=depends_on
            )
            step_name_to_id[step_data.get("name", f"Step {i+1}")] = step_id
        
        return workflow
    
    def _parse_plan(self, content: str) -> Dict[str, Any]:
        """Parse LLM response to extract plan JSON"""
        try:
            # Try to find JSON in response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        # Fallback: create a simple plan
        return {
            "analysis": "Could not parse LLM response",
            "steps": [
                {
                    "name": "Network Info",
                    "description": "Get local network information",
                    "tool": "get_network_info",
                    "params": {},
                    "depends_on": []
                }
            ]
        }
    
    async def replan(
        self, 
        workflow: Workflow, 
        failed_step: WorkflowStep,
        error: str
    ) -> Optional[List[PlanStep]]:
        """
        Re-plan after a step failure
        
        Args:
            workflow: The current workflow
            failed_step: The step that failed
            error: The error message
            
        Returns:
            List of replacement steps, or None if cannot recover
        """
        replan_prompt = f"""Step "{failed_step.name}" gagal dengan error: {error}

Original workflow goal: {workflow.goal}
Failed step tool: {failed_step.tool}
Failed step params: {json.dumps(failed_step.params)}

Berikan alternatif langkah untuk mencapai tujuan yang sama.
Format JSON:
{{
  "can_recover": true/false,
  "alternative_steps": [
    {{"name": "...", "tool": "...", "params": {{...}}}}
  ],
  "explanation": "..."
}}
"""
        
        response = await self.llm.chat_async(
            [{"role": "user", "content": replan_prompt}],
            timeout=600
        )
        
        content = response.get("message", {}).get("content", "")
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                data = json.loads(json_match.group())
                if data.get("can_recover") and data.get("alternative_steps"):
                    return [
                        PlanStep(
                            name=s.get("name", ""),
                            description=s.get("description", ""),
                            tool=s.get("tool", ""),
                            params=s.get("params", {})
                        )
                        for s in data["alternative_steps"]
                    ]
        except:
            pass
        
        return None


# Singleton planner
planner = WorkflowPlanner()
