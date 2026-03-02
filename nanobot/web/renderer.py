"""Render pipeline JSON into HTML cards — server-side, no JS needed.

Reads all available fields from the LOGIC.json structure and produces
styled HTML using the card/timeline/gradient visual language.
"""

from __future__ import annotations

from html import escape as _esc

# Color palette (dark theme, rgba for backgrounds)
_C = {
    "blue":   {"bg": "rgba(59,130,246,0.08)",  "bd": "rgba(59,130,246,0.2)",  "ic": "#3b82f6", "dot": "#3b82f6"},
    "teal":   {"bg": "rgba(20,184,166,0.08)",   "bd": "rgba(20,184,166,0.2)",  "ic": "#14b8a6", "dot": "#14b8a6"},
    "purple": {"bg": "rgba(139,92,246,0.08)",    "bd": "rgba(139,92,246,0.2)",  "ic": "#8b5cf6", "dot": "#8b5cf6"},
    "amber":  {"bg": "rgba(245,158,11,0.08)",    "bd": "rgba(245,158,11,0.2)",  "ic": "#f59e0b", "dot": "#f59e0b"},
    "rose":   {"bg": "rgba(244,63,94,0.08)",     "bd": "rgba(244,63,94,0.2)",   "ic": "#f43f5e", "dot": "#f43f5e"},
    "gray":   {"bg": "rgba(107,114,128,0.08)",   "bd": "rgba(107,114,128,0.2)", "ic": "#6b7280", "dot": "#6b7280"},
}

_STEP_ICONS = {
    "action": "fa-solid fa-gear",
    "decision": "fa-solid fa-code-branch",
    "output": "fa-solid fa-flag-checkered",
    "input": "fa-solid fa-right-to-bracket",
}

_BADGE_STYLES = {
    "action": "background:rgba(20,184,166,0.18);color:#5eead4",
    "decision": "background:rgba(245,158,11,0.18);color:#fcd34d",
    "output": "background:rgba(16,185,129,0.18);color:#6ee7b7",
    "input": "background:rgba(59,130,246,0.18);color:#93c5fd",
    "cli": "background:rgba(107,114,128,0.18);color:#d1d5db",
    "python": "background:rgba(16,185,129,0.18);color:#6ee7b7",
    "env": "background:rgba(245,158,11,0.18);color:#fcd34d",
    "api": "background:rgba(139,92,246,0.18);color:#c4b5fd",
}


def render_pipeline_html(data: dict) -> str:
    """Render a complete pipeline JSON into an HTML string."""
    parts: list[str] = []

    # Summary card
    summary = data.get("summary", "")
    if summary:
        parts.append(_card("blue", "fa-solid fa-circle-info", "Overview",
                           f'<p style="color:#d1d5db">{_esc(summary)}</p>'))

    # Entry point card
    ep = data.get("entry_point", {})
    if ep:
        icon = ep.get("icon", "fa-solid fa-bolt")
        trigger_type = ep.get("trigger_type", "")
        body = f'<p style="color:#d1d5db">{_esc(ep.get("trigger", ""))}</p>'
        if trigger_type:
            body += f'<div style="margin-top:0.5rem">{_badge(trigger_type, _BADGE_STYLES.get("input", ""))}</div>'
        parts.append(_card("blue", icon, "Entry Point", body))

    # Pipeline steps
    steps = data.get("steps", [])
    if steps:
        inner = _render_steps(steps, depth=0)
        parts.append(_card("teal", "fa-solid fa-diagram-project", "Pipeline", inner))

    # Dependencies
    deps = data.get("dependencies", [])
    if deps:
        parts.append(_card("purple", "fa-solid fa-puzzle-piece", "Dependencies",
                           _render_deps(deps)))

    # Class design
    cls = data.get("class_design")
    if cls and cls.get("class_name"):
        parts.append(_card("amber", "fa-solid fa-code", "Class Design",
                           _render_class(cls)))

    # Error handling
    errors = data.get("error_handling", [])
    if errors:
        parts.append(_card("rose", "fa-solid fa-triangle-exclamation", "Error Handling",
                           _render_errors(errors)))

    return "\n".join(parts)


# ------------------------------------------------------------------
# Steps renderer (recursive for branches)
# ------------------------------------------------------------------

def _render_steps(steps: list[dict], depth: int) -> str:
    colors = [_C["teal"], _C["amber"], _C["rose"]]
    c = colors[min(depth, len(colors) - 1)]
    line_color = c["bd"]
    dot_color = c["dot"]

    ml = "margin-left:1rem;" if depth == 0 else "margin-left:1.5rem;"
    h = f'<div class="relative" style="{ml}">'
    h += f'<div class="absolute top-0 bottom-0 w-0.5" style="left:13px;background:{line_color}"></div>'

    for i, s in enumerate(steps):
        step_type = s.get("type", "action")
        icon = _STEP_ICONS.get(step_type, _STEP_ICONS["action"])

        h += '<div class="flex items-start mb-5 relative">'
        # Numbered dot
        h += (f'<div class="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center '
              f'text-white text-xs font-bold z-10" style="background:{dot_color}">{i + 1}</div>')
        h += '<div class="ml-4 flex-1">'

        # Title + type badge
        h += '<div class="flex items-center gap-2 flex-wrap">'
        h += f'<i class="{icon} text-sm" style="color:{dot_color}"></i>'
        h += f'<span class="font-semibold text-gray-100">{_esc(s.get("title", ""))}</span>'
        if step_type in _BADGE_STYLES:
            h += _badge(step_type, _BADGE_STYLES[step_type])
        h += '</div>'

        # Description
        desc = s.get("description", "")
        if desc:
            h += f'<p class="text-sm text-gray-400 mt-0.5">{_esc(desc)}</p>'

        # Collapsible details + code snippet
        details = s.get("details", [])
        snippet = s.get("code_snippet", "")
        if details or snippet:
            h += ('<details class="step-expand" style="margin-top:0.4rem">'
                  '<summary style="cursor:pointer;color:#6b7280;font-size:0.75rem;'
                  'user-select:none;list-style:none;display:flex;align-items:center;gap:0.3rem">'
                  '<i class="fa-solid fa-plus expand-icon" style="font-size:0.6rem;transition:transform 0.15s"></i>'
                  ' details</summary>')
            if details:
                h += '<ul style="margin:0.4rem 0 0 1rem;padding:0;list-style:disc">'
                for d in details:
                    h += f'<li style="color:#9ca3af;font-size:0.8rem;margin:0.15rem 0">{_esc(d)}</li>'
                h += '</ul>'
            if snippet:
                h += ('<pre style="background:#0f172a;border-radius:0.5rem;padding:0.6rem 0.8rem;'
                      'margin-top:0.5rem;overflow-x:auto;font-size:0.78rem;color:#94a3b8">'
                      f'<code>{_esc(snippet)}</code></pre>')
            h += '</details>'

        # Decision branches
        branches = s.get("branches")
        if branches and isinstance(branches, dict):
            h += '<div style="margin-top:0.75rem;display:flex;flex-direction:column;gap:0.6rem">'
            branch_colors = {
                "yes": _C["teal"], "no": _C["rose"], "true": _C["teal"], "false": _C["rose"],
            }
            for bk, bv in branches.items():
                if not isinstance(bv, dict):
                    continue
                bc = branch_colors.get(bk.lower(), _C["amber"])
                b_icon = "fa-solid fa-check" if bk.lower() in ("yes", "true") else (
                    "fa-solid fa-xmark" if bk.lower() in ("no", "false") else "fa-solid fa-arrow-right"
                )
                h += (f'<div style="background:{bc["bg"]};border:1px solid {bc["bd"]};'
                      f'border-radius:0.75rem;padding:0.75rem 1rem">')
                h += '<div class="flex items-center gap-2 mb-2">'
                h += f'<i class="{b_icon}" style="color:{bc["ic"]}"></i>'
                h += f'<span class="font-semibold text-sm" style="color:{bc["ic"]}">{_esc(bk.upper())}</span>'
                label = bv.get("label", "")
                if label:
                    h += f'<span style="color:#9ca3af;font-size:0.75rem">{_esc(label)}</span>'
                h += '</div>'
                sub_steps = bv.get("steps", [])
                if sub_steps:
                    h += _render_steps(sub_steps, depth + 1)
                h += '</div>'
            h += '</div>'

        h += '</div></div>'

    h += '</div>'
    return h


# ------------------------------------------------------------------
# Dependencies renderer
# ------------------------------------------------------------------

def _render_deps(deps: list[dict]) -> str:
    h = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:0.5rem">'
    for d in deps:
        dep_type = d.get("type", "")
        h += ('<div style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.15);'
              'border-radius:0.5rem;padding:0.75rem">')
        h += '<div class="flex items-center gap-2">'
        h += f'<span class="font-semibold text-sm text-gray-200">{_esc(d.get("name", ""))}</span>'
        if dep_type:
            h += _badge(dep_type, _BADGE_STYLES.get(dep_type, _BADGE_STYLES["cli"]))
        h += '</div>'
        desc = d.get("description", "")
        if desc:
            h += f'<div style="color:#9ca3af;font-size:0.75rem;margin-top:0.25rem">{_esc(desc)}</div>'
        h += '</div>'
    h += '</div>'
    return h


# ------------------------------------------------------------------
# Class design renderer
# ------------------------------------------------------------------

def _render_class(cls: dict) -> str:
    h = ''
    purpose = cls.get("purpose", "")
    h += f'<div class="mb-3"><span class="font-mono" style="color:#fcd34d;font-size:0.9rem">class {_esc(cls["class_name"])}</span>'
    if purpose:
        h += f'<span style="color:#9ca3af;font-size:0.8rem;margin-left:0.5rem">— {_esc(purpose)}</span>'
    h += '</div>'

    params = cls.get("constructor_params", [])
    if params:
        h += '<div style="margin-bottom:0.75rem">'
        h += '<div style="color:#9ca3af;font-size:0.75rem;margin-bottom:0.25rem">Constructor</div>'
        h += (f'<pre style="background:#0f172a;border-radius:0.5rem;padding:0.5rem 0.75rem;'
              f'font-size:0.78rem;color:#94a3b8;margin:0">'
              f'<code>__init__({_esc(", ".join(params))})</code></pre>')
        h += '</div>'

    methods = cls.get("methods", [])
    if methods:
        h += '<div style="display:flex;flex-direction:column;gap:0.35rem">'
        for m in methods:
            h += ('<div class="flex items-start gap-2 rounded-lg" '
                  'style="background:rgba(245,158,11,0.06);padding:0.5rem 0.6rem">')
            h += '<i class="fa-solid fa-terminal text-xs mt-1" style="color:#f59e0b"></i>'
            h += '<div>'
            sig = m.get("signature", m.get("name", "") + "()")
            h += f'<span class="font-mono text-sm text-gray-200">{_esc(sig)}</span>'
            desc = m.get("description", "")
            if desc:
                h += f'<div style="color:#9ca3af;font-size:0.75rem">{_esc(desc)}</div>'
            h += '</div></div>'
        h += '</div>'

    return h


# ------------------------------------------------------------------
# Error handling renderer
# ------------------------------------------------------------------

def _render_errors(errors: list[dict]) -> str:
    h = '<div style="display:flex;flex-direction:column;gap:0.4rem">'
    for e in errors:
        h += ('<div style="background:rgba(244,63,94,0.06);border:1px solid rgba(244,63,94,0.12);'
              'border-radius:0.5rem;padding:0.6rem 0.75rem">')
        h += '<div class="flex items-start gap-2">'
        h += '<i class="fa-solid fa-circle-exclamation text-xs mt-1" style="color:#f43f5e"></i>'
        h += '<div>'
        h += f'<span class="font-semibold text-sm text-gray-200">{_esc(e.get("condition", ""))}</span>'
        action = e.get("action", "")
        if action:
            h += f'<div style="color:#9ca3af;font-size:0.75rem">{_esc(action)}</div>'
        h += '</div></div></div>'
    h += '</div>'
    return h


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _card(color: str, icon: str, title: str, body: str) -> str:
    c = _C.get(color, _C["blue"])
    return (
        f'<div class="pipe-card" style="background:{c["bg"]};border:1px solid {c["bd"]};'
        f'border-radius:1rem;padding:1.5rem;margin-bottom:1rem">'
        f'<div class="flex items-center mb-3">'
        f'<i class="{_esc(icon)} text-xl mr-3" style="color:{c["ic"]}"></i>'
        f'<h3 class="text-lg font-bold text-gray-100">{_esc(title)}</h3>'
        f'</div>{body}</div>'
    )


def _badge(text: str, style: str) -> str:
    return (
        f'<span style="display:inline-block;font-size:0.65rem;font-weight:500;'
        f'padding:1px 7px;border-radius:9999px;{style}">{_esc(text)}</span>'
    )
