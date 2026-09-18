from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM configuration
    llm_provider: Literal["nvidia", "bedrock", "openai", "ollama"] = "nvidia"
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_api_key: str = "nvapi-xxx"
    llm_model: str = "openai/gpt-oss-20b"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 2048
    llm_timeout_s: int = 45
    llm_cache: bool = True
    use_bedrock_native: bool = False

    # Agent configuration
    agent_runtime: Literal["strands", "simple"] = "strands"
    max_tool_calls: int = 6
    enable_gap_checker: bool = True
    narrator_max_retries: int = 1

    # Risk policy & Knowledge Base
    risk_policy: str = "risk_policy_v1"
    kb_dir: str = "./app/kb"

    # AWS / Local storage
    aws_region: str = "us-west-2"
    ddb_table: str = "PayGuardCases"
    ddb_endpoint_url: Optional[str] = "http://localhost:8000"
    s3_bucket: str = "payguard-uploads"
    s3_endpoint_url: Optional[str] = "http://localhost:4566"

    # Data lifecycle & privacy
    case_ttl_days: int = 7
    raw_text_ttl_hours: int = 24
    store_raw_input: bool = False

    # Ingest & Security limits
    enable_redirect_resolution: bool = False
    max_upload_mb: int = 5
    rate_limit_per_min: int = 20


settings = Settings()
