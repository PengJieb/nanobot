"""AppBuilder — manages build sessions and generates app specs via the agent."""

from __future__ import annotations

import json
import random
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from nanobot.app.schema import AppComponent, AppLayout, AppSpec, AppState, BuildSession, StateVariable
from nanobot.app.manager import AppManager

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop

# Directory holding color theme JSON files alongside the JPEG palette images
_COLOR_THEME_DIR = Path(__file__).parents[2] / "assert" / "color_theme"


_COLOR_SECTION = """\

## Color Theme

Apply the following color palette to give the app a distinctive visual identity.
Palette name: **{palette_name}** — {palette_desc}

Colors:
{color_list}

Instructions:
- Use these colors for card `color` values (map to nearest: blue/purple/teal/rose/amber)
- Populate the `theme_colors` object in your JSON output with CSS custom properties using \
exact hex values from the palette. Choose the best mapping:
  - `--app-primary`       → button backgrounds and primary accent
  - `--app-primary-hover` → slightly darker hover state for buttons
  - `--app-surface`       → card / panel background color
  - `--app-border`        → border color
  - `--app-text`          → main body text color
  - `--app-heading`       → heading / title text color
  - `--app-text-muted`    → muted label / subtitle text
  - `--app-input-bg`      → input / textarea background
  - `--app-result-bg`     → result box / output area background
  - `--app-accent`        → secondary accent color
- Set `"color": "{palette_name}"` in the output JSON
- Use the darkest palette colors for backgrounds, mid-tones for surfaces/borders, \
brightest colors for headings and key numbers
"""

_GENERATION_PROMPT = """\
CRITICAL: Your response must be PURE JSON ONLY. Do not include markdown code blocks, \
explanations, or any text before or after the JSON object. Start with {{ and end with }}.

You are an expert UI/UX designer and frontend developer.
Based on the user's application requirements below, generate a complete JSON specification \
for an interactive web application.

## User Requirements

{requirements}{color_section}

## Output Format

Output ONLY the JSON object below. NO markdown fences (```), NO explanatory text.
Use this exact structure:

{{
  "title": "Application title",
  "description": "What this application does in one sentence",
  "color": "",
  "theme_colors": {{}},
  "layout": {{
    "type": "single-page",
    "theme": "dark"
  }},
  "state": {{
    "variables": [
      {{"name": "inputText", "type": "string", "default": ""}},
      {{"name": "results", "type": "array", "default": []}}
    ]
  }},
  "components": [
    {{
      "id": "heading-1",
      "type": "heading",
      "label": "My App",
      "properties": {{"level": 1, "text": "My App Title"}},
      "layout": {{"row": 0, "col": 0, "colSpan": 12}},
      "bind": "",
      "events": {{}}
    }},
    {{
      "id": "input-1",
      "type": "input",
      "label": "Your Question",
      "properties": {{"placeholder": "Enter something...", "inputType": "text"}},
      "layout": {{"row": 1, "col": 0, "colSpan": 9}},
      "bind": "inputText",
      "events": {{}}
    }},
    {{
      "id": "btn-submit",
      "type": "button",
      "label": "Submit",
      "properties": {{"variant": "primary"}},
      "layout": {{"row": 1, "col": 9, "colSpan": 3}},
      "bind": "",
      "events": {{
        "click": {{
          "type": "agent",
          "agent_prompt": "Answer this question: {{{{state.inputText}}}}",
          "result_bind": "results",
          "local_code": ""
        }}
      }}
    }},
    {{
      "id": "card-action",
      "type": "card",
      "label": "",
      "properties": {{"title": "Quick Action", "body": "Click to run analysis", "icon": "fa-solid fa-bolt", "color": "blue"}},
      "layout": {{"row": 2, "col": 0, "colSpan": 4}},
      "bind": "",
      "events": {{
        "click": {{
          "type": "local",
          "local_code": "setState('inputText', 'Run analysis')",
          "agent_prompt": "",
          "result_bind": ""
        }}
      }}
    }},
    {{
      "id": "results-1",
      "type": "text",
      "label": "Results",
      "properties": {{"content": "Results will appear here"}},
      "layout": {{"row": 2, "col": 0, "colSpan": 12}},
      "bind": "results",
      "events": {{}}
    }}
  ]
}}

## Component Types & Their Properties

**Every component type supports an `events` object** — not just buttons. \
Any component can be clicked, hovered, or interacted with to trigger local logic or agent calls. \
Use this to make cards, stat tiles, table rows, chart bars, images, and text blocks interactive.

- **heading**: `{{"level": 1-3, "text": "Title"}}`
- **text**: `{{"content": "Static or bound text"}}` — if `bind` is set, shows state value; \
  add `events.click` to make the text block a clickable trigger
- **input**: `{{"placeholder": "...", "inputType": "text|number|email|password"}}`
- **textarea**: `{{"placeholder": "...", "rows": 4}}`
- **select**: `{{"options": [{{"value": "v", "label": "L"}}]}}`
- **button**: `{{"variant": "primary|secondary|danger"}}` — the canonical click trigger, \
  but any other component can serve the same role via `events.click`
- **checkbox**: `{{"checked_label": "Enabled", "unchecked_label": "Disabled"}}`
- **slider**: `{{"min": 0, "max": 100, "step": 1}}`
- **table**: `{{"columns": [{{"key": "col", "label": "Column Header"}}]}}` — bind to array state var; \
  supports rich sub-element interaction (see Table Interaction below)
- **chart**: `{{"chart_type": "bar|line|pie", "x_key": "label", "y_key": "value"}}` — bind to array; \
  `events.click` fires when a data point is clicked, with `context.label` and `context.value`
- **card**: `{{"title": "Card title", "body": "Card body text", "icon": "fa-solid fa-<name>", \
  "color": "blue|purple|teal|rose|amber"}}` — ideal clickable tile; add `events.click` to make it \
  a navigation or selection trigger
- **stat**: `{{"number": "98%", "stat_label": "...", "description": "...", \
  "color": "blue|purple|teal|rose|amber"}}` — large-number highlight; add `events.click` to drill down
- **image**: `{{"src": "url"}}` — add `events.click` to make images interactive
- **divider**: no properties needed

## Table Interaction Properties

Tables support richer interaction beyond the whole-table `events.click`:

- `"row_clickable": true` — rows get a hover highlight and pointer cursor
- `"row_click_bind": "selectedRow"` — clicking a row stores the full row object into this state var
- `"cell_click_bind": "selectedCell"` — clicking a cell stores `{{rowIndex, colKey, value, rowData}}`
- `"cell_editable": true` — clicking a cell opens an inline text input; \
  on Enter/blur the value is saved back into the bound array state var
- `"editable_columns": ["name", "price"]` — optional whitelist; only these columns are editable

Table event names (in addition to `"click"` on the whole table):
- `"row_click"` — fires per row; receives `context.rowData` and `context.rowIndex`
- `"cell_click"` — fires per cell; receives `context.value`, `context.colKey`, \
  `context.rowIndex`, `context.rowData`

## Event Types

All components support `events`. Common event names: `"click"`, `"change"`, `"submit"`. \
Table extras: `"row_click"`, `"cell_click"`.

- **local**: `"local_code"` is a JS snippet. Available variables: \
  `state` (full state object), `setState(name, value)`, `getState(name)`, \
  `event` (DOM event), `value` (shortcut for event.target.value), \
  `context` (sub-element context — see below).
- **agent**: `"agent_prompt"` is a template. Use `{{{{state.varName}}}}` to interpolate state \
  and `{{{{context.field}}}}` to interpolate sub-element context. \
  `"result_bind"` names the state variable to store the agent response.

### The `context` object

`context` is populated automatically for sub-element events and chart clicks:

| Event | context fields |
|-------|---------------|
| `row_click` | `context.rowData` (object), `context.rowIndex` |
| `cell_click` | `context.value`, `context.colKey`, `context.rowIndex`, `context.rowData` |
| chart `click` | `context.label`, `context.value`, `context.dataIndex` |
| all others | `context` is `{{}}` — use `state.*` for data |

Example — card click populates a form field:
```
"events": {{"click": {{"type": "local", "local_code": "setState('query', 'topic A')"}}}}
```
Example — table row click feeds an agent prompt:
```
"events": {{"row_click": {{"type": "agent",
  "agent_prompt": "Summarise this record: {{{{context.rowData}}}}",
  "result_bind": "rowSummary", "local_code": ""}}}}
```

## Layout Rules

- `colSpan` values: 12=full, 6=half, 4=thirds, 3=quarter, 9+3=3/4+1/4
- `row` starts at 0 and increments; components on the same row share it
- `col` starts at 0; multiple components on the same row start at different columns
- For dashboard layout, use side-by-side panels with `colSpan` 6 or 4

## Design Rules

- Always start with a heading component (row 0)
- Use `layout.type = "dashboard"` for complex multi-panel apps, `"single-page"` otherwise
- Use `layout.theme = "light"` for informational/report pages (white background, color-accented cards); use `"dark"` for tool/productivity apps
- For light-theme dashboard pages, prefer **card** and **stat** components with `color` set to one of: blue, purple, teal, rose, amber
- **Any component can be interactive** — prefer agent events for AI-driven features; local events for simple UI state changes
- Use `events.click` on cards and stat tiles to act as selection or navigation triggers instead of buttons
- For tables: use `row_clickable` + `row_click_bind` to drive detail panels; use `cell_editable` for in-place editing
- For charts: `events.click` fires with the clicked data point's label and value in `context`
- For tables and charts, always bind to an array state variable
- `agent_prompt` template variables use double curly braces: `{{{{state.varName}}}}`, `{{{{context.field}}}}`
- Keep the app focused; 4–12 components is typical
- State variable names must be camelCase with no spaces
"""


class AppBuilder:
    """
    Manages the 10-question build flow and triggers app spec generation.
    """

    # In-memory sessions (keyed by session_id). Sessions are short-lived.
    _sessions: dict[str, BuildSession] = {}

    @classmethod
    def start_session(cls) -> BuildSession:
        session = BuildSession(session_id=uuid.uuid4().hex[:16])
        cls._sessions[session.session_id] = session
        return session

    @classmethod
    def get_session(cls, session_id: str) -> BuildSession | None:
        return cls._sessions.get(session_id)

    @classmethod
    def answer(cls, session_id: str, answer: str) -> BuildSession | None:
        session = cls._sessions.get(session_id)
        if session is None:
            return None
        if not session.is_complete:
            session.add_answer(answer.strip())
        return session

    @classmethod
    def discard_session(cls, session_id: str) -> None:
        cls._sessions.pop(session_id, None)

    @classmethod
    async def generate(
        cls,
        session: BuildSession,
        agent: AgentLoop,
        app_manager: AppManager,
    ) -> AppSpec:
        """Ask the agent to produce an AppSpec from the completed Q&A."""
        requirements = session.build_requirements_text()
        color_section = _build_color_section()
        prompt = _GENERATION_PROMPT.format(requirements=requirements, color_section=color_section)

        raw = await agent.process_direct(
            prompt,
            session_key=f"app:build:{session.session_id}",
            channel="web",
            chat_id="app-builder",
        )

        spec = _parse_spec(raw or "", app_manager.new_id())
        spec.requirements = requirements
        app_manager.save(spec)
        cls.discard_session(session.session_id)
        return spec

    @classmethod
    async def regenerate(
        cls,
        app_id: str,
        feedback: str,
        agent: AgentLoop,
        app_manager: AppManager,
    ) -> AppSpec:
        """Regenerate an app based on user feedback."""
        spec = app_manager.get(app_id)
        if spec is None:
            raise ValueError("App not found")

        color_section = _build_color_section()
        prompt = _GENERATION_PROMPT.format(
            requirements=f"{spec.requirements}\n\n## User Feedback\n\n{feedback}",
            color_section=color_section,
        )

        raw = await agent.process_direct(
            prompt,
            session_key=f"app:improve:{app_id}",
            channel="web",
            chat_id="app-builder",
        )

        new_spec = _parse_spec(raw or "", app_id)
        new_spec.requirements = spec.requirements
        app_manager.save(new_spec)
        return new_spec


# ---------------------------------------------------------------------------
# Color theme helpers
# ---------------------------------------------------------------------------


def _pick_random_palette() -> dict | None:
    """Return a random color palette dict from assert/color_theme/*.json, or None."""
    if not _COLOR_THEME_DIR.is_dir():
        return None
    palette_files = list(_COLOR_THEME_DIR.glob("*.json"))
    if not palette_files:
        return None
    chosen = random.choice(palette_files)
    try:
        return json.loads(chosen.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_color_section() -> str:
    """Build the color section string to inject into the generation prompt."""
    palette = _pick_random_palette()
    if not palette:
        return ""
    color_list = "\n".join(
        f"  - {c['hex']} ({c['name']}): {c['role']}"
        for c in palette.get("colors", [])
    )
    return _COLOR_SECTION.format(
        palette_name=palette.get("name", "Custom Palette"),
        palette_desc=palette.get("description", ""),
        color_list=color_list,
    )


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


def _extract_json_object(text: str) -> dict | None:
    """Extract the first valid JSON object from text, trying each '{' position."""
    pos = 0
    while True:
        start = text.find("{", pos)
        if start == -1:
            return None

        brace_count = 0
        end = -1
        in_string = False
        escape_next = False

        for i in range(start, len(text)):
            char = text[i]
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = i
                        break

        if end == -1:
            return None

        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pos = start + 1


def _parse_spec(raw: str, app_id: str) -> AppSpec:
    """Parse agent output into an AppSpec, with fallback on failure."""
    text = raw.strip()

    # Try to extract from a markdown code block anywhere in the text
    fence = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()

    data = _extract_json_object(text)
    if data is None:
        return _fallback_spec(app_id, "Generated App", "Could not parse spec from agent response.")

    # Normalise component layouts (agent may omit colSpan alias)
    for comp in data.get("components", []):
        layout = comp.get("layout", {})
        if "colSpan" not in layout and "col_span" not in layout:
            layout["colSpan"] = 12
        comp["layout"] = layout
        # Normalise event sub-objects
        events = comp.get("events", {})
        for ev_name, ev in list(events.items()):
            if isinstance(ev, dict):
                ev.setdefault("type", "local")
                ev.setdefault("local_code", "")
                ev.setdefault("agent_prompt", "")
                ev.setdefault("result_bind", "")

    data["id"] = app_id
    data.setdefault("version", "1.0")

    try:
        return AppSpec.model_validate(data)
    except Exception:
        return _fallback_spec(app_id, data.get("title", "App"), "Spec validation failed.")


def _fallback_spec(app_id: str, title: str, description: str) -> AppSpec:
    return AppSpec(
        id=app_id,
        title=title,
        description=description,
        layout=AppLayout(type="single-page"),
        state=AppState(variables=[StateVariable(name="message", type="string", default="")]),
        components=[
            AppComponent(
                id="heading-1",
                type="heading",
                label=title,
                properties={"level": 1, "text": title},
            ),
            AppComponent(
                id="error-text",
                type="text",
                label="",
                properties={"content": description},
            ),
        ],
    )
