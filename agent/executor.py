"""
Workflow Executor

Step execution with:
- Tool invocation
- Result capture
- Error handling
- State management
"""
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
import asyncio

from tools.network_tools import network_tools


@dataclass
class ExecutionResult:
    """Result of tool execution"""
    success: bool
    output: Any
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error
        }


class WorkflowExecutor:
    """
    Executes workflow steps using registered tools
    
    Provides:
    - Tool lookup and invocation
    - Parameter validation
    - Error handling with retries
    - Result formatting
    """
    
    def __init__(self):
        self.tools = self._build_tool_map()
    
    def _build_tool_map(self) -> Dict[str, Callable]:
        """Build map of tool names to functions"""
        return {
            # Network diagnostic tools
            "ping": self._wrap_tool(network_tools.ping, ["host"], {"count": 4}),
            "traceroute": self._wrap_tool(network_tools.traceroute, ["host"]),
            "dns_lookup": self._wrap_tool(network_tools.dns_lookup, ["hostname"]),
            "check_port": self._wrap_tool(network_tools.check_port, ["host", "port"]),
            "port_scan": self._wrap_tool(network_tools.port_scan, ["host"], {"ports": None}),
            "get_network_info": self._wrap_tool(network_tools.get_network_info, []),
            "nslookup": self._wrap_tool(network_tools.nslookup, ["domain"]),
            
            # Advanced monitoring tools
            "get_interfaces": self._wrap_dict(network_tools.get_interfaces),
            "get_connections": self._wrap_dict(network_tools.get_connections),
            "measure_latency": self._wrap_dict(network_tools.measure_latency),
            "get_bandwidth_stats": self._wrap_dict(network_tools.get_bandwidth_stats),
            "get_provider_info": self._wrap_dict(network_tools.get_provider_info),
        }
    
    def _wrap_tool(
        self, 
        func: Callable, 
        required_params: list,
        defaults: dict = None
    ) -> Callable:
        """Wrap a ToolResult-returning function"""
        defaults = defaults or {}
        
        def wrapper(params: dict) -> dict:
            # Apply defaults
            full_params = {**defaults, **params}
            
            # Extract required params
            args = {}
            for p in required_params:
                if p in full_params:
                    args[p] = full_params[p]
            
            # Add optional params
            for k, v in full_params.items():
                if k not in args:
                    args[k] = v
            
            result = func(**args)
            return {
                "success": result.success,
                "output": result.output,
                "error": result.error
            }
        
        return wrapper
    
    def _wrap_dict(self, func: Callable) -> Callable:
        """Wrap a dict-returning function"""
        def wrapper(params: dict) -> dict:
            result = func(**params) if params else func()
            return result
        return wrapper
    
    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by name
        
        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool
            
        Returns:
            Execution result as dict
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "output": "",
                "error": f"Tool '{tool_name}' not found"
            }
        
        try:
            # Run in thread pool to avoid blocking
            result = await asyncio.to_thread(self.tools[tool_name], params)
            return result
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "error": str(e)
            }
    
    def get_available_tools(self) -> list:
        """Get list of available tool names"""
        return list(self.tools.keys())


# Singleton executor
executor = WorkflowExecutor()


async def execute_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience function to execute a tool"""
    return await executor.execute(tool_name, params)
