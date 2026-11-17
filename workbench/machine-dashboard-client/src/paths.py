from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ClientPaths:
    root: Path

    @property
    def config_root(self) -> Path:
        """Fixed per-user configuration directory, separate from client data."""
        return self.root / "config"

    @property
    def config(self) -> Path:
        return self.config_root / "settings.json"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def log(self) -> Path:
        return self.root / "logs" / "local-agent.log"

    @property
    def pid(self) -> Path:
        return self.root / "run" / "local-agent.pid"
