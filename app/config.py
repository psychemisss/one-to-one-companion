from decouple import config
from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    name: str = Field(default_factory=lambda: config("APP_NAME", default="1:1 Companion"))
    timezone: str = Field(default_factory=lambda: config("TIMEZONE", default="Europe/Kyiv"))
    default_language: str = Field(default_factory=lambda: config("DEFAULT_LANGUAGE", default="en"))
    default_cadence_days: int = Field(default_factory=lambda: config("DEFAULT_CADENCE_DAYS", default=75, cast=int))
    due_soon_days: int = Field(default_factory=lambda: config("DUE_SOON_DAYS", default=14, cast=int))


class DBSettings(BaseModel):
    path: str = Field(default_factory=lambda: config("DB_PATH", default="/data/one_on_one.db"))


class AuthSettings(BaseModel):
    app_password: str | None = Field(default_factory=lambda: config("APP_PASSWORD", default=None) or None)


class LogSettings(BaseModel):
    level: str = Field(default_factory=lambda: config("LOG_LEVEL", default="INFO"))
    to_file: bool = Field(default_factory=lambda: config("LOG_TO_FILE", default=True, cast=bool))
    dir: str = Field(default_factory=lambda: config("LOG_DIR", default="/data/logs"))
    rotation: str = Field(default_factory=lambda: config("LOG_ROTATION", default="10 MB"))
    retention: str = Field(default_factory=lambda: config("LOG_RETENTION", default="14 days"))


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    db: DBSettings = Field(default_factory=DBSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    log: LogSettings = Field(default_factory=LogSettings)


settings = Settings()
