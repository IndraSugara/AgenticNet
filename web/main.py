"""
FastAPI Web Application for Network Infrastructure Agent

Optimized with:
- Non-blocking health checks
- Background health monitoring
- Lifespan context manager (replacing deprecated on_event)
- Request timeout handling
- Modular route organization
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging
import os

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False

from config import config
from modules.monitoring import monitoring

# LangGraph Agent (primary - required)
from agent.langchain_tools import get_all_tools
print(f"🔗 LangGraph agent loaded with {len(get_all_tools())} tools")

# Import route modules
from web.routes import health as health_routes
from web.routes import chat as chat_routes
from web.routes import models as model_routes
from web.routes import workflows as workflow_routes
from web.routes import infrastructure as infra_routes
from web.routes import devices as device_routes
from web.routes import guardrails as guardrails_routes
from web.routes import log_watch as logwatch_routes
from web.routes import logs as logs_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events"""
    # Startup
    print("🚀 Starting Agentic Network Infrastructure Operator...")
    print(f"📡 Checking Ollama connection at {config.OLLAMA_HOST}...")
    
    # Non-blocking initial health check
    await health_routes.update_health_cache()
    health_cache = health_routes.get_health_cache()
    
    if health_cache["ollama_connected"]:
        print(f"✅ Connected to Ollama with model: {config.OLLAMA_MODEL}")
    else:
        print(f"⚠️ Ollama not available at startup")
    
    print(f"🔧 LangGraph Tools: {len(get_all_tools())} tools available")
    
    # Start background tasks
    health_task = asyncio.create_task(health_routes.health_check_background_task())
    network_task = asyncio.create_task(health_routes.network_monitor_task())
    metrics_task = asyncio.create_task(health_routes.metrics_broadcast_task())
    print("📡 WebSocket metrics broadcast started (every 5s)")
    
    # Start system metrics collection
    monitoring.start_collection(interval=10)
    
    print(f"🌐 Server ready at http://{config.HOST}:{config.PORT}")
    
    yield  # App is running
    
    # Shutdown
    monitoring.stop_collection()
    health_task.cancel()
    network_task.cancel()
    metrics_task.cancel()
    try:
        await health_task
        await network_task
        await metrics_task
    except asyncio.CancelledError:
        pass
    print("👋 Shutting down...")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Agentic Network Infrastructure Operator",
    description="AI-powered network infrastructure management with LangGraph",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS — use env var for origins, fallback to wildcard in dev mode
_cors_origins = (
    [o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()]
    if config.CORS_ORIGINS
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],  # Only allow credentials when origins are explicit
    allow_methods=["*"],
    allow_headers=["*"],
)


# Optional API key authentication middleware
class APIKeyMiddleware(BaseHTTPMiddleware):
    """Simple API key authentication via X-API-Key header.
    
    When API_KEY is not set in config, authentication is disabled (dev mode).
    Health and static endpoints are always exempt.
    """
    
    EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/"}
    EXEMPT_PREFIXES = ("/static/",)
    
    async def dispatch(self, request: Request, call_next):
        # Skip auth if API_KEY is not configured (dev mode)
        if not config.API_KEY:
            return await call_next(request)
        
        # Skip auth for exempt paths
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith(self.EXEMPT_PREFIXES):
            return await call_next(request)
        
        # Skip auth for WebSocket upgrades (they handle auth differently)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        
        # Check API key
        api_key = request.headers.get("X-API-Key", "")
        if api_key != config.API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key. Set X-API-Key header."}
            )
        
        return await call_next(request)


app.add_middleware(APIKeyMiddleware)

# Rate limiting via SlowAPI
logger = logging.getLogger("web.main")
if SLOWAPI_AVAILABLE and config.RATE_LIMIT:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[config.RATE_LIMIT],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info(f"Rate limiting enabled: {config.RATE_LIMIT}")
elif not SLOWAPI_AVAILABLE:
    logger.warning("slowapi not installed — rate limiting disabled. Install with: pip install slowapi")

# Setup templates and static files
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
static_dir = os.path.join(os.path.dirname(__file__), "static")

os.makedirs(templates_dir, exist_ok=True)
os.makedirs(static_dir, exist_ok=True)
os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
os.makedirs(os.path.join(static_dir, "js"), exist_ok=True)

templates = Jinja2Templates(directory=templates_dir)

print(f"📁 Static directory path: {static_dir}")
app.mount("/static", StaticFiles(directory=static_dir), name="static")
print(f"✅ Mounted static files at /static")


# Register route modules
app.include_router(health_routes.router)
app.include_router(chat_routes.router)
app.include_router(model_routes.router)
app.include_router(workflow_routes.router)
app.include_router(infra_routes.router)
app.include_router(device_routes.router)
app.include_router(guardrails_routes.router)
app.include_router(logwatch_routes.router)
app.include_router(logs_routes.router)


# Dashboard route (stays in main for template access)
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main dashboard"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "model": config.OLLAMA_MODEL
    })
