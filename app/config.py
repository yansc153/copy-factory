from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    app_env: str = os.getenv("COPY_FACTORY_ENV", "local")
    db_path: str = os.getenv("COPY_FACTORY_DB", "data/copy_factory.sqlite3")
    user: str = os.getenv("COPY_FACTORY_USER", "admin")
    password: str = os.getenv("COPY_FACTORY_PASSWORD", "password")
    session_secret: str = os.getenv("COPY_FACTORY_SESSION_SECRET", "dev-secret-change-me")
    sources: tuple[str, ...] = tuple(
        s.strip() for s in os.getenv("COPY_FACTORY_SOURCES", "mock-xueqiu,mock-reddit").split(",") if s.strip()
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate_for_web(self) -> None:
        if self.is_production:
            unsafe = {
                "COPY_FACTORY_USER": self.user == "admin",
                "COPY_FACTORY_PASSWORD": self.password == "password",
                "COPY_FACTORY_SESSION_SECRET": self.session_secret == "dev-secret-change-me",
            }
            bad = [name for name, is_bad in unsafe.items() if is_bad]
            if bad:
                raise RuntimeError(f"production requires secure env vars: {', '.join(bad)}")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
