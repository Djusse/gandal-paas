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

    # GitLab de simulation : permet de pointer vers le registry réel du cluster
    # (plan Phase 4). Par défaut, comportement inchangé (`fake-registry/paas`).
    gitlab_fake_registry: str = "fake-registry/paas"
    gitlab_fake_repository: str = ""   # si défini, utilisé pour tous les projets
    gitlab_fake_tag: str = "a1b2c3d4"
    gitlab_fake_digest: str = "sha256:" + "0" * 64  # vide = pas de digest

    orchestrator_url: str = ""
    orchestrator_token: str = "change-me-long-random"  # envoyé à l'orchestrateur
    orchestrator_timeout: float = 15.0
    orchestrator_retries: int = 3
    internal_token: str = "change-me-long-random"       # protège /internal/*

    # Valeur par défaut alignée sur l'infra (D8) : 2 réplicas par projet.
    default_replicas: int = 2

    # Relance périodique (R1, R11) : un déploiement resté `requested` est
    # renvoyé, un déploiement resté `deploying` est interrogé.
    recovery_enabled: bool = True
    recovery_interval: int = 60
    requested_timeout: int = 120
    deploying_timeout: int = 300
    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
