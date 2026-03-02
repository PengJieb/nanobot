"""FastAPI web server for nanobot chat UI and skills dashboard."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.skills import SkillsLoader

STATIC_DIR = Path(__file__).parent / "static"


def create_app(agent: AgentLoop, skills_loader: SkillsLoader) -> FastAPI:
    """Create the FastAPI application with all routes."""
    app = FastAPI(title="nanobot web")

    # ------------------------------------------------------------------
    # Chat endpoints
    # ------------------------------------------------------------------

    @app.post("/api/chat/new")
    async def new_session():
        session_key = f"web:{uuid.uuid4().hex[:12]}"
        return {"session_key": session_key}

    @app.post("/api/chat")
    async def chat(request: Request):
        body = await request.json()
        message = (body.get("message") or "").strip()
        session_key = body.get("session_key") or f"web:{uuid.uuid4().hex[:12]}"

        if not message:
            raise HTTPException(status_code=400, detail="message is required")

        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def on_progress(content: str, *, tool_hint: bool = False) -> None:
            await queue.put({"type": "progress", "content": content, "tool_hint": tool_hint})

        async def _run():
            try:
                result = await agent.process_direct(
                    message,
                    session_key=session_key,
                    channel="web",
                    chat_id=session_key,
                    on_progress=on_progress,
                )
                await queue.put({"type": "done", "content": result or ""})
            except Exception as exc:
                await queue.put({"type": "error", "content": str(exc)})

        task = asyncio.create_task(_run())

        async def event_stream():
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120)
                except asyncio.TimeoutError:
                    yield "data: {\"type\": \"error\", \"content\": \"timeout\"}\n\n"
                    break
                import json as _json
                yield f"data: {_json.dumps(event)}\n\n"
                if event["type"] in ("done", "error"):
                    break
            await task

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ------------------------------------------------------------------
    # Skills endpoints
    # ------------------------------------------------------------------

    @app.get("/api/skills")
    async def list_skills():
        all_skills = skills_loader.list_skills(filter_unavailable=False)
        result = []
        for s in all_skills:
            meta = skills_loader.get_skill_metadata(s["name"]) or {}
            skill_meta = skills_loader._parse_nanobot_metadata(meta.get("metadata", ""))
            available = skills_loader._check_requirements(skill_meta)
            always_on = bool(skill_meta.get("always") or meta.get("always"))
            skill_dir = Path(s["path"]).parent
            has_logic = (skill_dir / "LOGIC.md").exists()
            result.append({
                "name": s["name"],
                "source": s["source"],
                "description": meta.get("description", s["name"]),
                "available": available,
                "always_on": always_on,
                "has_logic": has_logic,
            })
        return {"skills": result}

    @app.get("/api/skills/{name}")
    async def get_skill(name: str):
        content = skills_loader.load_skill(name)
        if content is None:
            raise HTTPException(status_code=404, detail="skill not found")

        meta = skills_loader.get_skill_metadata(name) or {}
        skill_meta = skills_loader._parse_nanobot_metadata(meta.get("metadata", ""))
        available = skills_loader._check_requirements(skill_meta)
        always_on = bool(skill_meta.get("always") or meta.get("always"))

        # Find skill dir to check LOGIC.md
        skill_dir = _find_skill_dir(skills_loader, name)
        logic_content = None
        if skill_dir and (skill_dir / "LOGIC.md").exists():
            logic_content = (skill_dir / "LOGIC.md").read_text(encoding="utf-8")

        return {
            "name": name,
            "description": meta.get("description", name),
            "source": _get_skill_source(skills_loader, name),
            "available": available,
            "always_on": always_on,
            "content": content,
            "logic": logic_content,
        }

    @app.post("/api/skills/{name}/generate-logic")
    async def generate_logic(name: str):
        skill_dir = _find_skill_dir(skills_loader, name)
        if skill_dir is None:
            raise HTTPException(status_code=404, detail="skill not found")

        skill_content = skills_loader.load_skill(name)
        if not skill_content:
            raise HTTPException(status_code=404, detail="skill not found")

        # Collect scripts in the skill directory
        scripts: list[str] = []
        for ext in ("*.py", "*.sh"):
            for f in skill_dir.rglob(ext):
                try:
                    text = f.read_text(encoding="utf-8")
                    scripts.append(f"### {f.name}\n```\n{text}\n```")
                except Exception:
                    pass

        prompt = (
            "Generate a LOGIC.md document for the following nanobot skill. "
            "The document should describe:\n"
            "1. **Entry Point** — how the skill is triggered\n"
            "2. **Flow** — step-by-step execution pipeline\n"
            "3. **Dependencies** — external tools or APIs needed\n\n"
            f"## SKILL.md\n```\n{skill_content}\n```\n\n"
        )
        if scripts:
            prompt += "## Scripts\n" + "\n\n".join(scripts) + "\n\n"
        prompt += (
            "Write ONLY the LOGIC.md content in markdown. "
            "Do not wrap in code fences."
        )

        result = await agent.process_direct(
            prompt,
            session_key=f"web:logic:{name}",
            channel="web",
            chat_id="system",
        )

        logic_path = skill_dir / "LOGIC.md"
        logic_path.write_text(result or "", encoding="utf-8")

        return {"logic": result or ""}

    # ------------------------------------------------------------------
    # Static files (must be last so API routes take precedence)
    # ------------------------------------------------------------------

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _find_skill_dir(loader: SkillsLoader, name: str) -> Path | None:
    """Return the directory for a skill, or None."""
    ws = loader.workspace_skills / name
    if ws.is_dir() and (ws / "SKILL.md").exists():
        return ws
    bi = loader.builtin_skills / name
    if bi.is_dir() and (bi / "SKILL.md").exists():
        return bi
    return None


def _get_skill_source(loader: SkillsLoader, name: str) -> str:
    ws = loader.workspace_skills / name
    if ws.is_dir() and (ws / "SKILL.md").exists():
        return "workspace"
    return "builtin"
