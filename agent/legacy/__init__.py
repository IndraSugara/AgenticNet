"""
Legacy Agent Components

These files are kept for backward compatibility with existing code
that may still reference them. New code should use:

- agent.langgraph_agent.network_agent (main agent)
- agent.langchain_llm.get_llm() (LLM client)
- agent.langchain_tools.get_all_tools() (tools)

The legacy ODRVA cycle (Observe-Reason-Decide-Act-Verify) has been
replaced with LangGraph's StateGraph workflow.
"""

# Re-export legacy components for backward compatibility
from agent.legacy.core import agent, NetworkAgent, CyclePhase, CycleContext
from agent.legacy.llm_client import llm_client, LLMClient
from agent.memory import memory, WorkflowMemory
from agent.legacy.transparency import transparency, TransparencyModule
