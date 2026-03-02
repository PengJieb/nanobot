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

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.skills import SkillsLoader

STATIC_DIR = Path(__file__).parent / "static"

# Paths that do NOT require authentication
_PUBLIC_PATHS = {"/api/auth/login", "/api/auth/register"}
_PUBLIC_PREFIXES = ("/login.html", "/style.css")


def create_app(
    agent: AgentLoop,
    skills_loader: SkillsLoader,
    auth: AuthManager | None = None,
) -> FastAPI:
    """Create the FastAPI application with all routes."""
    app = FastAPI(title="nanobot web")

    # ------------------------------------------------------------------
    # Auth middleware
    # ------------------------------------------------------------------

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path

        # Public paths — always allowed
        if auth is None or path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        # Static assets at root that aren't pages (css/js) — allow
        # Let login.html and API auth endpoints through; block everything else
        if path.startswith("/api/"):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            if not auth.verify_token(token):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        else:
            # For HTML pages (except login.html), let the browser load them.
            # The JS on each page will check auth and redirect to login if needed.
            pass

        return await call_next(request)

    # ------------------------------------------------------------------
    # Auth endpoints
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
            # No auth configured — registration is a no-op, return a dummy token
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
                    yield 'data: {"type": "error", "content": "timeout"}\n\n'
                    break
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
