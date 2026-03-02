"""FastAPI web server for nanobot chat UI and skills dashboard."""

from __future__ import annotations

import asyncio
import json as _json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from nanobot.web.auth import AuthManager
from nanobot.web.pipeline import build_prompt, parse_logic_json
from nanobot.web.renderer import render_pipeline_html

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.skills import SkillsLoader

STATIC_DIR = Path(__file__).parent / "static"

_PUBLIC_PATHS = {"/api/auth/login", "/api/auth/register"}
_PUBLIC_PREFIXES = ("/login.html", "/style.css")


def create_app(
    agent: AgentLoop,
    skills_loader: SkillsLoader,
    auth: AuthManager | None = None,
) -> FastAPI:
    """Create the FastAPI application with all routes."""
    app = FastAPI(title="nanobot web")

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        if auth is None or path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)
        if path.startswith("/api/"):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not auth.verify_token(token):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    @app.post("/api/auth/register")
    async def register(request: Request):
        body = await request.json()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        invite_code = (body.get("invite_code") or "").strip()
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password required")
        if auth is None:
            return {"token": "no-auth", "username": username}
        token = auth.register(username, password, invite_code)
        if token is None:
            raise HTTPException(status_code=403, detail="invalid invite code or username taken")
        return {"token": token, "username": username}

    @app.post("/api/auth/login")
    async def login(request: Request):
        body = await request.json()
        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password required")
        if auth is None:
            return {"token": "no-auth", "username": username}
        token = auth.login(username, password)
        if token is None:
            raise HTTPException(status_code=401, detail="invalid username or password")
        return {"token": token, "username": username}

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    @app.post("/api/chat/new")
    async def new_session():
        return {"session_key": f"web:{uuid.uuid4().hex[:12]}"}

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
                    message, session_key=session_key, channel="web",
                    chat_id=session_key, on_progress=on_progress,
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
                    yield 'data: {"type": "error", "content": "timeout"}\n\n'
                    break
                yield f"data: {_json.dumps(event)}\n\n"
                if event["type"] in ("done", "error"):
                    break
            await task

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ------------------------------------------------------------------
    # Skills
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
            has_logic = (skill_dir / "LOGIC.json").exists()
            result.append({
                "name": s["name"], "source": s["source"],
                "description": meta.get("description", s["name"]),
                "available": available, "always_on": always_on, "has_logic": has_logic,
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
        skill_dir = _find_skill_dir(skills_loader, name)
        has_python = bool(skill_dir and list(skill_dir.rglob("*.py")))

        # Read cached LOGIC.json → render HTML via Python
        logic_html = None
        logic_json_path = skill_dir / "LOGIC.json" if skill_dir else None
        if logic_json_path and logic_json_path.exists():
            try:
                data = _json.loads(logic_json_path.read_text(encoding="utf-8"))
                logic_html = render_pipeline_html(data)
            except Exception:
                logic_html = None

        return {
            "name": name, "description": meta.get("description", name),
            "source": _get_skill_source(skills_loader, name),
            "available": available, "always_on": always_on,
            "content": content, "logic_html": logic_html,
            "has_logic": logic_html is not None, "has_python": has_python,
        }

    @app.post("/api/skills/{name}/generate-logic")
    async def generate_logic(name: str):
        """Use LLM to extract structured JSON, then render via Python."""
        skill_dir = _find_skill_dir(skills_loader, name)
        if skill_dir is None:
            raise HTTPException(status_code=404, detail="skill not found")
        skill_content = skills_loader.load_skill(name)
        if not skill_content:
            raise HTTPException(status_code=404, detail="skill not found")

        # Phase 1: LLM extracts structured JSON
        prompt = build_prompt(name, skill_content, skill_dir)
        raw = await agent.process_direct(
            prompt, session_key=f"web:logic:{name}", channel="web", chat_id="system",
        )

        data = parse_logic_json(raw)
        if data is None:
            raise HTTPException(status_code=500, detail="Failed to parse pipeline JSON from agent")

        # Cache the JSON
        json_path = skill_dir / "LOGIC.json"
        json_path.write_text(_json.dumps(data, indent=2), encoding="utf-8")

        # Phase 2: Python renders HTML from JSON
        html = render_pipeline_html(data)
        return {"logic_html": html}

    # ------------------------------------------------------------------
    # Static files
    # ------------------------------------------------------------------

    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


def _find_skill_dir(loader: SkillsLoader, name: str) -> Path | None:
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
