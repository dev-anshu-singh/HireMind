from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from app.core.config import settings


def get_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.2,
) -> ChatGoogleGenerativeAI:
    """
    Centralized factory function returning a configured ChatGoogleGenerativeAI LLM instance.

    Args:
        model_name: Optional model override (e.g. 'gemini-3.6-flash').
                    Defaults to settings.DEFAULT_MODEL_NAME.
        temperature: Sampling temperature for creativity vs precision. Default is 0.2.

    Returns:
        ChatGoogleGenerativeAI: Configured LangChain chat model instance.
    """
    selected_model = model_name or settings.DEFAULT_MODEL_NAME

    return ChatGoogleGenerativeAI(
        model=selected_model,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=temperature,
        timeout=60.0,
        max_retries=3,
    )


def get_embeddings(
    model_name: str = "models/text-embedding-004",
) -> GoogleGenerativeAIEmbeddings:
    """
    Centralized factory function returning GoogleGenerativeAIEmbeddings for vector similarity.

    Args:
        model_name: Embedding model name. Defaults to 'models/text-embedding-004'.

    Returns:
        GoogleGenerativeAIEmbeddings: Configured LangChain embedding model instance.
    """
    return GoogleGenerativeAIEmbeddings(
        model=model_name,
        google_api_key=settings.GOOGLE_API_KEY,
    )
