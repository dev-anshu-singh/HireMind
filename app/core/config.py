from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "HireMind"
    API_V1_STR: str = "/api/v1"
    
    # Primary Database URL (Synchronous format from Neon console or local fallback)
    DATABASE_URL: str = "sqlite:///./hiremind.db"
    
    SECRET_KEY: str = "dev_secret_key_change_in_production"
    ENVIRONMENT: str = "development"
    
    # LLM Configuration
    DEFAULT_MODEL_NAME: str = "gemini-3.6-flash"
    JD_PARSER_MODEL_NAME: str = "gemini-3.6-flash"
    JOB_POST_GENERATOR_MODEL_NAME: str = "gemini-3.6-flash"
    RESUME_PARSER_MODEL_NAME: str = "gemini-3.6-flash"
    EVALUATOR_MODEL_NAME: str = "gemini-3.6-flash"
    EVIDENCE_VERIFIER_MODEL_NAME: str = "gemini-3.6-flash"
    CAMPAIGN_MONITOR_MODEL_NAME: str = "gemini-3.6-flash"
    EMBEDDING_MODEL_NAME: str = "models/text-embedding-004"

    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLAMA_CLOUD_API_KEY: str = ""

    @property
    def async_database_url(self) -> str:
        """
        Derive async database URL for SQLModel/SQLAlchemy async engine.
        Converts postgresql:// to postgresql+asyncpg:// and maps libpq sslmode parameter.
        """
        url = self.DATABASE_URL
        if url.startswith("sqlite:///"):
            return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)

        # Convert libpq parameters (sslmode, channel_binding) for asyncpg driver compatibility
        if "?" in url:
            base_url, query_params = url.split("?", 1)
            cleaned_params = []
            for param in query_params.split("&"):
                if param.startswith("channel_binding="):
                    continue
                elif param.startswith("sslmode="):
                    val = param.split("=", 1)[1]
                    if val in ["require", "verify-ca", "verify-full", "prefer"]:
                        cleaned_params.append("ssl=require")
                    else:
                        cleaned_params.append(f"ssl={val}")
                else:
                    cleaned_params.append(param)
            url = f"{base_url}?{'&'.join(cleaned_params)}" if cleaned_params else base_url

        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
