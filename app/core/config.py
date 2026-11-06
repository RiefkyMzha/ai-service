from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    PROJECT_NAME: str = "CegahScam AI Service"
    API_V1_STR: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "nvidia/nemotron-3.5-super-vl:free"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1/chat/completions"

    CEGAHSCAM_API_TOKEN: str = ""
    MOCK_MODE: bool = False
    CORS_ORIGINS: str = "*"

settings = Settings()