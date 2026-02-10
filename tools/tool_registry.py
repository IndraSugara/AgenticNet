"""
Tool Registry

Dynamic tool registration and discovery with:
- Tool metadata for LLM understanding
- Automatic tool discovery
- Capability matching
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Callable, Optional


@dataclass
class ToolParameter:
    """Definition of a tool parameter"""
    name: str
    description: str
    type: str = "string"
    required: bool = True
    default: Any = None


@dataclass
class ToolDefinition:
    """Complete definition of a tool"""
    name: str
    description: str
    function: Callable
    parameters: List[ToolParameter] = field(default_factory=list)
    returns: str = ""
    category: str = "general"
    risk_level: str = "low"  # low, medium, high
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "description": p.description,
                    "type": p.type,
                    "required": p.required
                }
                for p in self.parameters
            ],
            "returns": self.returns,
            "category": self.category,
            "risk_level": self.risk_level
        }
    
    def to_schema(self) -> str:
        """Generate schema string for LLM"""
        params_str = ", ".join([
            f"{p.name}: {p.description}" + (" (required)" if p.required else "")
            for p in self.parameters
        ])
        return f"- {self.name}: {self.description}\n  params: {{{params_str}}}\n  returns: {self.returns}"


class ToolRegistry:
    """
    Central registry for all available tools
    
    Provides:
    - Tool registration and discovery
    - Metadata for LLM tool selection
    - Category-based filtering
    - Capability matching
    """
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self.categories: Dict[str, List[str]] = {}
    
    def register(self, tool: ToolDefinition):
        """Register a new tool"""
        self.tools[tool.name] = tool
        
        # Add to category
        if tool.category not in self.categories:
            self.categories[tool.category] = []
        if tool.name not in self.categories[tool.category]:
            self.categories[tool.category].append(tool.name)
    
    def unregister(self, name: str):
        """Remove a tool from registry"""
        if name in self.tools:
            tool = self.tools.pop(name)
            if tool.category in self.categories:
                self.categories[tool.category].remove(name)
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name"""
        return self.tools.get(name)
    
    def list_all(self) -> List[ToolDefinition]:
        """List all registered tools"""
        return list(self.tools.values())
    
    def list_by_category(self, category: str) -> List[ToolDefinition]:
        """List tools in a category"""
        names = self.categories.get(category, [])
        return [self.tools[n] for n in names if n in self.tools]
    
    def find_tools(self, capability: str) -> List[ToolDefinition]:
        """Find tools matching a capability description"""
        capability_lower = capability.lower()
        matched = []
        
        for tool in self.tools.values():
            # Simple keyword matching
            if (capability_lower in tool.name.lower() or 
                capability_lower in tool.description.lower()):
                matched.append(tool)
        
        return matched
    
    def get_schema_for_llm(self) -> str:
        """Generate complete schema for LLM"""
        lines = ["## Available Tools\n"]
        
        for category in sorted(self.categories.keys()):
            lines.append(f"### {category.title()}\n")
            for name in self.categories[category]:
                tool = self.tools.get(name)
                if tool:
                    lines.append(tool.to_schema())
            lines.append("")
        
        return "\n".join(lines)
    
    def get_tool_names(self) -> List[str]:
        """Get list of all tool names"""
        return list(self.tools.keys())
    
    def execute(self, name: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a tool by name.
        
        Args:
            name: Tool name
            params: Parameters to pass
            
        Returns:
            Execution result dict with success, output, error
        """
        tool = self.get(name)
        if not tool:
            return {"success": False, "output": "", "error": f"Tool '{name}' not found"}
        
        params = params or {}
        
        try:
            # Filter to valid params with defaults
            valid_params = {}
            for param in tool.parameters:
                if param.name in params:
                    valid_params[param.name] = params[param.name]
                elif not param.required and param.default is not None:
                    valid_params[param.name] = param.default
            
            result = tool.function(**valid_params)
            
            # Normalize result
            if isinstance(result, dict):
                return result
            elif hasattr(result, 'success'):  # ToolResult
                return {
                    "success": result.success,
                    "output": result.output,
                    "error": result.error
                }
            else:
                return {"success": True, "output": str(result), "error": ""}
                
        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}
    
    def get_langchain_tools(self):
        """
        Generate LangChain tool objects for all registered tools.
        
        Returns:
            List of LangChain StructuredTool objects
        """
        from langchain_core.tools import StructuredTool
        from functools import wraps
        
        langchain_tools = []
        
        for tool_def in self.tools.values():
            # Create wrapper that normalizes output
            def make_wrapper(fn):
                @wraps(fn)
                def wrapper(**kwargs):
                    result = fn(**kwargs)
                    if hasattr(result, 'success'):  # ToolResult
                        return result.output if result.success else f"Error: {result.error}"
                    elif isinstance(result, dict):
                        if result.get('success', True):
                            return result.get('output', str(result))
                        return f"Error: {result.get('error', 'Unknown error')}"
                    return str(result)
                return wrapper
            
            lc_tool = StructuredTool.from_function(
                func=make_wrapper(tool_def.function),
                name=tool_def.name,
                description=tool_def.description
            )
            langchain_tools.append(lc_tool)
        
        return langchain_tools


# Singleton registry
registry = ToolRegistry()


def register_network_tools():
    """Register all network tools"""
    from tools.network_tools import network_tools
    
    # Ping
    registry.register(ToolDefinition(
        name="ping",
        description="Check network connectivity to a host",
        function=network_tools.ping,
        parameters=[
            ToolParameter("host", "Target IP address or hostname"),
            ToolParameter("count", "Number of ping packets", "int", False, 4)
        ],
        returns="Connectivity status with latency information",
        category="connectivity"
    ))
    
    # Traceroute
    registry.register(ToolDefinition(
        name="traceroute",
        description="Trace the network path to a host",
        function=network_tools.traceroute,
        parameters=[
            ToolParameter("host", "Target IP address or hostname")
        ],
        returns="Network path with hop information",
        category="connectivity"
    ))
    
    # DNS Lookup
    registry.register(ToolDefinition(
        name="dns_lookup",
        description="Perform DNS lookup for a hostname",
        function=network_tools.dns_lookup,
        parameters=[
            ToolParameter("hostname", "Domain name to resolve")
        ],
        returns="IP addresses associated with the hostname",
        category="dns"
    ))
    
    # Port Scan
    registry.register(ToolDefinition(
        name="port_scan",
        description="Scan common ports on a host",
        function=network_tools.port_scan,
        parameters=[
            ToolParameter("host", "Target IP address or hostname"),
            ToolParameter("ports", "List of ports to scan", "list", False, None)
        ],
        returns="Open and closed port status",
        category="security",
        risk_level="medium"
    ))
    
    # Check Port
    registry.register(ToolDefinition(
        name="check_port",
        description="Check if a specific port is open",
        function=network_tools.check_port,
        parameters=[
            ToolParameter("host", "Target IP address or hostname"),
            ToolParameter("port", "Port number to check", "int")
        ],
        returns="Port open/closed status",
        category="connectivity"
    ))
    
    # Network Info
    registry.register(ToolDefinition(
        name="get_network_info",
        description="Get local network configuration",
        function=network_tools.get_network_info,
        parameters=[],
        returns="Local IP, hostname, and network configuration",
        category="info"
    ))
    
    # NSLookup
    registry.register(ToolDefinition(
        name="nslookup",
        description="Query DNS server for domain information",
        function=network_tools.nslookup,
        parameters=[
            ToolParameter("domain", "Domain to query")
        ],
        returns="DNS query results",
        category="dns"
    ))
    
    # Get Interfaces
    registry.register(ToolDefinition(
        name="get_interfaces",
        description="List all network interfaces with status",
        function=network_tools.get_interfaces,
        parameters=[],
        returns="Network interface list with IP addresses and statistics",
        category="info"
    ))
    
    # Get Connections
    registry.register(ToolDefinition(
        name="get_connections",
        description="List active network connections",
        function=network_tools.get_connections,
        parameters=[],
        returns="Active TCP/UDP connections",
        category="monitoring"
    ))
    
    # Measure Latency
    registry.register(ToolDefinition(
        name="measure_latency",
        description="Measure latency to multiple hosts",
        function=network_tools.measure_latency,
        parameters=[
            ToolParameter("hosts", "List of hosts to measure", "list", False, None)
        ],
        returns="Latency measurements in milliseconds",
        category="monitoring"
    ))
    
    # Bandwidth Stats
    registry.register(ToolDefinition(
        name="get_bandwidth_stats",
        description="Get current bandwidth usage statistics",
        function=network_tools.get_bandwidth_stats,
        parameters=[],
        returns="Upload/download rates and total bytes",
        category="monitoring"
    ))
    
    # Provider/ISP Info
    registry.register(ToolDefinition(
        name="get_provider_info",
        description="Get ISP/provider information including public IP, ISP name, location",
        function=network_tools.get_provider_info,
        parameters=[],
        returns="ISP name, public IP, AS number, country, city, timezone",
        category="info"
    ))


# Auto-register tools on import
register_network_tools()

