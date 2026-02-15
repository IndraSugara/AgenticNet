"""
Configuration for Agentic AI Network Infrastructure Operator
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration"""
    
    # Ollama Settings
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "DEFAULT_MODEL")
    
    # Available LLM Models
    AVAILABLE_MODELS = {
        "gpt-oss:20b": {
            "name": "GPT OSS 20B",
            "model_id": "gpt-oss:20b",
            "description": "Larger model, better quality responses"
        },
        "glm-4.7-flash:latest": {
            "name": "GLM 4.7 Flash",
            "model_id": "glm-4.7-flash:latest",
            "description": "Faster responses, lower resource usage"
        },
        "kimi-k2-thinking:cloud": {
            "name": "Kimi K2 Thinking",
            "model_id": "kimi-k2-thinking:cloud",
            "description": "Cloud-based thinking model with advanced reasoning"
        },
        "kimi-k2.5:cloud": {
            "name": "Kimi K2.5",
            "model_id": "kimi-k2.5:cloud",
            "description": "Cloud-based thinking model with advanced reasoning"
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
