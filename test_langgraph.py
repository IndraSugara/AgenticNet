"""Test LangGraph agent"""
import sys
import traceback

try:
    print("Testing imports...")
    
    print("1. Testing langchain_llm...")
    from agent.langchain_llm import get_llm
    print("   OK")
    
    print("2. Testing langchain_tools...")
    from agent.langchain_tools import get_all_tools
    tools = get_all_tools()
    print(f"   OK - {len(tools)} tools loaded")
    
    print("3. Testing langgraph_agent...")
    from agent.langgraph_agent import network_agent
    print("   OK")
    
    print("")
    print("SUCCESS: All imports OK!")
    
except Exception as e:
    print(f"")
    print(f"ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
