"""AppManager — CRUD operations for generated applications."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from nanobot.app.schema import AppSpec


class AppManager:
    """Persists app specifications as JSON files in workspace/apps/."""

    def __init__(self, workspace: Path) -> None:
        self._dir = workspace / "apps"
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, spec: AppSpec) -> None:
        path = self._dir / f"{spec.id}.json"
        path.write_text(json.dumps(spec.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, app_id: str) -> AppSpec | None:
        path = self._dir / f"{app_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return AppSpec.model_validate(data)
        except Exception:
            return None

    def delete(self, app_id: str) -> bool:
        path = self._dir / f"{app_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_apps(self) -> list[dict[str, Any]]:
        result = []
        for p in sorted(self._dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                result.append({
                    "id": data.get("id", p.stem),
                    "title": data.get("title", p.stem),
                    "description": data.get("description", ""),
                    "created_at": data.get("created_at", ""),
                    "layout_type": data.get("layout", {}).get("type", "single-page"),
                    "component_count": len(data.get("components", [])),
                })
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex[:12]
