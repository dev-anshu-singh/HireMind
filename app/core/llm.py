"""
Centralized LLM Provider Module.

Initializes and exposes Google Gemini Chat models using configuration
from app.core.config. Centralizing LLM creation ensures all agents
share uniform initialization logic and credential management.
"""

from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings


def get_llm(
    model_name: Optional[str] = None, 
    temperature: float = 0.1
) -> ChatGoogleGenerativeAI:
    """
    Factory function to get an initialized Google Gemini LLM instance.

    Args:
        model_name: Override model name (defaults to settings.DEFAULT_MODEL_NAME).
        temperature: Model sampling temperature (default 0.1 for factual outputs).

    Returns:
        ChatGoogleGenerativeAI instance.
    """
    target_model = model_name or settings.DEFAULT_MODEL_NAME

    return ChatGoogleGenerativeAI(
        model=target_model,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
    )
