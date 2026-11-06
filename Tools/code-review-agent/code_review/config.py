from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ReviewConfig:
    raw: dict[str, Any]

    @property
    def project(self) -> dict[str, Any]: return self.raw["project"]
    @property
    def model_service(self) -> dict[str, Any]: return self.raw.get("model_service", {})
    @property
    def checks(self) -> dict[str, Any]: return self.raw.get("checks", {})
    @property
    def storage(self) -> dict[str, Any]: return self.raw.get("storage", {})

    @classmethod
    def load(cls, path: Path) -> "ReviewConfig":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.raw, ensure_ascii=False, indent=2), encoding="utf-8")
