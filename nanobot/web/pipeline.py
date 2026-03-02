"""Build logic pipeline JSON from skill files — no LLM needed.

Analyzes SKILL.md content, Python AST, and shell scripts to produce
a structured pipeline with meaningful steps and decision branches.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

# Icon mapping: keyword → FA icon
_ICON_MAP = [
    ("cron", "fa-solid fa-clock"), ("schedul", "fa-solid fa-clock"),
    ("remind", "fa-solid fa-bell"), ("github", "fa-solid fa-code-branch"),
    ("git", "fa-solid fa-code-branch"), ("weather", "fa-solid fa-cloud-sun"),
    ("tmux", "fa-solid fa-terminal"), ("shell", "fa-solid fa-terminal"),
    ("exec", "fa-solid fa-terminal"), ("memory", "fa-solid fa-brain"),
    ("summar", "fa-solid fa-file-lines"), ("skill", "fa-solid fa-puzzle-piece"),
    ("web", "fa-solid fa-globe"), ("fetch", "fa-solid fa-globe"),
    ("search", "fa-solid fa-magnifying-glass"), ("message", "fa-solid fa-message"),
    ("chat", "fa-solid fa-comments"), ("email", "fa-solid fa-envelope"),
    ("file", "fa-solid fa-file"), ("write", "fa-solid fa-pen"),
    ("read", "fa-solid fa-book-open"), ("python", "fa-solid fa-code"),
    ("code", "fa-solid fa-code"), ("improv", "fa-solid fa-wand-magic-sparkles"),
    ("creat", "fa-solid fa-plus"), ("updat", "fa-solid fa-rotate"),
]


def build_pipeline(
    skill_name: str,
    skill_content: str,
    metadata: dict | None,
    skill_dir: Path,
) -> str:
    """Build pipeline JSON from skill files. Returns a JSON string."""
    meta = metadata or {}
    nanobot_meta = _parse_nanobot_meta(meta.get("metadata", ""))
    description = meta.get("description", skill_name)
    always_on = bool(nanobot_meta.get("always") or meta.get("always"))
    body = _strip_frontmatter(skill_content)

    icon = _pick_icon(skill_name, description)
    trigger = _detect_trigger(body, description, always_on)

    py_files = list(skill_dir.rglob("*.py"))
    sh_files = list(skill_dir.rglob("*.sh"))

    if py_files:
        steps, deps, class_design = _analyze_python(py_files, body)
    else:
        steps, deps = _analyze_content(body, sh_files)
        class_design = None

    # Merge deps from metadata requires
    for b in nanobot_meta.get("requires", {}).get("bins", []):
        if not any(d["name"] == b for d in deps):
            deps.append({"name": b, "description": "Required CLI tool"})
    for env in nanobot_meta.get("requires", {}).get("env", []):
        if not any(d["name"] == env for d in deps):
            deps.append({"name": env, "description": "Required environment variable"})

    # Ensure meaningful steps
    if len(steps) < 2:
        steps = _build_generic_steps(body, always_on, description)

    result: dict = {
        "entry_point": {"trigger": trigger, "icon": icon},
        "steps": steps,
        "dependencies": deps,
    }
    if class_design:
        result["class_design"] = class_design
    return json.dumps(result, indent=2)


# ------------------------------------------------------------------
# Trigger & icon detection
# ------------------------------------------------------------------

def _detect_trigger(body: str, description: str, always_on: bool) -> str:
    if always_on:
        return "Always-on: auto-injected into every agent conversation"
    tool_match = re.search(r'[Uu]se (?:the )?`(\w+)`\s+tool', body)
    if tool_match:
        return f"Activated when user needs the `{tool_match.group(1)}` tool"
    if re.search(r'```bash', body):
        return f"Triggered by user request: {description[:80]}"
    return f"Triggered by user request: {description[:80]}"


def _pick_icon(name: str, description: str) -> str:
    combined = (name + " " + description).lower()
    for kw, icon in _ICON_MAP:
        if kw in combined:
            return icon
    return "fa-solid fa-bolt"


# ------------------------------------------------------------------
# Python AST analysis
# ------------------------------------------------------------------

def _analyze_python(
    py_files: list[Path], body: str,
) -> tuple[list[dict], list[dict], dict | None]:
    steps: list[dict] = []
    deps: list[dict] = []
    class_design = None

    for f in py_files:
        try:
            source = f.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            continue

        # Collect imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _add_dep(deps, alias.name.split(".")[0], f.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                _add_dep(deps, node.module.split(".")[0], f.name)

        classes = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
        if not classes:
            continue

        cls = classes[0]
        init = None
        check_methods = []
        action_methods = []

        for item in cls.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name == "__init__":
                init = item
            elif item.name.startswith("_"):
                continue
            elif any(k in item.name.lower() for k in ("check", "valid", "verify", "can_", "is_", "has_")):
                check_methods.append(item)
            else:
                action_methods.append(item)

        # Step 1: Instantiation
        if init:
            params = [a.arg for a in init.args.args if a.arg != "self"]
            desc = f"Initialize with: {', '.join(params[:4])}" if params else "Create instance"
        else:
            desc = "Create instance"
        steps.append({"title": f"Create {cls.name}", "description": desc, "type": "action"})

        # Step 2: Validation (decision branch)
        for cm in check_methods[:1]:
            doc = _docstring(cm) or f"Run {cm.name}() validation"
            steps.append({
                "title": cm.name.replace("_", " ").title(),
                "description": doc,
                "type": "decision",
                "branches": {
                    "yes": {"label": "Passed", "steps": [
                        {"title": "Continue execution", "description": "Proceed to main logic", "type": "action"},
                    ]},
                    "no": {"label": "Failed", "steps": [
                        {"title": "Handle error", "description": "Return error or fallback", "type": "output"},
                    ]},
                },
            })

        # Step 3+: Public methods
        for m in action_methods[:5]:
            doc = _docstring(m) or m.name.replace("_", " ").capitalize()
            steps.append({"title": f"{m.name}()", "description": doc, "type": "action"})

        # Final: output
        steps.append({"title": "Return result", "description": f"Output from {cls.name}", "type": "output"})

        class_design = {
            "class_name": cls.name,
            "methods": [
                {"name": m.name, "description": _docstring(m) or m.name.replace("_", " ")}
                for m in (check_methods + action_methods)[:8]
            ],
        }
        break  # Process first class only

    return steps, deps, class_design


_STDLIB = {
    "os", "sys", "json", "re", "pathlib", "typing", "ast", "abc",
    "collections", "functools", "itertools", "dataclasses", "enum",
    "datetime", "time", "math", "hashlib", "secrets", "uuid",
    "shutil", "subprocess", "asyncio", "logging", "copy", "io",
    "contextlib", "unittest", "tempfile", "textwrap", "nanobot",
}


def _add_dep(deps: list[dict], mod: str, filename: str):
    if mod in _STDLIB or not mod:
        return
    if not any(d["name"] == mod for d in deps):
        deps.append({"name": mod, "description": f"Python library (from {filename})"})


def _docstring(node: ast.AST) -> str:
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        return node.body[0].value.value.strip()[:100]
    return ""


# ------------------------------------------------------------------
# Content-based analysis (markdown + optional shell scripts)
# ------------------------------------------------------------------

def _analyze_content(
    body: str, sh_files: list[Path],
) -> tuple[list[dict], list[dict]]:
    steps: list[dict] = []
    deps: list[dict] = []

    # 1) Extract tool call patterns: tool_name(action="xxx", ...)
    tool_actions: dict[str, list[dict]] = {}  # tool → [{action, full_call}]
    for match in re.finditer(r'(\w+)\(([^)]+)\)', body):
        name, args = match.group(1), match.group(2)
        if name[0].isupper() or len(name) < 2:
            continue
        action_m = re.search(r'action\s*=\s*["\'](\w+)', args)
        action = action_m.group(1) if action_m else None
        tool_actions.setdefault(name, []).append({
            "action": action,
            "call": f'{name}({args[:60]}{"..." if len(args) > 60 else ""})',
        })

    # 2) Build steps from tool calls
    for tool_name, calls in tool_actions.items():
        actions = {}
        for c in calls:
            key = c["action"] or "default"
            if key not in actions:
                actions[key] = c["call"]

        if len(actions) == 1:
            # Single action tool
            key = list(actions.keys())[0]
            steps.append({
                "title": f"Call {tool_name}",
                "description": actions[key],
                "type": "action",
            })
        else:
            # Multi-action tool → decision branch
            steps.append({
                "title": f"Receive {tool_name} request",
                "description": f"Parse user intent for {tool_name} operation",
                "type": "action",
            })
            branches = {}
            for act, call_str in list(actions.items())[:4]:
                branches[act] = {
                    "label": f"action = {act}",
                    "steps": [{"title": act.replace("_", " ").title(),
                               "description": call_str, "type": "action"}],
                }
            steps.append({
                "title": f"Route {tool_name} action",
                "description": f"Choose from: {', '.join(actions.keys())}",
                "type": "decision",
                "branches": branches,
            })

    # 3) Extract bash commands and deps
    bash_cmds: list[str] = []
    for block in re.findall(r'```(?:bash|sh)?\n(.*?)```', body, re.DOTALL):
        for line in block.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("$"):
                continue
            cmd = line.split()[0] if line.split() else ""
            if cmd in {"curl", "wget", "jq", "gh", "git", "tmux", "npm", "node",
                        "python3", "docker", "kubectl", "aws", "gcloud"}:
                if cmd not in bash_cmds:
                    bash_cmds.append(cmd)
                    deps.append({"name": cmd, "description": "CLI tool used in skill"})

    # 4) Shell script analysis
    for f in sh_files:
        try:
            source = f.read_text(encoding="utf-8")
        except Exception:
            continue
        purpose = _shell_purpose(source, f.name)
        steps.append({"title": f"Run {f.name}", "description": purpose, "type": "action"})
        for line in source.split("\n"):
            cmd = line.strip().split()[0] if line.strip().split() else ""
            if cmd in {"curl", "wget", "jq", "gh", "git", "tmux", "grep", "awk", "sed"}:
                if not any(d["name"] == cmd for d in deps):
                    deps.append({"name": cmd, "description": f"Used in {f.name}"})

    # 5) If no tool calls found, extract workflow from section structure
    if not steps:
        steps = _extract_workflow_from_sections(body)

    # 6) Ensure output step
    if steps and steps[-1].get("type") != "output":
        steps.append({"title": "Return result", "description": "Send response to user", "type": "output"})

    return steps, deps


def _shell_purpose(source: str, filename: str) -> str:
    for line in source.split("\n"):
        line = line.strip()
        if line.startswith("#!"):
            continue
        if line.startswith("#"):
            comment = line.lstrip("# ").strip()
            if len(comment) > 5:
                return comment[:80]
    return f"Execute {filename}"


def _extract_workflow_from_sections(body: str) -> list[dict]:
    """Extract meaningful steps from markdown sections."""
    steps = []
    sections = re.split(r'^##\s+(.+)$', body, flags=re.MULTILINE)

    # sections = [pre, title1, body1, title2, body2, ...]
    i = 1
    while i < len(sections) - 1:
        title = sections[i].strip()
        sec_body = sections[i + 1]
        i += 2

        # Skip generic sections
        if title.lower() in {"about", "overview", "introduction", "notes"}:
            continue

        # Extract first meaningful sentence from section body
        desc = _first_sentence(sec_body)

        # Check if section describes multiple options (numbered list or sub-headings)
        options = re.findall(r'^\d+\.\s+\*\*(.+?)\*\*\s*[-–—]\s*(.+)', sec_body, re.MULTILINE)
        if len(options) >= 2:
            branches = {}
            for opt_title, opt_desc in options[:3]:
                key = opt_title.strip().lower().replace(" ", "_")[:20]
                branches[key] = {
                    "label": opt_title.strip(),
                    "steps": [{"title": opt_title.strip()[:40],
                               "description": opt_desc.strip()[:80], "type": "action"}],
                }
            steps.append({
                "title": title[:50],
                "description": desc,
                "type": "decision",
                "branches": branches,
            })
        else:
            steps.append({"title": title[:50], "description": desc, "type": "action"})

        if len(steps) >= 7:
            break

    return steps


def _first_sentence(text: str) -> str:
    """Extract first meaningful sentence from markdown text."""
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("```") or line.startswith("|") or line.startswith("-"):
            continue
        # Clean markdown formatting
        clean = re.sub(r'[`*_\[\]]', '', line).strip()
        if len(clean) > 10:
            return clean[:100]
    return ""


# ------------------------------------------------------------------
# Generic fallback steps
# ------------------------------------------------------------------

def _build_generic_steps(body: str, always_on: bool, description: str) -> list[dict]:
    steps = []
    if always_on:
        steps.append({
            "title": "Inject skill context",
            "description": "Skill instructions loaded into agent system prompt automatically",
            "type": "action",
        })
    steps.append({
        "title": "Receive user request",
        "description": f"User asks: {description[:60]}",
        "type": "action",
    })
    # Check if body mentions conditions/modes
    mode_match = re.findall(r'\d+\.\s+\*\*(.+?)\*\*', body)
    if len(mode_match) >= 2:
        branches = {}
        for m in mode_match[:3]:
            key = m.strip().lower().replace(" ", "_")[:20]
            branches[key] = {
                "label": m.strip(),
                "steps": [{"title": m.strip()[:40], "description": f"Execute {m.strip().lower()} workflow", "type": "action"}],
            }
        steps.append({
            "title": "Select mode",
            "description": f"Choose from: {', '.join(m.strip() for m in mode_match[:3])}",
            "type": "decision",
            "branches": branches,
        })
    else:
        steps.append({
            "title": "Process request",
            "description": "Follow skill instructions to execute the task",
            "type": "action",
        })
    steps.append({
        "title": "Return response",
        "description": "Send result back to user",
        "type": "output",
    })
    return steps


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        m = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
        if m:
            return content[m.end():]
    return content


def _parse_nanobot_meta(raw: str) -> dict:
    try:
        data = json.loads(raw)
        return data.get("nanobot", data.get("openclaw", {})) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
