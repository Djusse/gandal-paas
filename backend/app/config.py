from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./paas.db"
    gitlab_mode: str = "fake"            # fake | real
    orchestrator_mode: str = "mock"      # mock | real
    auth_mode: str = "dev"               # dev | oauth
    gitlab_url: str = ""
    gitlab_token: str = ""
    gitlab_group_id: int = 0
    gitlab_ca_bundle: str | None = None
    ci_template: str = "templates/build.yml@paas/ci-templates"
    webhook_secret: str = "change-me-long-random"
    webhook_public_url: str = "http://localhost:8000"
    orchestrator_url: str = ""
    internal_token: str = "change-me-long-random"                   # protects /internal/* callbacks

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
