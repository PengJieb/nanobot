"""Pydantic models for the Application builder module."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# App specification — produced by the agent
# ---------------------------------------------------------------------------


class ComponentLayout(BaseModel):
    row: int = 0
    col: int = 0
    col_span: int = Field(12, alias="colSpan")
    row_span: int = Field(1, alias="rowSpan")

    model_config = {"populate_by_name": True}


class ComponentEvent(BaseModel):
    """A single event handler (click, change, submit, …)."""
    type: str = "local"           # "local" | "agent"
    local_code: str = ""          # JS snippet executed client-side
    agent_prompt: str = ""        # Prompt template sent to the agent
    result_bind: str = ""         # State variable to store the agent response


class AppComponent(BaseModel):
    id: str
    type: str                     # heading|text|input|textarea|select|button|
                                  # checkbox|slider|table|chart|card|divider|image
    label: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    layout: ComponentLayout = Field(default_factory=ComponentLayout)
    bind: str = ""                # State variable name
    events: dict[str, ComponentEvent] = Field(default_factory=dict)


class StateVariable(BaseModel):
    name: str
    type: str = "string"          # string|number|boolean|array|object
    default: Any = None


class AppLayout(BaseModel):
    type: str = "single-page"     # single-page|dashboard|wizard
    theme: str = "dark"


class AppState(BaseModel):
    variables: list[StateVariable] = Field(default_factory=list)


class AppSpec(BaseModel):
    """Full specification of a generated application."""
    id: str
    title: str
    description: str = ""
    version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.now)
    layout: AppLayout = Field(default_factory=AppLayout)
    state: AppState = Field(default_factory=AppState)
    components: list[AppComponent] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


# ---------------------------------------------------------------------------
# Build session — tracks the Q&A flow before generation
# ---------------------------------------------------------------------------

QUESTIONS: list[str] = [
    "What is the name of your application?",
    "What is its main goal — what problem does it solve?",
    "Who will use it, and what tasks should they perform?",
    "What data will it handle? (e.g. text input, numbers, files, web data, API responses)",
    "What are the core user actions? (e.g. submit forms, click buttons, explore data, run queries)",
    "What outputs should the application display? (e.g. tables, charts, text answers, images)",
    "Should it remember data between interactions? If yes, what information should persist?",
    "What layout style do you prefer? (simple form, dashboard with panels, step-by-step wizard)",
    "Which features need AI assistance? (e.g. generating content, answering questions, analyzing data)",
    "Any extra requirements or constraints? (specific inputs, styling preferences, integrations, etc.)",
]


class BuildSession(BaseModel):
    """In-memory session tracking answers to the 10 questions."""
    session_id: str
    answers: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def current_question_index(self) -> int:
        return len(self.answers)

    @property
    def current_question(self) -> str | None:
        idx = self.current_question_index
        return QUESTIONS[idx] if idx < len(QUESTIONS) else None

    @property
    def is_complete(self) -> bool:
        return len(self.answers) >= len(QUESTIONS)

    def add_answer(self, answer: str) -> None:
        self.answers.append(answer)

    def build_requirements_text(self) -> str:
        lines = []
        for i, (q, a) in enumerate(zip(QUESTIONS, self.answers), 1):
            lines.append(f"Q{i}. {q}")
            lines.append(f"A{i}. {a}")
            lines.append("")
        return "\n".join(lines)
