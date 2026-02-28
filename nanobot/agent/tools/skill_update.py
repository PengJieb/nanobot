"""Skill update tool: list, check, and update workspace skills."""

import ast
import asyncio
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class SkillUpdater:
    """Core logic for listing, checking, and updating workspace skills."""

    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._skills_dir = workspace / "skills"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_skills(self) -> str:
        """Return a formatted list of installed workspace skills."""
        skills = self._get_installed_skills()
        if not skills:
            return "No skills installed in workspace/skills/."
        lines = ["Installed skills:\n"]
        for s in skills:
            source = self._get_source_type(s)
            ver = s.get("version", "—")
            desc = s.get("description", "No description")
            lines.append(f"- **{s['name']}** (v{ver}, {source}): {desc}")
        return "\n".join(lines)

    async def check_updates(self, names: list[str] | None = None) -> str:
        """Check for available updates without installing."""
        skills = self._filter_skills(names)
        if isinstance(skills, str):
            return skills  # error message

        clawhub_skills = [s for s in skills if self._get_source_type(s) == "clawhub"]
        if not clawhub_skills:
            return "No ClawHub-sourced skills found to check."

        slug_args: list[str] = []
        for s in clawhub_skills:
            slug_args.extend(["--skill", s["name"]])

        rc, stdout, stderr = await self._run_clawhub(["update", "--check", *slug_args])
        if rc != 0:
            return f"clawhub check failed (exit {rc}):\n{stderr or stdout}"
        return stdout or "All skills are up to date."

    async def update_skills(
        self, names: list[str] | None = None, backup: bool = True
    ) -> str:
        """Update all or specified skills. Returns a summary."""
        skills = self._filter_skills(names)
        if isinstance(skills, str):
            return skills

        results: list[str] = []
        for s in skills:
            source = self._get_source_type(s)
            skill_dir = self._skills_dir / s["name"]

            if source != "clawhub":
                results.append(f"- **{s['name']}**: Skipped (no update source)")
                continue

            # Backup
            if backup:
                bak = self._backup_skill(skill_dir)
                results.append(f"- **{s['name']}**: Backed up to {bak.name}")

            # Run clawhub update
            rc, stdout, stderr = await self._run_clawhub(
                ["install", s["name"]]
            )
            if rc != 0:
                results.append(f"- **{s['name']}**: Update FAILED (exit {rc}): {stderr or stdout}")
                continue

            # Validate Python scripts
            warnings = self._validate_python_scripts(skill_dir)
            status = "Updated"
            if warnings:
                status += " (with warnings)"
                for w in warnings:
                    results.append(f"  - {w}")
            results.append(f"- **{s['name']}**: {status}")

        return "Update results:\n" + "\n".join(results) if results else "Nothing to update."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_installed_skills(self) -> list[dict]:
        """Scan workspace/skills/ and parse each skill's metadata."""
        if not self._skills_dir.is_dir():
            return []
        skills: list[dict] = []
        for child in sorted(self._skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.is_file():
                try:
                    content = skill_md.read_text(encoding="utf-8")
                except OSError:
                    continue
                meta = self._parse_frontmatter(content)
                meta.setdefault("name", child.name)
                skills.append(meta)
        return skills

    @staticmethod
    def _parse_frontmatter(content: str) -> dict:
        """Parse YAML frontmatter from SKILL.md content."""
        if not content.startswith("---"):
            return {}
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return {}
        metadata: dict[str, str] = {}
        for line in match.group(1).split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip().strip("\"'")
        return metadata

    @staticmethod
    def _get_source_type(metadata: dict) -> str:
        """Determine skill source from metadata."""
        homepage = metadata.get("homepage", "")
        meta_raw = metadata.get("metadata", "")
        if "clawhub" in homepage.lower() or "clawhub" in meta_raw.lower():
            return "clawhub"
        return "manual"

    def _backup_skill(self, skill_dir: Path) -> Path:
        """Backup a skill directory with timestamp suffix."""
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        bak = skill_dir.parent / f"{skill_dir.name}.bak.{stamp}"
        shutil.copytree(skill_dir, bak)
        return bak

    async def _run_clawhub(self, args: list[str]) -> tuple[int, str, str]:
        """Run clawhub CLI via npx. Returns (returncode, stdout, stderr)."""
        cmd = [
            "npx", "--yes", "clawhub@latest",
            *args,
            "--workdir", str(self._workspace),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            return proc.returncode or 0, stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            return 1, "", "clawhub command timed out after 120s"
        except FileNotFoundError:
            return 1, "", "npx not found — Node.js is required for ClawHub operations"

    @staticmethod
    def _validate_python_scripts(skill_dir: Path) -> list[str]:
        """Check .py files for top-level class definitions. Return warnings."""
        warnings: list[str] = []
        for py_file in skill_dir.rglob("*.py"):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                warnings.append(f"{py_file.name}: syntax error")
                continue
            has_class = any(
                isinstance(node, ast.ClassDef) for node in ast.iter_child_nodes(tree)
            )
            if not has_class:
                warnings.append(f"{py_file.name}: no top-level class found")
        return warnings

    def _filter_skills(self, names: list[str] | None) -> list[dict] | str:
        """Return matching skills or an error string."""
        installed = self._get_installed_skills()
        if not installed:
            return "No skills installed in workspace/skills/."
        if not names:
            return installed
        installed_map = {s["name"]: s for s in installed}
        missing = [n for n in names if n not in installed_map]
        if missing:
            return f"Unknown skill(s): {', '.join(missing)}"
        return [installed_map[n] for n in names]


class SkillUpdateTool(Tool):
    """Tool wrapper that exposes SkillUpdater to the agent."""

    def __init__(self, workspace: Path):
        self._updater = SkillUpdater(workspace)

    @property
    def name(self) -> str:
        return "skill_update"

    @property
    def description(self) -> str:
        return (
            "List, check for updates, or update installed workspace skills. "
            "Supports ClawHub-sourced skills with automatic backup and validation."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "check", "update"],
                    "description": "Action to perform: list installed skills, check for updates, or update skills.",
                },
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of skill names to target. Omit to target all.",
                },
                "backup": {
                    "type": "boolean",
                    "description": "Create backup before updating (default true).",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, names: list[str] | None = None, backup: bool = True, **kwargs: Any) -> str:
        if action == "list":
            return await self._updater.list_skills()
        if action == "check":
            return await self._updater.check_updates(names)
        if action == "update":
            return await self._updater.update_skills(names, backup=backup)
        return f"Unknown action: {action!r}. Use 'list', 'check', or 'update'."
