"""Build logic pipeline JSON from skill files — no LLM needed."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

# Icon mapping: keyword in skill name/description → FA icon
_ICON_MAP = [
    ("cron", "fa-solid fa-clock"),
    ("schedul", "fa-solid fa-clock"),
    ("remind", "fa-solid fa-bell"),
    ("github", "fa-solid fa-code-branch"),
    ("git", "fa-solid fa-code-branch"),
    ("weather", "fa-solid fa-cloud-sun"),
    ("tmux", "fa-solid fa-terminal"),
    ("shell", "fa-solid fa-terminal"),
    ("exec", "fa-solid fa-terminal"),
    ("memory", "fa-solid fa-brain"),
    ("summar", "fa-solid fa-file-lines"),
    ("skill", "fa-solid fa-puzzle-piece"),
    ("web", "fa-solid fa-globe"),
    ("fetch", "fa-solid fa-globe"),
    ("search", "fa-solid fa-magnifying-glass"),
    ("message", "fa-solid fa-message"),
    ("chat", "fa-solid fa-comments"),
    ("email", "fa-solid fa-envelope"),
    ("file", "fa-solid fa-file"),
    ("write", "fa-solid fa-pen"),
    ("read", "fa-solid fa-book-open"),
    ("python", "fa-solid fa-code"),
    ("code", "fa-solid fa-code"),
    ("improv", "fa-solid fa-wand-magic-sparkles"),
    ("creat", "fa-solid fa-plus"),
    ("updat", "fa-solid fa-rotate"),
]

_DEFAULT_ICON = "fa-solid fa-bolt"


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

    # Detect entry point
    always_on = bool(nanobot_meta.get("always") or meta.get("always"))
    trigger = _detect_trigger(skill_content, always_on)
    icon = _pick_icon(skill_name, description)

    # Collect scripts
    py_files = list(skill_dir.rglob("*.py"))
    sh_files = list(skill_dir.rglob("*.sh"))

    # Build steps
    steps: list[dict] = []
    deps: list[dict] = []
    class_design = None

    if py_files:
        # Analyze Python code via AST
        steps, deps, class_design = _analyze_python(py_files, skill_content)
    elif sh_files:
        steps, deps = _analyze_shell(sh_files, skill_content)
    else:
        # Markdown-only: parse sections and code blocks
        steps, deps = _analyze_markdown(skill_content)

    # Extract dependencies from metadata requires
    requires = nanobot_meta.get("requires", {})
    for b in requires.get("bins", []):
        if not any(d["name"] == b for d in deps):
            deps.append({"name": b, "description": "Required CLI tool"})
    for env in requires.get("env", []):
        if not any(d["name"] == env for d in deps):
            deps.append({"name": env, "description": "Required environment variable"})

    # Ensure at least some steps
    if not steps:
        steps = _fallback_steps(skill_content, always_on)

    pipeline = {
        "entry_point": {"trigger": trigger, "icon": icon},
        "steps": steps,
        "dependencies": deps,
    }
    if class_design:
        pipeline["class_design"] = class_design

    return json.dumps(pipeline, indent=2)


# ------------------------------------------------------------------
# Entry point detection
# ------------------------------------------------------------------


def _detect_trigger(content: str, always_on: bool) -> str:
    lower = content.lower()
    if always_on:
        return "Always-on skill, auto-injected into agent context"

    # Check for tool references
    tool_match = re.search(r'(?:use the |use )`(\w+)`\s+tool', lower)
    if tool_match:
        return f"User triggers via the `{tool_match.group(1)}` tool call"

    # Check for CLI commands
    if "```bash" in lower or "```sh" in lower:
        return "User requests a task that requires shell commands"

    return "User message matching skill description"


def _pick_icon(name: str, description: str) -> str:
    combined = (name + " " + description).lower()
    for keyword, icon in _ICON_MAP:
        if keyword in combined:
            return icon
    return _DEFAULT_ICON


# ------------------------------------------------------------------
# Python analysis
# ------------------------------------------------------------------


def _analyze_python(
    py_files: list[Path], skill_content: str
) -> tuple[list[dict], list[dict], dict | None]:
    steps = []
    deps = []
    class_design = None

    for f in py_files:
        try:
            source = f.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            continue

        # Extract imports as dependencies
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod not in {"os", "sys", "json", "re", "pathlib", "typing", "ast"}:
                        if not any(d["name"] == mod for d in deps):
                            deps.append({"name": mod, "description": f"Python library ({f.name})"})
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.split(".")[0]
                if mod not in {"os", "sys", "json", "re", "pathlib", "typing", "ast", "nanobot"}:
                    if not any(d["name"] == mod for d in deps):
                        deps.append({"name": mod, "description": f"Python library ({f.name})"})

        # Extract classes
        classes = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
        if classes:
            primary = classes[0]
            init_method = None
            public_methods = []
            for item in primary.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name == "__init__":
                        init_method = item
                    elif not item.name.startswith("_"):
                        public_methods.append(item)

            # Build steps from class structure
            steps.append({
                "title": f"Instantiate {primary.name}",
                "description": f"Create {primary.name} instance from {f.name}",
                "type": "action",
            })

            if init_method:
                params = [a.arg for a in init_method.args.args if a.arg != "self"]
                if params:
                    steps.append({
                        "title": "Configure parameters",
                        "description": f"Set up: {', '.join(params[:5])}",
                        "type": "action",
                    })

            # Add decision if there's a method with "check" or "validate" in name
            check_methods = [m for m in public_methods if any(
                k in m.name.lower() for k in ("check", "valid", "verify", "can_", "is_", "has_")
            )]
            other_methods = [m for m in public_methods if m not in check_methods]

            if check_methods:
                cm = check_methods[0]
                doc = _get_ast_docstring(cm) or f"Validate via {cm.name}()"
                steps.append({
                    "title": f"Check: {cm.name}()",
                    "description": doc,
                    "type": "decision",
                    "branches": {
                        "yes": {
                            "label": "Validation passed",
                            "steps": [{"title": "Proceed with execution",
                                        "description": "Continue to main logic",
                                        "type": "action"}],
                        },
                        "no": {
                            "label": "Validation failed",
                            "steps": [{"title": "Return error",
                                        "description": "Report issue to user",
                                        "type": "output"}],
                        },
                    },
                })

            for m in other_methods[:4]:
                doc = _get_ast_docstring(m) or f"Execute {m.name}"
                steps.append({
                    "title": f"Call {m.name}()",
                    "description": doc,
                    "type": "action",
                })

            steps.append({
                "title": "Return result",
                "description": f"Output from {primary.name}",
                "type": "output",
            })

            # Build class_design
            class_design = {
                "class_name": primary.name,
                "methods": [
                    {"name": m.name, "description": _get_ast_docstring(m) or ""}
                    for m in public_methods[:8]
                ],
            }

    # If no class found, just show file-level steps
    if not steps:
        for f in py_files:
            steps.append({
                "title": f"Execute {f.name}",
                "description": f"Run Python script {f.name}",
                "type": "action",
            })
        steps.append({"title": "Return result", "description": "Script output", "type": "output"})

    return steps, deps, class_design


def _get_ast_docstring(node: ast.AST) -> str:
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ):
        doc = node.body[0].value.value.strip()
        # Truncate long docstrings
        return doc[:100] if len(doc) > 100 else doc
    return ""


# ------------------------------------------------------------------
# Shell script analysis
# ------------------------------------------------------------------


def _analyze_shell(
    sh_files: list[Path], skill_content: str
) -> tuple[list[dict], list[dict]]:
    steps = []
    deps = []

    for f in sh_files:
        try:
            source = f.read_text(encoding="utf-8")
        except Exception:
            continue

        steps.append({
            "title": f"Run {f.name}",
            "description": _extract_shell_purpose(source, f.name),
            "type": "action",
        })

        # Extract commands used
        for line in source.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cmd = line.split()[0] if line.split() else ""
            if cmd in {"curl", "wget", "jq", "grep", "awk", "sed", "tmux", "gh", "git", "npm", "node", "python3", "python"}:
                if not any(d["name"] == cmd for d in deps):
                    deps.append({"name": cmd, "description": f"Used in {f.name}"})

    # Add markdown-derived steps too
    md_steps, md_deps = _analyze_markdown(skill_content)
    # Only add markdown steps if shell didn't produce enough
    if len(steps) < 3:
        steps.extend(md_steps)
    deps.extend(d for d in md_deps if not any(x["name"] == d["name"] for x in deps))

    if steps and steps[-1]["type"] != "output":
        steps.append({"title": "Return output", "description": "Script results", "type": "output"})

    return steps, deps


def _extract_shell_purpose(source: str, filename: str) -> str:
    """Extract purpose from first comment block."""
    for line in source.split("\n"):
        line = line.strip()
        if line.startswith("#!"):
            continue
        if line.startswith("#"):
            comment = line.lstrip("# ").strip()
            if comment and len(comment) > 5:
                return comment[:80]
    return f"Execute {filename}"


# ------------------------------------------------------------------
# Markdown-only analysis
# ------------------------------------------------------------------


def _analyze_markdown(skill_content: str) -> tuple[list[dict], list[dict]]:
    steps = []
    deps = []
    body = _strip_frontmatter(skill_content)

    # Extract sections (## headings)
    sections = re.split(r'^##\s+', body, flags=re.MULTILINE)

    # Extract tool calls from code blocks
    tool_calls = re.findall(r'(\w+)\(([^)]*)\)', body)
    seen_tools = set()
    for name, args in tool_calls:
        if name not in seen_tools and name[0].islower() and len(name) > 2:
            seen_tools.add(name)
            # Extract action param if present
            action_match = re.search(r'action\s*=\s*["\'](\w+)', args)
            desc = f'{name}(action="{action_match.group(1)}")' if action_match else f'{name}({args[:40]})'
            steps.append({
                "title": f"Call {name} tool",
                "description": desc,
                "type": "action",
            })

    # Extract bash commands from code blocks
    bash_blocks = re.findall(r'```(?:bash|sh)?\n(.*?)```', body, re.DOTALL)
    seen_cmds = set()
    for block in bash_blocks:
        for line in block.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cmd = line.split()[0] if line.split() else ""
            if cmd and cmd not in seen_cmds and not cmd.startswith("$") and not cmd.startswith("{"):
                seen_cmds.add(cmd)
                if cmd in {"curl", "wget", "gh", "git", "tmux", "npm", "node", "python3", "docker"}:
                    if not any(d["name"] == cmd for d in deps):
                        deps.append({"name": cmd, "description": "CLI tool used in examples"})

    # If we found tool calls, add decision step for multi-action tools
    if len(seen_tools) == 1 and len(tool_calls) > 2:
        tool_name = list(seen_tools)[0]
        actions = set()
        for name, args in tool_calls:
            if name == tool_name:
                m = re.search(r'action\s*=\s*["\'](\w+)', args)
                if m:
                    actions.add(m.group(1))
        if len(actions) >= 2:
            action_list = sorted(actions)
            branches = {}
            for a in action_list[:2]:
                branches[a] = {
                    "label": f"action={a}",
                    "steps": [{"title": f"Execute {a}", "description": f"{tool_name}(action=\"{a}\")", "type": "action"}],
                }
            # Insert decision before the tool-call steps
            decision = {
                "title": f"Select {tool_name} action",
                "description": "User specifies which action to perform",
                "type": "decision",
                "branches": branches,
            }
            steps = [steps[0]] + [decision] + steps[1:] if steps else [decision]

    # Parse section headings as additional context
    if not steps and len(sections) > 1:
        for sec in sections[1:6]:
            title = sec.split("\n")[0].strip()
            if title:
                steps.append({
                    "title": title[:50],
                    "description": f"Section: {title}",
                    "type": "action",
                })

    return steps, deps


# ------------------------------------------------------------------
# Fallback
# ------------------------------------------------------------------


def _fallback_steps(content: str, always_on: bool) -> list[dict]:
    steps = []
    if always_on:
        steps.append({
            "title": "Inject into context",
            "description": "Skill content loaded into agent system prompt",
            "type": "action",
        })
    steps.append({
        "title": "Receive user request",
        "description": "Agent receives message matching skill triggers",
        "type": "action",
    })
    steps.append({
        "title": "Process request",
        "description": "Agent follows skill instructions to handle the task",
        "type": "action",
    })
    steps.append({
        "title": "Return response",
        "description": "Agent sends result back to user",
        "type": "output",
    })
    return steps


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _strip_frontmatter(content: str) -> str:
    if content.startswith("---"):
        match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
        if match:
            return content[match.end():]
    return content


def _parse_nanobot_meta(raw: str) -> dict:
    try:
        data = json.loads(raw)
        return data.get("nanobot", data.get("openclaw", {})) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
