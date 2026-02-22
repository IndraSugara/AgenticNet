"""
LangChain LLM Client — Multi-Provider Support

Supports multiple LLM providers with automatic fallback:
- Ollama (local/remote via ngrok)
- OpenAI (GPT-4o, GPT-4o-mini, etc.)
- DeepSeek (via OpenAI-compatible API)

Inspired by OpenClaw's multi-provider architecture.
"""
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from config import config
from agent.logging_config import get_logger

logger = get_logger("langchain_llm")


# ============= PROVIDER FACTORY =============

def _create_ollama_llm(model: str = None, base_url: str = None,
                       temperature: float = 0.7, timeout: int = 45) -> BaseChatModel:
    """Create ChatOllama instance"""
    return ChatOllama(
        model=model or config.OLLAMA_MODEL,
        base_url=base_url or config.OLLAMA_HOST,
        temperature=temperature,
        timeout=timeout
    )


def _create_openai_llm(model: str = None, temperature: float = 0.7,
                        timeout: int = 45) -> BaseChatModel:
    """Create ChatOpenAI instance"""
    from langchain_openai import ChatOpenAI
    
    kwargs = {
        "model": model or config.OPENAI_MODEL,
        "api_key": config.OPENAI_API_KEY,
        "temperature": temperature,
        "timeout": timeout,
    }
    if config.OPENAI_BASE_URL:
        kwargs["base_url"] = config.OPENAI_BASE_URL
    
    return ChatOpenAI(**kwargs)


def _create_deepseek_llm(model: str = None, temperature: float = 0.7,
                          timeout: int = 45) -> BaseChatModel:
    """Create ChatOpenAI instance pointing to DeepSeek API"""
    from langchain_openai import ChatOpenAI
    
    return ChatOpenAI(
        model=model or config.DEEPSEEK_MODEL,
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        temperature=temperature,
        timeout=timeout,
    )


# Provider registry
_PROVIDER_FACTORY = {
    "ollama": _create_ollama_llm,
    "openai": _create_openai_llm,
    "deepseek": _create_deepseek_llm,
}


def get_llm(
    provider: str = None,
    model: str = None,
    temperature: float = 0.7,
    timeout: int = 45
) -> BaseChatModel:
    """
    Get LangChain LLM instance for specified provider
    
    Args:
        provider: LLM provider ("ollama", "openai", "deepseek"). Default: from config.
        model: Model name. Default: from provider-specific config.
        temperature: Sampling temperature
        timeout: Request timeout in seconds
    
    Returns:
        BaseChatModel instance
    """
    provider = provider or config.LLM_PROVIDER
    factory = _PROVIDER_FACTORY.get(provider)
    
    if not factory:
        logger.warning(f"Unknown provider '{provider}', falling back to ollama")
        factory = _PROVIDER_FACTORY["ollama"]
    
    # For ollama, pass base_url; for others, don't
    if provider == "ollama":
        return factory(model=model, temperature=temperature, timeout=timeout)
    else:
        return factory(model=model, temperature=temperature, timeout=timeout)


# ============= FALLBACK LLM WRAPPER =============

class FallbackLLM:
    """
    LLM wrapper with automatic fallback to secondary provider.
    
    If the primary provider fails (timeout, API error, quota exceeded),
    automatically retries with the fallback provider.
    
    Inspired by OpenClaw's multi-provider resilience pattern.
    """
    
    def __init__(self, primary: BaseChatModel, fallback: BaseChatModel,
                 primary_name: str = "primary", fallback_name: str = "fallback"):
        self.primary = primary
        self.fallback = fallback
        self.primary_name = primary_name
        self.fallback_name = fallback_name
        self._using_fallback = False
    
    @property
    def is_using_fallback(self) -> bool:
        return self._using_fallback
    
    def invoke(self, messages, **kwargs):
        """Invoke with automatic fallback"""
        try:
            result = self.primary.invoke(messages, **kwargs)
            self._using_fallback = False
            return result
        except Exception as e:
            logger.warning(
                f"⚠️ Primary LLM ({self.primary_name}) failed: {e}. "
                f"Switching to fallback ({self.fallback_name})..."
            )
            self._using_fallback = True
            return self.fallback.invoke(messages, **kwargs)
    
    async def ainvoke(self, messages, **kwargs):
        """Async invoke with automatic fallback"""
        try:
            result = await self.primary.ainvoke(messages, **kwargs)
            self._using_fallback = False
            return result
        except Exception as e:
            logger.warning(
                f"⚠️ Primary LLM ({self.primary_name}) failed: {e}. "
                f"Switching to fallback ({self.fallback_name})..."
            )
            self._using_fallback = True
            return await self.fallback.ainvoke(messages, **kwargs)
    
    def bind_tools(self, tools, **kwargs):
        """Bind tools to both primary and fallback, return new FallbackLLM"""
        try:
            primary_with_tools = self.primary.bind_tools(tools, **kwargs)
        except Exception:
            primary_with_tools = self.primary
        
        try:
            fallback_with_tools = self.fallback.bind_tools(tools, **kwargs)
        except Exception:
            fallback_with_tools = self.fallback
        
        return FallbackLLM(
            primary_with_tools, fallback_with_tools,
            self.primary_name, self.fallback_name
        )


def get_llm_with_fallback(
    model: str = None,
    temperature: float = 0.7,
    timeout: int = 45
) -> BaseChatModel:
    """
    Get LLM with automatic fallback enabled.
    
    If LLM_FALLBACK_ENABLED is True and fallback provider differs from primary,
    returns a FallbackLLM wrapper. Otherwise returns a plain LLM.
    
    Args:
        model: Optional model override for primary provider
        temperature: Sampling temperature
        timeout: Request timeout
    
    Returns:
        BaseChatModel (or FallbackLLM wrapper)
    """
    primary = get_llm(model=model, temperature=temperature, timeout=timeout)
    
    if (config.LLM_FALLBACK_ENABLED and 
        config.LLM_FALLBACK_PROVIDER != config.LLM_PROVIDER):
        try:
            fallback = get_llm(
                provider=config.LLM_FALLBACK_PROVIDER,
                temperature=temperature,
                timeout=timeout
            )
            logger.info(
                f"🔄 Multi-LLM: primary={config.LLM_PROVIDER}, "
                f"fallback={config.LLM_FALLBACK_PROVIDER}"
            )
            return FallbackLLM(
                primary, fallback,
                primary_name=config.LLM_PROVIDER,
                fallback_name=config.LLM_FALLBACK_PROVIDER
            )
        except Exception as e:
            logger.warning(f"Failed to create fallback LLM: {e}. Using primary only.")
    
    return primary


# ============= TOOL BINDING =============

def get_llm_with_tools(tools: list, **kwargs) -> BaseChatModel:
    """
    Get LLM with tools bound for function calling
    
    Args:
        tools: List of LangChain tools to bind
        **kwargs: Additional arguments for get_llm()
    
    Returns:
        LLM with tools bound
    """
    llm = get_llm_with_fallback(**kwargs)
    
    if isinstance(llm, FallbackLLM):
        return llm.bind_tools(tools)
    else:
        return llm.bind_tools(tools)


# ============= SINGLETON =============

_llm_instance = None

def get_default_llm() -> BaseChatModel:
    """Get or create default LLM instance (with fallback if configured)"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = get_llm_with_fallback()
    return _llm_instance


def reset_llm_instance():
    """Reset singleton (e.g., after config change)"""
    global _llm_instance
    _llm_instance = None
