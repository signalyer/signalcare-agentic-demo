"""AI Gateway adapter: tier-based routing to local (Ollama) and hosted (OpenRouter) providers.

Public surface:
    - Tier, Message, CompletionRequest, CompletionResponse, AIGatewayError (from .base)
    - AIGateway (abstract, from .base)
    - OllamaGateway (concrete, from .local)
    - OpenRouterGateway (concrete, from .openrouter)
    - TieredAIGateway (dispatching composite, from .router)
"""
from .base import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    CompletionResponse,
    Message,
    Tier,
)
from .local import OllamaGateway
from .openrouter import OpenRouterGateway
from .router import TieredAIGateway

__all__ = [
    "AIGateway",
    "AIGatewayError",
    "CompletionRequest",
    "CompletionResponse",
    "Message",
    "OllamaGateway",
    "OpenRouterGateway",
    "Tier",
    "TieredAIGateway",
]
