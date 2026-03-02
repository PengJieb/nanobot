"""Build the LLM prompt for extracting structured pipeline JSON from a skill."""

from __future__ import annotations

import json
import re
from pathlib import Path

_SCHEMA = """\
{
  "summary": "2-3 sentence overview of what this skill does",
  "entry_point": {
    "trigger": "how the skill is activated (one sentence)",
    "trigger_type": "always-on | tool-call | user-message",
    "icon": "fa-solid fa-<icon-name>"
  },
  "steps": [
    {
      "title": "short step title",
      "description": "what happens in this step",
      "type": "action | decision | output | input",
      "details": ["optional bullet point 1", "optional bullet point 2"],
      "code_snippet": "optional: key code example for this step",
      "branches": {
        "branch_label_1": {
          "label": "when this branch is taken",
          "steps": [<nested steps, same schema>]
        }
      }
    }
  ],
  "dependencies": [
    {"name": "tool/library", "type": "cli | python | env | api", "description": "purpose"}
  ],
  "class_design": {
    "class_name": "PrimaryClassName",
    "purpose": "what the class does",
    "constructor_params": ["param1: type", "param2: type"],
    "methods": [
      {"name": "method_name", "signature": "method_name(args) -> return", "description": "purpose"}
    ]
  },
  "error_handling": [
    {"condition": "when this error occurs", "action": "what the skill does"}
  ]
}\
"""

_PROMPT_TEMPLATE = """\
Analyze the following nanobot skill thoroughly and extract a detailed structured \
JSON representation of its logic pipeline.

## SKILL.md
```
{skill_content}
```
{scripts_section}
Output ONLY valid JSON matching this schema (no markdown fences, no extra text):

{schema}

Rules:
- summary: 2-3 sentences capturing the skill's purpose and key capabilities
- steps: 5-10 items covering the COMPLETE execution flow from trigger to output
- Use type="decision" for ANY conditional logic, with branches for each path
- decision branches: use descriptive keys (not just yes/no), each with label + sub-steps
- details: 2-4 bullet points per step explaining specifics, parameters, or edge cases
- code_snippet: include the most relevant code example for steps that execute commands
- dependencies: list ALL external requirements with their type
- class_design: describe the primary class structure (real if Python exists, hypothetical otherwise)
- error_handling: list 2-4 error scenarios and how they are handled
- icon: choose a Font Awesome 6 solid icon that best represents the skill
- Keep descriptions informative but concise\
"""


def build_prompt(skill_name: str, skill_content: str, skill_dir: Path) -> str:
    """Build the LLM prompt for extracting pipeline JSON."""
    scripts_section = ""
    script_parts: list[str] = []
    for ext in ("*.py", "*.sh"):
        for f in skill_dir.rglob(ext):
            try:
                text = f.read_text(encoding="utf-8")
                script_parts.append(f"### {f.relative_to(skill_dir)}\n```\n{text}\n```")
            except Exception:
                pass

    if script_parts:
        scripts_section = "\n\n## Scripts\n" + "\n\n".join(script_parts) + "\n"

    return _PROMPT_TEMPLATE.format(
        skill_content=skill_content,
        scripts_section=scripts_section,
        schema=_SCHEMA,
    )


def parse_logic_json(raw: str) -> dict | None:
    """Parse LLM output into a pipeline dict, tolerating markdown fences."""
    if not raw:
        return None
    cleaned = raw.strip()
    cleaned = re.sub(r'^```json?\s*\n?', '', cleaned)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
