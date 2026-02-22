"""
Configuration for Agentic AI Network Infrastructure Operator
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration"""
    
    # ============= LLM Provider Settings =============
    # Primary provider: "ollama" | "openai" | "deepseek"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    
    # Ollama Settings
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "DEFAULT_MODEL")
    
    # OpenAI Settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")  # Custom endpoint
    
    # DeepSeek Settings
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    
    # Fallback Settings
    LLM_FALLBACK_ENABLED: bool = os.getenv("LLM_FALLBACK_ENABLED", "true").lower() == "true"
    LLM_FALLBACK_PROVIDER: str = os.getenv("LLM_FALLBACK_PROVIDER", "ollama")
    
    # Available LLM Models (for UI model selector)
    AVAILABLE_MODELS = {
        "gpt-oss:20b": {
            "name": "GPT OSS 20B",
            "model_id": "gpt-oss:20b",
            "provider": "ollama",
            "description": "Larger model, better quality responses"
        },
        "glm-4.7-flash:latest": {
            "name": "GLM 4.7 Flash",
            "model_id": "glm-4.7-flash:latest",
            "provider": "ollama",
            "description": "Faster responses, lower resource usage"
        },
        "kimi-k2-thinking:cloud": {
            "name": "Kimi K2 Thinking",
            "model_id": "kimi-k2-thinking:cloud",
            "provider": "ollama",
            "description": "Cloud-based thinking model with advanced reasoning"
        },
        "kimi-k2.5:cloud": {
            "name": "Kimi K2.5",
            "model_id": "kimi-k2.5:cloud",
            "provider": "ollama",
            "description": "Cloud-based thinking model with advanced reasoning"
        },
        "gpt-4o-mini": {
            "name": "GPT-4o Mini",
            "model_id": "gpt-4o-mini",
            "provider": "openai",
            "description": "OpenAI GPT-4o Mini — fast and affordable"
        },
        "deepseek-chat": {
            "name": "DeepSeek Chat",
            "model_id": "deepseek-chat",
            "provider": "deepseek",
            "description": "DeepSeek V3 — strong reasoning, low cost"
        }
    }
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-oss:20b")
    
    # Server Settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Agent Settings
    MAX_REASONING_STEPS: int = 10
    RISK_THRESHOLD: float = 0.7  # Block actions above this risk level


config = Config()
