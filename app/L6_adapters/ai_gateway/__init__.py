"""AI Gateway adapter: tier-based routing to local (Ollama) and hosted (Anthropic) providers.

Per ADR-0004 the hosted tier uses the Anthropic SDK directly (not a gateway proxy).

Public surface:
    - Tier, Message, CompletionRequest, CompletionResponse, AIGatewayError (from .base)
    - AIGateway (abstract, from .base)
    - OllamaGateway (concrete, from .local)
    - AnthropicGateway (concrete, from .anthropic_gateway)
    - TieredAIGateway (dispatching composite, from .router)
"""
from .anthropic_gateway import AnthropicGateway
from .base import (
    AIGateway,
    AIGatewayError,
    CompletionRequest,
    CompletionResponse,
    Message,
    Tier,
)
from .local import OllamaGateway
from .router import TieredAIGateway

__all__ = [
    "AIGateway",
    "AIGatewayError",
    "AnthropicGateway",
    "CompletionRequest",
    "CompletionResponse",
    "Message",
    "OllamaGateway",
    "Tier",
    "TieredAIGateway",
]
