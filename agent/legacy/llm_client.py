"""
LLM Client for Ollama + LLaMA 3.x + DeepSeek Integration

Supports:
- Ollama for local LLM (LLaMA 3.x)
- DeepSeek API for production
- Async support for non-blocking calls
- Timeout handling
- Connection caching with TTL
- Retry logic with backoff
"""
import os
import asyncio
import time
from typing import Optional, List, Dict, Any
from functools import lru_cache
from enum import Enum

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    from openai import OpenAI, AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from config import config


class LLMProvider(Enum):
    """LLM provider selection"""
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"


class LLMClient:
    """Client for communicating with LLMs (Ollama or DeepSeek)"""
    
    # Class-level cache for connection status
    _connection_cache: Dict[str, Any] = {
        "status": None,
        "timestamp": 0,
        "ttl": 30  # Cache TTL in seconds
    }
    
    def __init__(
        self, 
        model: str = None, 
        host: str = None,
        provider: LLMProvider = None
    ):
        self.model = model or config.OLLAMA_MODEL
        self.host = host or config.OLLAMA_HOST
        self.default_timeout = 120  # Default timeout in seconds
        
        # Determine provider
        deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        
        if provider:
            self.provider = provider
        elif deepseek_key:
            self.provider = LLMProvider.DEEPSEEK
            self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-coder")
        else:
            self.provider = LLMProvider.OLLAMA
        
        # Initialize clients
        self.ollama_client = None
        self.deepseek_client = None
        self.deepseek_async_client = None
        
        if self.provider == LLMProvider.OLLAMA and OLLAMA_AVAILABLE:
            self.ollama_client = ollama.Client(host=self.host)
            print(f"🦙 Using Ollama with model: {self.model}")
        
        elif self.provider == LLMProvider.DEEPSEEK and OPENAI_AVAILABLE:
            self.deepseek_client = OpenAI(
                api_key=deepseek_key,
                base_url="https://api.deepseek.com/v1"
            )
            self.deepseek_async_client = AsyncOpenAI(
                api_key=deepseek_key,
                base_url="https://api.deepseek.com/v1"
            )
            print(f"🤖 Using DeepSeek with model: {self.model}")
        
    def check_connection(self, use_cache: bool = True) -> bool:
        """
        Check if LLM provider is running and model is available.
        Uses cached result if available and not expired.
        """
        cache = self._connection_cache
        now = time.time()
        
        # Return cached result if still valid
        if use_cache and cache["status"] is not None:
            if now - cache["timestamp"] < cache["ttl"]:
                return cache["status"]
        
        result = False
        
        try:
            if self.provider == LLMProvider.DEEPSEEK:
                # Test DeepSeek with a simple request
                if self.deepseek_client:
                    self.deepseek_client.models.list()
                    result = True
            else:
                # Test Ollama
                if self.ollama_client:
                    response = self.ollama_client.list()
                    models = response.get('models', []) if isinstance(response, dict) else getattr(response, 'models', [])
                    available = []
                    for m in models:
                        if isinstance(m, dict):
                            available.append(m.get('name', ''))
                        else:
                            available.append(getattr(m, 'model', '') or getattr(m, 'name', ''))
                    result = any(self.model in name for name in available)
        except Exception as e:
            print(f"❌ LLM connection check failed: {e}")
            result = False
        
        # Update cache
        cache["status"] = result
        cache["timestamp"] = now
        
        return result
    
    async def check_connection_async(self, use_cache: bool = True) -> bool:
        """Async version of connection check"""
        return await asyncio.to_thread(self.check_connection, use_cache)
    
    def pull_model(self) -> bool:
        """Pull the model if not available (Ollama only)"""
        if self.provider != LLMProvider.OLLAMA:
            return True  # DeepSeek doesn't need model pulling
        
        try:
            print(f"📥 Pulling model {self.model}...")
            self.ollama_client.pull(self.model)
            print(f"✅ Model {self.model} ready")
            return True
        except Exception as e:
            print(f"❌ Failed to pull model: {e}")
            return False
    
    def chat(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Send chat completion request to LLM (synchronous)
        
        Args:
            messages: List of {"role": "user/assistant", "content": "..."}
            system_prompt: Optional system prompt override
            temperature: Sampling temperature (0.0-1.0)
        
        Returns:
            Response dict with 'message' containing 'content'
        """
        full_messages = self._prepare_messages(messages, system_prompt)
        
        try:
            if self.provider == LLMProvider.DEEPSEEK:
                return self._chat_deepseek(full_messages, temperature)
            else:
                return self._chat_ollama(full_messages, temperature)
        except Exception as e:
            return {"error": str(e), "message": {"content": f"Error: {e}"}}
    
    def _chat_ollama(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float
    ) -> Dict[str, Any]:
        """Chat via Ollama"""
        response = self.ollama_client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": temperature}
        )
        return response
    
    def _chat_deepseek(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float
    ) -> Dict[str, Any]:
        """Chat via DeepSeek API"""
        response = self.deepseek_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=4096
        )
        
        # Convert to Ollama-compatible format
        content = response.choices[0].message.content if response.choices else ""
        return {
            "message": {"content": content},
            "model": self.model,
            "provider": "deepseek"
        }
    
    async def chat_async(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None,
        temperature: float = 0.7,
        timeout: float = None
    ) -> Dict[str, Any]:
        """
        Async version of chat with timeout support
        
        Args:
            messages: List of {"role": "user/assistant", "content": "..."}
            system_prompt: Optional system prompt override
            temperature: Sampling temperature (0.0-1.0)
            timeout: Timeout in seconds (default: self.default_timeout)
        
        Returns:
            Response dict with 'message' containing 'content'
        """
        timeout = timeout or self.default_timeout
        full_messages = self._prepare_messages(messages, system_prompt)
        
        try:
            if self.provider == LLMProvider.DEEPSEEK:
                result = await asyncio.wait_for(
                    self._chat_deepseek_async(full_messages, temperature),
                    timeout=timeout
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._chat_ollama,
                        full_messages,
                        temperature
                    ),
                    timeout=timeout
                )
            return result
        except asyncio.TimeoutError:
            return {
                "error": f"Timeout after {timeout}s",
                "message": {"content": f"⏱️ Request timeout setelah {timeout} detik. Model mungkin sedang sibuk atau terlalu lambat."}
            }
        except Exception as e:
            return {"error": str(e), "message": {"content": f"Error: {e}"}}
    
    async def _chat_deepseek_async(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float
    ) -> Dict[str, Any]:
        """Async chat via DeepSeek API"""
        response = await self.deepseek_async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=4096
        )
        
        content = response.choices[0].message.content if response.choices else ""
        return {
            "message": {"content": content},
            "model": self.model,
            "provider": "deepseek"
        }
    
    def _prepare_messages(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None
    ) -> List[Dict[str, str]]:
        """Prepare message list with system prompt"""
        full_messages = []
        
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        else:
            full_messages.append({"role": "system", "content": config.SYSTEM_PROMPT})
        
        full_messages.extend(messages)
        return full_messages
    
    def stream_chat(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None,
        temperature: float = 0.7
    ):
        """
        Stream chat completion for real-time responses
        
        Yields:
            Chunks of response text
        """
        full_messages = self._prepare_messages(messages, system_prompt)
        
        try:
            if self.provider == LLMProvider.DEEPSEEK:
                stream = self.deepseek_client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    temperature=temperature,
                    max_tokens=4096,
                    stream=True
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            else:
                stream = self.ollama_client.chat(
                    model=self.model,
                    messages=full_messages,
                    options={"temperature": temperature},
                    stream=True
                )
                for chunk in stream:
                    if 'message' in chunk and 'content' in chunk['message']:
                        yield chunk['message']['content']
        except Exception as e:
            yield f"Error: {e}"
    
    async def stream_chat_async(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None,
        temperature: float = 0.7
    ):
        """
        Async generator for streaming chat
        
        Yields:
            Chunks of response text
        """
        import queue
        import threading
        
        q = queue.Queue()
        
        def producer():
            try:
                for chunk in self.stream_chat(messages, system_prompt, temperature):
                    q.put(chunk)
            except Exception as e:
                q.put(f"Error: {e}")
            finally:
                q.put(None)  # Signal end
        
        # Start producer in thread
        thread = threading.Thread(target=producer, daemon=True)
        thread.start()
        
        # Yield chunks as they arrive
        while True:
            try:
                chunk = await asyncio.to_thread(q.get, timeout=1)
                if chunk is None:
                    break
                yield chunk
            except:
                if not thread.is_alive():
                    break
    
    def invalidate_cache(self):
        """Invalidate the connection cache"""
        self._connection_cache["status"] = None
        self._connection_cache["timestamp"] = 0
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get current provider information"""
        return {
            "provider": self.provider.value,
            "model": self.model,
            "host": self.host if self.provider == LLMProvider.OLLAMA else "api.deepseek.com",
            "connected": self.check_connection(use_cache=True)
        }


# Singleton instance
llm_client = LLMClient()

