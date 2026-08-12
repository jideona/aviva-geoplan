"""Application configuration. All values come from the environment."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_db: str = "geoplan"
    postgres_user: str = "geoplan"
    postgres_password: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    redis_url: str = "redis://redis:6379/0"

    # Object storage (MinIO / S3) for field-survey photos & video. Access keys
    # reuse the MinIO root credentials from the environment.
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = Field(default="geoplan", validation_alias="MINIO_ROOT_USER")
    minio_secret_key: str = Field(default="", validation_alias="MINIO_ROOT_PASSWORD")
    minio_bucket: str = "geoplan"
    minio_secure: bool = False
    # Public endpoint a device off the Docker network uses for presigned URLs
    # (the host maps MinIO to 9010); differs from the in-cluster endpoint above.
    minio_public_endpoint: str = "localhost:9010"

    jwt_secret: str
    jwt_access_minutes: int = 60
    jwt_refresh_days: int = 14

    allowed_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    seed_admin_email: str = "admin@avivanetworx.com.ng"
    seed_admin_password: str = ""

    # Maximum project boundary area, guarding against an accidental
    # country-sized import (SRD FR-PRJ-006).
    max_boundary_area_sqkm: float = 2000.0

    # Auto-fetch a ward/district boundary from GRID3 or OSM on project
    # creation when one isn't already cached. Fetch-once-then-cache — see
    # app/db/models/reference_boundary.py. Off switch for offline/CI envs,
    # or if either upstream needs to be paused without a code change.
    auto_fetch_reference_boundaries: bool = True
    reference_fetch_timeout_seconds: float = 15.0

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
