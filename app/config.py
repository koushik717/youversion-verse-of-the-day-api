import os


class Settings:
    youversion_base_url: str = os.environ.get(
        "YOUVERSION_BASE_URL", "https://api.youversion.com"
    )
    youversion_app_key: str = os.environ.get("YOUVERSION_APP_KEY", "")
    default_version_id: int = int(os.environ.get("DEFAULT_VERSION_ID", "206"))
    request_timeout_seconds: float = float(
        os.environ.get("YOUVERSION_TIMEOUT_SECONDS", "5")
    )


settings = Settings()
