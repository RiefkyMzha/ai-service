from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_REASONING_EFFORTS = {
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
}
_MIN_JSON_TOKEN_MARGIN = 1_200
_MIN_STANDALONE_MAX_TOKENS = 1_536


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    PROJECT_NAME: str = "CegahScam AI Service"
    API_V1_STR: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "nvidia/nemotron-3.5-super-vl:free"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    OPENROUTER_ZDR_ONLY: bool = False
    OPENROUTER_STRUCTURED_OUTPUTS: bool = False
    OPENROUTER_REASONING_EFFORT: str = ""
    OPENROUTER_REASONING_MAX_TOKENS: Optional[int] = None
    OPENROUTER_MAX_TOKENS: Optional[int] = None

    CEGAHSCAM_API_TOKEN: str = ""
    MOCK_MODE: bool = False
    CORS_ORIGINS: str = "*"

    @field_validator(
        "MOCK_MODE",
        "OPENROUTER_ZDR_ONLY",
        "OPENROUTER_STRUCTURED_OUTPUTS",
        mode="before",
    )
    @classmethod
    def parse_optional_bool(cls, value: object) -> object:
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        return value

    @field_validator("OPENROUTER_REASONING_EFFORT", mode="before")
    @classmethod
    def validate_reasoning_effort(cls, value: object) -> str:
        if value is None:
            return ""
        text = str(value).strip().lower()
        if not text:
            return ""
        if text not in _VALID_REASONING_EFFORTS:
            raise ValueError("OPENROUTER_REASONING_EFFORT tidak valid.")
        return text

    @field_validator(
        "OPENROUTER_REASONING_MAX_TOKENS",
        "OPENROUTER_MAX_TOKENS",
        mode="before",
    )
    @classmethod
    def parse_optional_positive_int(cls, value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("Nilai token harus berupa bilangan bulat positif.")
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            value = stripped
        parsed = int(value)
        if parsed < 1:
            raise ValueError("Nilai token harus minimal 1.")
        return parsed

    @model_validator(mode="after")
    def validate_token_budgets(self) -> "Settings":
        if (
            self.OPENROUTER_REASONING_EFFORT
            and self.OPENROUTER_REASONING_MAX_TOKENS is not None
        ):
            raise ValueError(
                "OPENROUTER_REASONING_EFFORT dan OPENROUTER_REASONING_MAX_TOKENS tidak boleh diisi bersamaan."
            )
        if (
            self.OPENROUTER_MAX_TOKENS is not None
            and self.OPENROUTER_REASONING_MAX_TOKENS is not None
            and self.OPENROUTER_MAX_TOKENS - self.OPENROUTER_REASONING_MAX_TOKENS
            < _MIN_JSON_TOKEN_MARGIN
        ):
            raise ValueError(
                "OPENROUTER_MAX_TOKENS harus memiliki margin minimal 1200 token di atas OPENROUTER_REASONING_MAX_TOKENS."
            )
        if (
            self.OPENROUTER_MAX_TOKENS is not None
            and self.OPENROUTER_REASONING_MAX_TOKENS is None
            and self.OPENROUTER_MAX_TOKENS < _MIN_STANDALONE_MAX_TOKENS
        ):
            raise ValueError(
                "OPENROUTER_MAX_TOKENS minimal 1536 bila digunakan tanpa OPENROUTER_REASONING_MAX_TOKENS."
            )
        return self


settings = Settings()