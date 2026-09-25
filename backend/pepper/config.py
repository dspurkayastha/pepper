"""Runtime settings, read once from the environment."""

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    agent_ids_path: Path
    app_token: str | None  # bootstrap secret, only used to enrol devices
    model: str
    pump_timeout_s: float
    session_budget_usd_cents: int | None
    apns_key_path: str | None
    apns_key_id: str | None
    apns_team_id: str | None
    apns_bundle_id: str
    apns_sandbox: bool
    cors_origins: list[str] = field(default_factory=list)

    def agent_ids(self) -> dict:
        """IDs written by scripts/setup_agent.py (agent, environment, vault)."""
        if self.agent_ids_path.exists():
            return json.loads(self.agent_ids_path.read_text())
        return {}


def _opt(name: str) -> str | None:
    value = os.getenv(name)
    return value or None


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.getenv("PEPPER_DATA_DIR", "/var/lib/pepper"))
    budget = _opt("PEPPER_SESSION_BUDGET_USD_CENTS")
    return Settings(
        data_dir=data_dir,
        database_url=os.getenv("PEPPER_DATABASE_URL", f"sqlite+aiosqlite:///{data_dir / 'pepper.db'}"),
        agent_ids_path=Path(os.getenv("PEPPER_AGENT_IDS", "agent_ids.json")),
        app_token=_opt("PEPPER_APP_TOKEN"),
        model=os.getenv("PEPPER_MODEL", "claude-opus-5"),
        pump_timeout_s=float(os.getenv("PEPPER_PUMP_TIMEOUT_S", "1800")),
        session_budget_usd_cents=int(budget) if budget else None,
        apns_key_path=_opt("APNS_KEY_PATH"),
        apns_key_id=_opt("APNS_KEY_ID"),
        apns_team_id=_opt("APNS_TEAM_ID"),
        apns_bundle_id=os.getenv("APNS_BUNDLE_ID", "com.sciscribe.pepper"),
        apns_sandbox=os.getenv("APNS_SANDBOX", "true").lower() == "true",
        cors_origins=[o for o in os.getenv("PEPPER_CORS_ORIGINS", "").split(",") if o],
    )
