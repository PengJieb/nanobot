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
    from nanobot.app.manager import AppManager

STATIC_DIR = Path(__file__).parent / "static"

# Paths that do NOT require authentication
_PUBLIC_PATHS = {"/api/auth/login", "/api/auth/register"}
_PUBLIC_PREFIXES = ("/login.html", "/style.css")

# Prompt for skills WITH existing Python code
_LOGIC_PROMPT_WITH_CODE = (
    "Analyze the following nanobot skill and its code. Output a JSON object "
    "describing the logic pipeline. Respond with ONLY valid JSON — no markdown "
    "fences, no extra text.\n\n"
    "## SKILL.md\n```\n{skill_content}\n```\n\n"
    "## Python / Shell Scripts\n{scripts_section}\n\n"
    'Output this exact JSON structure:\n'
    '{{\n'
    '  "entry_point": {{\n'
    '    "trigger": "how the skill is triggered (one sentence)",\n'
    '    "icon": "fa-solid fa-<icon-name>"\n'
    '  }},\n'
    '  "steps": [\n'
    '    {{\n'
    '      "title": "short step title (3-6 words)",\n'
    '      "description": "what happens in this step (one sentence)",\n'
    '      "type": "action"\n'
    '    }}\n'
    '  ],\n'
    '  "dependencies": [\n'
    '    {{"name": "tool or library", "description": "what it is used for"}}\n'
    '  ]\n'
    '}}\n\n'
    "Rules:\n"
    "- steps: 4-8 items covering the real execution flow\n"
    '- step type: "action", "decision", or "output"\n'
    "- icon: a Font Awesome 6 solid icon name relevant to the entry point\n"
    "- dependencies: list all external tools, libraries, CLI binaries, APIs, env vars\n"
    "- Keep all text concise"
)

# Prompt for skills WITHOUT Python code
_LOGIC_PROMPT_NO_CODE = (
    "Analyze the following nanobot skill. It has NO Python implementation — "
    "it is a markdown-only skill. Describe its execution logic. Output a JSON "
    "object. Respond with ONLY valid JSON — no markdown fences, no extra text.\n\n"
    "## SKILL.md\n```\n{skill_content}\n```\n\n"
    'Output this exact JSON structure:\n'
    '{{\n'
    '  "entry_point": {{\n'
    '    "trigger": "how the skill is triggered (one sentence)",\n'
    '    "icon": "fa-solid fa-<icon-name>"\n'
    '  }},\n'
    '  "steps": [\n'
    '    {{\n'
    '      "title": "short step title (3-6 words)",\n'
    '      "description": "what happens in this step (one sentence)",\n'
    '      "type": "action"\n'
    '    }}\n'
    '  ],\n'
    '  "dependencies": [\n'
    '    {{"name": "tool or library", "description": "what it is used for"}}\n'
    '  ],\n'
    '  "class_design": {{\n'
    '    "class_name": "HypotheticalClassName",\n'
    '    "methods": [\n'
    '      {{"name": "method_name", "description": "what it does"}}\n'
    '    ]\n'
    '  }}\n'
    '}}\n\n'
    "Rules:\n"
    "- steps: 4-8 items covering the real execution flow\n"
    '- step type: "action", "decision", or "output"\n'
    "- icon: a Font Awesome 6 solid icon name relevant to the entry point\n"
    "- dependencies: list all external tools, libraries, CLI binaries, APIs, env vars\n"
    "- class_design: reconstruct how this skill WOULD be implemented as a Python class\n"
    "- Keep all text concise"
)


def create_app(
    agent: AgentLoop,
    skills_loader: SkillsLoader,
    auth: AuthManager | None = None,
    app_manager: AppManager | None = None,
) -> FastAPI:
    """Create the FastAPI application with all routes."""
    app = FastAPI(title="nanobot web")

    # ------------------------------------------------------------------
    # Auth middleware
    # ------------------------------------------------------------------

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
            return {"token": "no-auth", "username": username, "role": "admin"}

        token = auth.login(username, password)
        if token is None:
            raise HTTPException(status_code=401, detail="invalid username or password")
        role = auth.get_user_role(token) or "normal"
        return {"token": token, "username": username, "role": role}

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

        # Check for app construct command first
        lower_msg = message.lower()
        if lower_msg == "#app" or lower_msg.startswith("#app "):
            raise HTTPException(
                status_code=400,
                detail="Please use the App Builder interface to create applications"
            )

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
    async def list_skills(request: Request):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        user_role = auth.get_user_role(token) if auth else "admin"

        all_skills = skills_loader.list_skills(filter_unavailable=False)
        result = []
        for s in all_skills:
            if user_role == "normal" and s["source"] == "builtin":
                continue
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

        has_python = bool(skill_dir and list(skill_dir.rglob("*.py")))

        return {
            "name": name,
            "description": meta.get("description", name),
            "source": _get_skill_source(skills_loader, name),
            "available": available,
            "always_on": always_on,
            "content": content,
            "logic": logic_content,
            "has_python": has_python,
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

        has_code = bool(scripts)

        if has_code:
            prompt = _LOGIC_PROMPT_WITH_CODE.format(
                skill_content=skill_content,
                scripts_section="\n\n".join(scripts),
            )
        else:
            prompt = _LOGIC_PROMPT_NO_CODE.format(
                skill_content=skill_content,
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

    @app.delete("/api/skills/{name}")
    async def delete_skill(name: str, request: Request):
        import shutil
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        user_role = auth.get_user_role(token) if auth else "admin"

        skill_dir = _find_skill_dir(skills_loader, name)
        if skill_dir is None:
            raise HTTPException(status_code=404, detail="skill not found")

        source = _get_skill_source(skills_loader, name)
        if source == "builtin" and user_role != "admin":
            raise HTTPException(status_code=403, detail="only admin can delete builtin skills")

        try:
            shutil.rmtree(skill_dir)
            return {"status": "deleted"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"failed to delete: {str(e)}")

    # ------------------------------------------------------------------
    # Application builder endpoints
    # ------------------------------------------------------------------

    if app_manager is not None:
        from nanobot.app.builder import AppBuilder
        from nanobot.app.schema import QUESTIONS

        @app.post("/api/app/build/start")
        async def app_build_start():
            session = AppBuilder.start_session()
            return {
                "session_id": session.session_id,
                "question_index": 0,
                "question": session.current_question,
                "total_questions": len(QUESTIONS),
            }

        @app.post("/api/app/build/{session_id}/answer")
        async def app_build_answer(session_id: str, request: Request):
            body = await request.json()
            answer = (body.get("answer") or "").strip()
            if not answer:
                raise HTTPException(status_code=400, detail="answer is required")

            session = AppBuilder.answer(session_id, answer)
            if session is None:
                raise HTTPException(status_code=404, detail="session not found")

            if session.is_complete:
                return {"status": "complete", "session_id": session_id}

            return {
                "status": "continue",
                "question_index": session.current_question_index,
                "question": session.current_question,
                "total_questions": len(QUESTIONS),
            }

        @app.post("/api/app/build/{session_id}/generate")
        async def app_build_generate(session_id: str):
            session = AppBuilder.get_session(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="session not found")
            if not session.is_complete:
                raise HTTPException(status_code=400, detail="not all questions answered")

            queue: asyncio.Queue[dict] = asyncio.Queue()

            async def _run():
                try:
                    spec = await AppBuilder.generate(session, agent, app_manager)
                    await queue.put({"type": "done", "app_id": spec.id, "title": spec.title})
                except Exception as exc:
                    await queue.put({"type": "error", "content": str(exc)})

            task = asyncio.create_task(_run())

            async def _stream():
                await queue.put({"type": "progress", "content": "Designing your application..."})
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

            return StreamingResponse(_stream(), media_type="text/event-stream")

        @app.get("/api/apps")
        async def list_apps():
            return {"apps": app_manager.list_apps()}

        @app.get("/api/app/{app_id}")
        async def get_app(app_id: str):
            spec = app_manager.get(app_id)
            if spec is None:
                raise HTTPException(status_code=404, detail="app not found")
            return spec.to_dict()

        @app.delete("/api/app/{app_id}")
        async def delete_app(app_id: str):
            if not app_manager.delete(app_id):
                raise HTTPException(status_code=404, detail="app not found")
            return {"status": "deleted"}

        @app.post("/api/app/{app_id}/action")
        async def app_action(app_id: str, request: Request):
            """Handle an agent event triggered by the app viewer."""
            spec = app_manager.get(app_id)
            if spec is None:
                raise HTTPException(status_code=404, detail="app not found")

            body = await request.json()
            prompt = (body.get("prompt") or "").strip()
            if not prompt:
                raise HTTPException(status_code=400, detail="prompt is required")

            queue: asyncio.Queue[dict] = asyncio.Queue()

            async def _run():
                try:
                    result = await agent.process_direct(
                        prompt,
                        session_key=f"app:{app_id}",
                        channel="web",
                        chat_id=f"app-{app_id}",
                    )
                    await queue.put({"type": "done", "content": result or ""})
                except Exception as exc:
                    await queue.put({"type": "error", "content": str(exc)})

            task = asyncio.create_task(_run())

            async def _stream():
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

            return StreamingResponse(_stream(), media_type="text/event-stream")

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
