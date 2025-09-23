import os
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = Field(default="production")
    APP_HOST: str = Field(default="0.0.0.0")
    APP_PORT: int = Field(default=8000)
    ALLOWED_ORIGINS: str = Field(default="*")
    DEFAULT_LANGUAGE: str = Field(default="de")

    # LLM / News
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = Field(default="gpt-4o-mini")
    TAVILY_API_KEY: str | None = None

    # PDF
    ENABLE_PDF: bool = Field(default=True)

    # DB (optional)
    DATABASE_URL: str | None = None

    # Admin
    ADMIN_TOKEN: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
