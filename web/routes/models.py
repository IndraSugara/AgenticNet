"""
Model Management Routes

Endpoints for listing and switching LLM models.
"""
from fastapi import APIRouter, Request

from config import config
from agent.llm_client import llm_client

router = APIRouter()


@router.get("/agent/models/list")
async def list_available_models():
    """Get list of available LLM models"""
    try:
        return {
            "success": True,
            "models": config.AVAILABLE_MODELS,
            "current": config.DEFAULT_MODEL
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/agent/model/switch")
async def switch_model(request: Request):
    """Switch the active LLM model"""
    try:
        data = await request.json()
        model_id = data.get("model_id")
        
        if not model_id or model_id not in config.AVAILABLE_MODELS:
            return {
                "success": False,
                "error": "Invalid model ID. Available models: " + ", ".join(config.AVAILABLE_MODELS.keys())
            }
        
        config.DEFAULT_MODEL = model_id
        config.OLLAMA_MODEL = model_id
        llm_client.model = model_id
        
        from web.routes.health import _health_cache
        _health_cache["model"] = model_id
        
        return {
            "success": True,
            "model": config.AVAILABLE_MODELS[model_id],
            "message": f"Switched to {config.AVAILABLE_MODELS[model_id]['name']}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
