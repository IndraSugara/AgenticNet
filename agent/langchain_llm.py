"""
LangChain LLM Client using Ollama

Provides ChatOllama wrapper for use with LangGraph agents.
"""
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from config import config


def get_llm(
    model: str = None,
    base_url: str = None,
    temperature: float = 0.7,
    timeout: int = 45  # Reduced from 120s for better UX
) -> BaseChatModel:
    """
    Get LangChain ChatOllama instance
    
    Args:
        model: Model name (default: from config)
        base_url: Ollama host URL (default: from config)
        temperature: Sampling temperature
        timeout: Request timeout in seconds
    
    Returns:
        ChatOllama instance
    """
    return ChatOllama(
        model=model or config.OLLAMA_MODEL,
        base_url=base_url or config.OLLAMA_HOST,
        temperature=temperature,
        timeout=timeout
    )


def get_llm_with_tools(tools: list, **kwargs) -> BaseChatModel:
    """
    Get LLM with tools bound for function calling
    
    Args:
        tools: List of LangChain tools to bind
        **kwargs: Additional arguments for get_llm()
    
    Returns:
        ChatOllama with tools bound
    """
    llm = get_llm(**kwargs)
    return llm.bind_tools(tools)


# Singleton LLM instance
_llm_instance = None

def get_default_llm() -> BaseChatModel:
    """Get or create default LLM instance"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = get_llm()
    return _llm_instance
