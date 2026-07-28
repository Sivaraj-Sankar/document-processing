from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Ententia IDP"
    version: str = "0.1.0"
    cache_dir: Path = Path.home() / ".cache" / "ententia-idp"
    request_timeout_seconds: int = 120
    enable_prometheus: bool = True
    prometheus_metrics_path: str = "/metrics"

    # Required — no defaults; must be set via env vars or .env
    aws_region: str
    bedrock_model_id: str
    aws_profile_name: str

    bedrock_max_tokens: int = 4096

    model_config = {"env_prefix": "ENTENTIA_IDP_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
