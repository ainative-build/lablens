"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DashScope (Qwen API)
    dashscope_api_key: str = ""
    dashscope_api_base: str = "https://dashscope-intl.aliyuncs.com/api/v1"
    dashscope_ocr_model: str = "qwen-vl-ocr"
    dashscope_chat_model: str = "qwen-plus"             # Text generation (intl endpoint)
    dashscope_structure_model: str = "qwen3-vl-plus"   # Section-aware re-extraction
    dashscope_verify_model: str = "qwen-plus"           # Semantic verifier (Phase 4)
    dashscope_embedding_model: str = "text-embedding-v3"

    # Alibaba GDB (optional for Phases 1-5; required for Phase 6 graph enrichment)
    gdb_host: str | None = None
    gdb_port: int = 8182
    gdb_username: str | None = None
    gdb_password: str | None = None

    # DashVector
    dashvector_api_key: str = ""
    dashvector_endpoint: str = ""
    dashvector_collection: str = "lab_education"

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    max_upload_size_mb: int = 20

    # CORS — dev default ["*"] permits any origin; prod sets explicit list
    # via LABLENS_ALLOWED_ORIGINS=["https://lablens.ainative.build"]
    # (pydantic-settings parses JSON arrays from env automatically)
    allowed_origins: list[str] = ["*"]

    model_config = {"env_file": ".env", "env_prefix": "LABLENS_"}


settings = Settings()

# Set DashScope SDK base URL for international endpoint
import dashscope as _dashscope

_dashscope.base_http_api_url = settings.dashscope_api_base
