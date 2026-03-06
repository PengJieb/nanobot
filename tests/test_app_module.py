"""Tests for the nanobot/app/ module: AppManager, BuildSession, AppBuilder, _parse_spec.

Potential bugs targeted:
- AppManager.get silently returns None for corrupted files (no logging)
- AppBuilder._sessions is a class-level variable shared across tests (cleanup required)
- _parse_spec fallback when agent returns surrounding text or malformed JSON
- BuildSession.current_question returns None when is_complete (boundary)
- add_answer after is_complete is blocked only at AppBuilder.answer level
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from nanobot.app.manager import AppManager
from nanobot.app.schema import (
    AppComponent,
    AppLayout,
    AppSpec,
    AppState,
    BuildSession,
    ComponentLayout,
    QUESTIONS,
    StateVariable,
)
from nanobot.app.builder import AppBuilder, _parse_spec, _fallback_spec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(app_id: str = "abc123def456", title: str = "Test App") -> AppSpec:
    return AppSpec(
        id=app_id,
        title=title,
        description="A test application",
        layout=AppLayout(type="single-page", theme="dark"),
        state=AppState(variables=[StateVariable(name="query", type="string", default="")]),
        components=[
            AppComponent(
                id="heading-1",
                type="heading",
                label="Test",
                properties={"level": 1, "text": "Test App"},
                layout=ComponentLayout(row=0, col=0, col_span=12),
            )
        ],
    )


# ---------------------------------------------------------------------------
# AppManager
# ---------------------------------------------------------------------------


class TestAppManager:
    def test_save_and_get_roundtrip(self, tmp_path: Path) -> None:
        manager = AppManager(tmp_path)
        spec = _make_spec()
        manager.save(spec)

        loaded = manager.get(spec.id)
        assert loaded is not None
        assert loaded.id == spec.id
        assert loaded.title == spec.title
        assert loaded.description == spec.description

    def test_get_returns_none_for_missing_id(self, tmp_path: Path) -> None:
        manager = AppManager(tmp_path)
        assert manager.get("nonexistent") is None

    def test_get_returns_none_for_corrupted_json(self, tmp_path: Path) -> None:
        """Corrupted JSON files are silently ignored and return None."""
        manager = AppManager(tmp_path)
        bad_file = manager._dir / "badapp.json"
        bad_file.write_text("this is not valid json", encoding="utf-8")

        # Should return None, not raise
        result = manager.get("badapp")
        assert result is None

    def test_get_returns_none_for_invalid_spec(self, tmp_path: Path) -> None:
        """A valid JSON file that doesn't match AppSpec schema returns None."""
        manager = AppManager(tmp_path)
        bad_file = manager._dir / "badspec.json"
        bad_file.write_text(json.dumps({"not_an_app": True}), encoding="utf-8")

        result = manager.get("badspec")
        assert result is None

    def test_delete_existing_app(self, tmp_path: Path) -> None:
        manager = AppManager(tmp_path)
        spec = _make_spec()
        manager.save(spec)

        result = manager.delete(spec.id)
        assert result is True
        assert manager.get(spec.id) is None

    def test_delete_nonexistent_app(self, tmp_path: Path) -> None:
        manager = AppManager(tmp_path)
        assert manager.delete("no-such-id") is False

    def test_list_apps_empty(self, tmp_path: Path) -> None:
        manager = AppManager(tmp_path)
        assert manager.list_apps() == []

    def test_list_apps_returns_summaries(self, tmp_path: Path) -> None:
        manager = AppManager(tmp_path)
        spec1 = _make_spec("aaa111bbb222", "First App")
        spec2 = _make_spec("ccc333ddd444", "Second App")
        manager.save(spec1)
        manager.save(spec2)

        apps = manager.list_apps()
        assert len(apps) == 2
        ids = {a["id"] for a in apps}
        assert "aaa111bbb222" in ids
        assert "ccc333ddd444" in ids

    def test_list_apps_fields(self, tmp_path: Path) -> None:
        manager = AppManager(tmp_path)
        spec = _make_spec()
        manager.save(spec)

        apps = manager.list_apps()
        assert len(apps) == 1
        app = apps[0]
        assert "id" in app
        assert "title" in app
        assert "description" in app
        assert "created_at" in app
        assert "layout_type" in app
        assert "component_count" in app
        assert app["component_count"] == 1
        assert app["layout_type"] == "single-page"

    def test_list_apps_skips_corrupted_files(self, tmp_path: Path) -> None:
        """Corrupted JSON files are silently skipped in list_apps."""
        manager = AppManager(tmp_path)
        spec = _make_spec()
        manager.save(spec)
        bad_file = manager._dir / "corrupt.json"
        bad_file.write_text("{bad json", encoding="utf-8")

        apps = manager.list_apps()
        assert len(apps) == 1  # Only valid app appears

    def test_new_id_generates_12_char_hex(self, tmp_path: Path) -> None:
        app_id = AppManager.new_id()
        assert len(app_id) == 12
        int(app_id, 16)  # Must be valid hex

    def test_new_id_is_unique(self, tmp_path: Path) -> None:
        ids = {AppManager.new_id() for _ in range(20)}
        assert len(ids) == 20  # All unique


# ---------------------------------------------------------------------------
# BuildSession
# ---------------------------------------------------------------------------


class TestBuildSession:
    def test_initial_state(self) -> None:
        session = BuildSession(session_id="test123")
        assert session.current_question_index == 0
        assert session.current_question == QUESTIONS[0]
        assert not session.is_complete
        assert session.answers == []

    def test_add_answer_advances_index(self) -> None:
        session = BuildSession(session_id="test123")
        session.add_answer("My App")
        assert session.current_question_index == 1
        assert session.current_question == QUESTIONS[1]

    def test_is_complete_after_all_answers(self) -> None:
        session = BuildSession(session_id="test123")
        for i in range(len(QUESTIONS)):
            assert not session.is_complete
            session.add_answer(f"Answer {i}")
        assert session.is_complete

    def test_current_question_returns_none_when_complete(self) -> None:
        session = BuildSession(session_id="test123")
        for i in range(len(QUESTIONS)):
            session.add_answer(f"Answer {i}")
        assert session.is_complete
        assert session.current_question is None

    def test_add_answer_beyond_complete_still_appends(self) -> None:
        """BuildSession.add_answer has no is_complete guard; that guard lives in AppBuilder."""
        session = BuildSession(session_id="test123")
        for i in range(len(QUESTIONS)):
            session.add_answer(f"Answer {i}")
        # Direct call to add_answer (bypassing AppBuilder) can still add extras
        session.add_answer("extra")
        assert len(session.answers) == len(QUESTIONS) + 1

    def test_build_requirements_text_format(self) -> None:
        session = BuildSession(session_id="test123")
        for i in range(len(QUESTIONS)):
            session.add_answer(f"Answer{i}")

        text = session.build_requirements_text()
        # Check first Q&A pair
        assert "Q1." in text
        assert QUESTIONS[0] in text
        assert "A1. Answer0" in text
        # Check last Q&A pair
        assert f"Q{len(QUESTIONS)}." in text
        assert f"A{len(QUESTIONS)}. Answer{len(QUESTIONS) - 1}" in text


# ---------------------------------------------------------------------------
# AppBuilder (class-level session store)
# ---------------------------------------------------------------------------


class TestAppBuilder:
    """Tests for AppBuilder class methods.

    IMPORTANT: AppBuilder._sessions is a class-level dict shared across all tests
    in this process. Each test must explicitly discard sessions to avoid leaking
    state into subsequent tests.
    """

    def test_start_session_creates_new_session(self) -> None:
        session = AppBuilder.start_session()
        try:
            assert session.session_id
            assert AppBuilder.get_session(session.session_id) is session
        finally:
            AppBuilder.discard_session(session.session_id)

    def test_get_session_returns_none_for_unknown_id(self) -> None:
        result = AppBuilder.get_session("no-such-session-id-xyz")
        assert result is None

    def test_answer_adds_to_session(self) -> None:
        session = AppBuilder.start_session()
        sid = session.session_id
        try:
            returned = AppBuilder.answer(sid, "My App")
            assert returned is session
            assert session.answers == ["My App"]
            assert session.current_question_index == 1
        finally:
            AppBuilder.discard_session(sid)

    def test_answer_strips_whitespace(self) -> None:
        session = AppBuilder.start_session()
        sid = session.session_id
        try:
            AppBuilder.answer(sid, "  padded  ")
            assert session.answers == ["padded"]
        finally:
            AppBuilder.discard_session(sid)

    def test_answer_returns_none_for_unknown_session(self) -> None:
        result = AppBuilder.answer("unknown-session-xyz", "some answer")
        assert result is None

    def test_answer_does_not_add_when_complete(self) -> None:
        """AppBuilder.answer enforces is_complete: extra answers are silently dropped."""
        session = AppBuilder.start_session()
        sid = session.session_id
        try:
            # Fill all questions
            for i in range(len(QUESTIONS)):
                AppBuilder.answer(sid, f"Answer {i}")
            assert session.is_complete

            # Extra answer should be ignored
            AppBuilder.answer(sid, "extra answer")
            assert len(session.answers) == len(QUESTIONS)
        finally:
            AppBuilder.discard_session(sid)

    def test_discard_session_removes_it(self) -> None:
        session = AppBuilder.start_session()
        sid = session.session_id
        AppBuilder.discard_session(sid)
        assert AppBuilder.get_session(sid) is None

    def test_discard_nonexistent_session_is_noop(self) -> None:
        # Should not raise
        AppBuilder.discard_session("no-such-session-xyz")

    def test_sessions_are_class_level(self) -> None:
        """Demonstrates that _sessions is shared across all AppBuilder instances."""
        session = AppBuilder.start_session()
        sid = session.session_id
        try:
            # Retrieved via a fresh reference, no instance needed
            assert AppBuilder.get_session(sid) is session
        finally:
            AppBuilder.discard_session(sid)

    def test_multiple_sessions_are_independent(self) -> None:
        s1 = AppBuilder.start_session()
        s2 = AppBuilder.start_session()
        try:
            assert s1.session_id != s2.session_id
            AppBuilder.answer(s1.session_id, "App One")
            assert len(s1.answers) == 1
            assert len(s2.answers) == 0
        finally:
            AppBuilder.discard_session(s1.session_id)
            AppBuilder.discard_session(s2.session_id)


# ---------------------------------------------------------------------------
# _parse_spec
# ---------------------------------------------------------------------------


_MINIMAL_SPEC_JSON = {
    "title": "My App",
    "description": "A test app",
    "layout": {"type": "single-page", "theme": "dark"},
    "state": {"variables": []},
    "components": [
        {
            "id": "heading-1",
            "type": "heading",
            "label": "My App",
            "properties": {"level": 1, "text": "My App"},
            "layout": {"row": 0, "col": 0, "colSpan": 12},
            "bind": "",
            "events": {},
        }
    ],
}


class TestParseSpec:
    def test_parse_valid_json(self) -> None:
        raw = json.dumps(_MINIMAL_SPEC_JSON)
        spec = _parse_spec(raw, "abc123")
        assert spec.id == "abc123"
        assert spec.title == "My App"
        assert len(spec.components) == 1

    def test_parse_json_with_markdown_fences(self) -> None:
        raw = "```json\n" + json.dumps(_MINIMAL_SPEC_JSON) + "\n```"
        spec = _parse_spec(raw, "abc123")
        assert spec.title == "My App"

    def test_parse_json_with_plain_fences(self) -> None:
        raw = "```\n" + json.dumps(_MINIMAL_SPEC_JSON) + "\n```"
        spec = _parse_spec(raw, "abc123")
        assert spec.title == "My App"

    def test_parse_json_embedded_in_surrounding_text(self) -> None:
        """Agent may wrap JSON in explanation text; extraction should still work."""
        raw = "Here is the spec:\n" + json.dumps(_MINIMAL_SPEC_JSON) + "\nDone."
        spec = _parse_spec(raw, "abc123")
        assert spec.title == "My App"

    def test_parse_invalid_json_returns_fallback(self) -> None:
        spec = _parse_spec("not valid json at all", "fallback1")
        assert spec.id == "fallback1"
        # Fallback spec should still be a valid AppSpec
        assert isinstance(spec, AppSpec)
        assert len(spec.components) >= 1

    def test_parse_empty_string_returns_fallback(self) -> None:
        spec = _parse_spec("", "fallback2")
        assert spec.id == "fallback2"
        assert isinstance(spec, AppSpec)

    def test_parse_missing_colSpan_defaults_to_12(self) -> None:
        data = dict(_MINIMAL_SPEC_JSON)
        data["components"] = [
            {
                "id": "c1",
                "type": "text",
                "label": "",
                "properties": {},
                "layout": {"row": 0, "col": 0},  # No colSpan
                "bind": "",
                "events": {},
            }
        ]
        raw = json.dumps(data)
        spec = _parse_spec(raw, "abc123")
        assert spec.components[0].layout.col_span == 12

    def test_parse_existing_colSpan_not_overwritten(self) -> None:
        data = dict(_MINIMAL_SPEC_JSON)
        data["components"] = [
            {
                "id": "c1",
                "type": "text",
                "label": "",
                "properties": {},
                "layout": {"row": 0, "col": 0, "colSpan": 6},
                "bind": "",
                "events": {},
            }
        ]
        raw = json.dumps(data)
        spec = _parse_spec(raw, "abc123")
        assert spec.components[0].layout.col_span == 6

    def test_parse_existing_col_span_snake_not_overwritten(self) -> None:
        """col_span (snake_case) is also recognised as an existing colSpan."""
        data = dict(_MINIMAL_SPEC_JSON)
        data["components"] = [
            {
                "id": "c1",
                "type": "text",
                "label": "",
                "properties": {},
                "layout": {"row": 0, "col": 0, "col_span": 4},
                "bind": "",
                "events": {},
            }
        ]
        raw = json.dumps(data)
        spec = _parse_spec(raw, "abc123")
        assert spec.components[0].layout.col_span == 4

    def test_parse_event_defaults_are_injected(self) -> None:
        data = dict(_MINIMAL_SPEC_JSON)
        data["components"] = [
            {
                "id": "btn-1",
                "type": "button",
                "label": "Go",
                "properties": {"variant": "primary"},
                "layout": {"row": 0, "col": 0, "colSpan": 3},
                "bind": "",
                "events": {
                    "click": {
                        "type": "agent",
                        "agent_prompt": "Do something",
                        # Missing result_bind and local_code
                    }
                },
            }
        ]
        raw = json.dumps(data)
        spec = _parse_spec(raw, "abc123")
        click_ev = spec.components[0].events["click"]
        assert click_ev.result_bind == ""
        assert click_ev.local_code == ""

    def test_parse_sets_app_id(self) -> None:
        raw = json.dumps(_MINIMAL_SPEC_JSON)
        spec = _parse_spec(raw, "unique-id-xyz")
        assert spec.id == "unique-id-xyz"

    def test_parse_sets_default_version(self) -> None:
        data = dict(_MINIMAL_SPEC_JSON)
        data.pop("version", None)
        raw = json.dumps(data)
        spec = _parse_spec(raw, "abc123")
        assert spec.version == "1.0"


# ---------------------------------------------------------------------------
# _fallback_spec
# ---------------------------------------------------------------------------


class TestFallbackSpec:
    def test_fallback_produces_valid_appspec(self) -> None:
        spec = _fallback_spec("fbid", "Fallback App", "Error occurred")
        assert isinstance(spec, AppSpec)
        assert spec.id == "fbid"
        assert spec.title == "Fallback App"

    def test_fallback_has_at_least_two_components(self) -> None:
        spec = _fallback_spec("fbid", "Title", "Desc")
        # heading + error-text
        assert len(spec.components) >= 2

    def test_fallback_has_heading_component(self) -> None:
        spec = _fallback_spec("fbid", "My Title", "Some error")
        heading = next((c for c in spec.components if c.type == "heading"), None)
        assert heading is not None

    def test_fallback_description_in_components(self) -> None:
        spec = _fallback_spec("fbid", "App", "Something went wrong")
        text_comp = next((c for c in spec.components if c.type == "text"), None)
        assert text_comp is not None
        assert text_comp.properties.get("content") == "Something went wrong"

    def test_fallback_has_state_with_message_variable(self) -> None:
        spec = _fallback_spec("fbid", "App", "Error")
        assert any(v.name == "message" for v in spec.state.variables)

    def test_fallback_roundtrip_to_dict(self) -> None:
        """_fallback_spec should produce a spec that survives to_dict() + model_validate()."""
        spec = _fallback_spec("fbid", "App", "Error")
        d = spec.to_dict()
        reloaded = AppSpec.model_validate(d)
        assert reloaded.id == "fbid"
