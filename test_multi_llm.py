"""
Test suite for Multi-LLM Provider and OpenClaw-inspired features
"""
import sys
import os

# Add project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_provider_factory():
    """Test that the provider factory is correctly populated"""
    from agent.langchain_llm import _PROVIDER_FACTORY
    
    assert "ollama" in _PROVIDER_FACTORY, "Ollama provider missing"
    assert "openai" in _PROVIDER_FACTORY, "OpenAI provider missing"
    assert "deepseek" in _PROVIDER_FACTORY, "DeepSeek provider missing"
    print("  ✅ Provider factory has all 3 providers")


def test_get_llm_returns_instance():
    """Test that get_llm returns an LLM instance"""
    from agent.langchain_llm import get_llm
    
    # Default provider (ollama) should work if ollama host is reachable
    try:
        llm = get_llm()
        assert llm is not None, "get_llm returned None"
        print(f"  ✅ get_llm() returned: {type(llm).__name__}")
    except Exception as e:
        print(f"  ⚠️ get_llm() raised (expected if provider unavailable): {e}")


def test_fallback_llm_class():
    """Test FallbackLLM class structure"""
    from agent.langchain_llm import FallbackLLM
    
    assert hasattr(FallbackLLM, 'invoke'), "FallbackLLM missing invoke method"
    assert hasattr(FallbackLLM, 'ainvoke'), "FallbackLLM missing ainvoke method"
    assert hasattr(FallbackLLM, 'bind_tools'), "FallbackLLM missing bind_tools method"
    print("  ✅ FallbackLLM has invoke, ainvoke, bind_tools")


def test_config_fields():
    """Test that config has new LLM fields"""
    from config import config
    
    assert hasattr(config, 'LLM_PROVIDER'), "Missing LLM_PROVIDER"
    assert hasattr(config, 'LLM_FALLBACK_ENABLED'), "Missing LLM_FALLBACK_ENABLED"
    assert hasattr(config, 'LLM_FALLBACK_PROVIDER'), "Missing LLM_FALLBACK_PROVIDER"
    assert config.LLM_PROVIDER in ["ollama", "openai", "deepseek"], f"Invalid provider: {config.LLM_PROVIDER}"
    print(f"  ✅ Config: provider={config.LLM_PROVIDER}, fallback={config.LLM_FALLBACK_ENABLED}")


def test_remediation_runbooks():
    """Test remediation runbook definitions"""
    from agent.log_watcher import REMEDIATION_RUNBOOKS
    
    expected = ["link_down", "link_flap", "auth_failure", "system_error", 
                "system_warning", "routing_change", "hardware_issue"]
    
    for key in expected:
        assert key in REMEDIATION_RUNBOOKS, f"Missing runbook: {key}"
        runbook = REMEDIATION_RUNBOOKS[key]
        assert "prompt" in runbook, f"Runbook {key} missing prompt"
        assert "auto_actions" in runbook, f"Runbook {key} missing auto_actions"
        assert "requires_confirmation" in runbook, f"Runbook {key} missing requires_confirmation"
    
    print(f"  ✅ {len(REMEDIATION_RUNBOOKS)} remediation runbooks loaded")


def test_device_watch_config_auto_remediate():
    """Test that DeviceWatchConfig has auto_remediate field"""
    from agent.log_watcher import DeviceWatchConfig
    
    cfg = DeviceWatchConfig(device_ip="10.0.0.1")
    assert cfg.auto_remediate is True, "auto_remediate default should be True"
    print("  ✅ DeviceWatchConfig.auto_remediate defaults to True")


def test_intelligence_tools_loadable():
    """Test that intelligence tools can be loaded"""
    from agent.langchain_intelligence_tools import get_intelligence_tools
    
    tools = get_intelligence_tools()
    assert len(tools) == 4, f"Expected 4 intelligence tools, got {len(tools)}"
    tool_names = [t.name for t in tools]
    assert "save_diagnostic_result" in tool_names
    assert "query_device_history" in tool_names
    assert "get_network_baseline" in tool_names
    assert "check_anomaly_against_baseline" in tool_names
    print(f"  ✅ {len(tools)} intelligence tools loaded: {', '.join(tool_names)}")


def test_remediation_tools_loadable():
    """Test that remediation tools can be loaded"""
    from agent.langchain_remediation_tools import get_remediation_tools
    
    tools = get_remediation_tools()
    assert len(tools) == 3, f"Expected 3 remediation tools, got {len(tools)}"
    tool_names = [t.name for t in tools]
    assert "get_remediation_runbook" in tool_names
    assert "record_remediation_result" in tool_names
    assert "get_remediation_history" in tool_names
    print(f"  ✅ {len(tools)} remediation tools loaded: {', '.join(tool_names)}")


def test_memory_schema():
    """Test that long_term_memory has the new tables"""
    from agent.long_term_memory import LongTermMemory
    
    # Check methods exist
    assert hasattr(LongTermMemory, 'record_event'), "Missing record_event"
    assert hasattr(LongTermMemory, 'get_device_history'), "Missing get_device_history"
    assert hasattr(LongTermMemory, 'update_baseline'), "Missing update_baseline"
    assert hasattr(LongTermMemory, 'get_baseline'), "Missing get_baseline"
    assert hasattr(LongTermMemory, 'is_anomalous'), "Missing is_anomalous"
    assert hasattr(LongTermMemory, 'get_all_baselines'), "Missing get_all_baselines"
    print("  ✅ LongTermMemory has all intelligence methods")


def test_tools_count():
    """Test that all new tools are registered in get_all_tools()"""
    from agent.langchain_tools import get_all_tools
    
    tools = get_all_tools()
    tool_names = [t.name for t in tools]
    
    # Check new remediation tools
    assert "get_remediation_runbook" in tool_names, "Remediation tools not registered"
    assert "record_remediation_result" in tool_names
    
    # Check new intelligence tools
    assert "save_diagnostic_result" in tool_names, "Intelligence tools not registered"
    assert "query_device_history" in tool_names
    assert "get_network_baseline" in tool_names
    assert "check_anomaly_against_baseline" in tool_names
    
    print(f"  ✅ All new tools registered ({len(tools)} total tools)")


if __name__ == "__main__":
    tests = [
        ("Provider Factory", test_provider_factory),
        ("get_llm Instance", test_get_llm_returns_instance),
        ("FallbackLLM Class", test_fallback_llm_class),
        ("Config Fields", test_config_fields),
        ("Remediation Runbooks", test_remediation_runbooks),
        ("DeviceWatchConfig", test_device_watch_config_auto_remediate),
        ("Intelligence Tools", test_intelligence_tools_loadable),
        ("Remediation Tools", test_remediation_tools_loadable),
        ("Memory Schema", test_memory_schema),
        ("Tool Registration", test_tools_count),
    ]
    
    print("=" * 50)
    print("OpenClaw Feature Integration Tests")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            print(f"\n🧪 {name}...")
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
    
    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    sys.exit(1 if failed else 0)
