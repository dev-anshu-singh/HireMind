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


def get_jd_parser_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.1,
) -> ChatGoogleGenerativeAI:
    """Factory returning configured LLM instance for JD Parser Agent."""
    selected_model = model_name or settings.JD_PARSER_MODEL_NAME or settings.DEFAULT_MODEL_NAME
    return get_llm(model_name=selected_model, temperature=temperature)


def get_job_post_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.2,
) -> ChatGoogleGenerativeAI:
    """Factory returning configured LLM instance for Job Post Generator Agent."""
    selected_model = model_name or settings.JOB_POST_GENERATOR_MODEL_NAME or settings.DEFAULT_MODEL_NAME
    return get_llm(model_name=selected_model, temperature=temperature)


def get_resume_parser_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.1,
) -> ChatGoogleGenerativeAI:
    """Factory returning configured LLM instance for Resume Parser Agent."""
    selected_model = model_name or settings.RESUME_PARSER_MODEL_NAME or settings.DEFAULT_MODEL_NAME
    return get_llm(model_name=selected_model, temperature=temperature)


def get_evaluator_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
) -> ChatGoogleGenerativeAI:
    """Factory returning configured LLM instance for Candidate Evaluator Agent."""
    selected_model = model_name or settings.EVALUATOR_MODEL_NAME or settings.DEFAULT_MODEL_NAME
    return get_llm(model_name=selected_model, temperature=temperature)


def get_evidence_verifier_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
) -> ChatGoogleGenerativeAI:
    """Factory returning configured LLM instance for Omni-Evidence Verifier Agent."""
    selected_model = model_name or settings.EVIDENCE_VERIFIER_MODEL_NAME or settings.DEFAULT_MODEL_NAME
    return get_llm(model_name=selected_model, temperature=temperature)


def get_campaign_monitor_llm(
    model_name: Optional[str] = None,
    temperature: float = 0.2,
) -> ChatGoogleGenerativeAI:
    """Factory returning configured LLM instance for Campaign Monitor LangGraph Agent."""
    selected_model = model_name or settings.CAMPAIGN_MONITOR_MODEL_NAME or settings.DEFAULT_MODEL_NAME
    return get_llm(model_name=selected_model, temperature=temperature)


def get_embeddings(
    model_name: Optional[str] = None,
) -> GoogleGenerativeAIEmbeddings:
    """
    Centralized factory function returning GoogleGenerativeAIEmbeddings for vector similarity.

    Args:
        model_name: Embedding model name. Defaults to settings.EMBEDDING_MODEL_NAME.

    Returns:
        GoogleGenerativeAIEmbeddings: Configured LangChain embedding model instance.
    """
    selected_model = model_name or settings.EMBEDDING_MODEL_NAME
    return GoogleGenerativeAIEmbeddings(
        model=selected_model,
        google_api_key=settings.GOOGLE_API_KEY,
    )
