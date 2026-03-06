"""Edge case tests for CronService and related scheduling logic.

Potential bugs targeted:
- add_job with every_ms=0 creates a non-runnable job (silent failure)
- add_job with past at_ms creates a non-runnable job (silent failure)
- tz field on non-cron schedule raises ValueError (correct)
- list_jobs sorts by next_run_at_ms with None treated as infinity
- remove_job and enable_job for unknown IDs return correct sentinel values
"""

import time

import pytest

from nanobot.cron.service import CronService, _compute_next_run, _validate_schedule_for_add
from nanobot.cron.types import CronSchedule


# ---------------------------------------------------------------------------
# _compute_next_run unit tests
# ---------------------------------------------------------------------------


class TestComputeNextRun:
    def test_at_schedule_future_returns_timestamp(self) -> None:
        now_ms = int(time.time() * 1000)
        future_ms = now_ms + 60_000
        result = _compute_next_run(CronSchedule(kind="at", at_ms=future_ms), now_ms)
        assert result == future_ms

    def test_at_schedule_past_returns_none(self) -> None:
        """An at-schedule in the past should return None — job will never run."""
        now_ms = int(time.time() * 1000)
        past_ms = now_ms - 1000
        result = _compute_next_run(CronSchedule(kind="at", at_ms=past_ms), now_ms)
        assert result is None

    def test_at_schedule_none_at_ms_returns_none(self) -> None:
        result = _compute_next_run(CronSchedule(kind="at", at_ms=None), 0)
        assert result is None

    def test_every_schedule_returns_now_plus_interval(self) -> None:
        now_ms = 1_000_000
        result = _compute_next_run(CronSchedule(kind="every", every_ms=5000), now_ms)
        assert result == now_ms + 5000

    def test_every_schedule_zero_interval_returns_none(self) -> None:
        """every_ms=0 is invalid and must yield None, making the job non-runnable."""
        result = _compute_next_run(CronSchedule(kind="every", every_ms=0), 0)
        assert result is None

    def test_every_schedule_negative_interval_returns_none(self) -> None:
        result = _compute_next_run(CronSchedule(kind="every", every_ms=-500), 0)
        assert result is None

    def test_every_schedule_none_every_ms_returns_none(self) -> None:
        result = _compute_next_run(CronSchedule(kind="every", every_ms=None), 0)
        assert result is None

    def test_cron_schedule_returns_future_timestamp(self) -> None:
        now_ms = int(time.time() * 1000)
        # Every minute — next should be within 60 seconds
        result = _compute_next_run(CronSchedule(kind="cron", expr="* * * * *"), now_ms)
        assert result is not None
        assert result > now_ms
        assert result <= now_ms + 61_000

    def test_cron_schedule_invalid_expr_returns_none(self) -> None:
        result = _compute_next_run(CronSchedule(kind="cron", expr="not a cron"), 0)
        assert result is None

    def test_cron_schedule_none_expr_returns_none(self) -> None:
        result = _compute_next_run(CronSchedule(kind="cron", expr=None), 0)
        assert result is None

    def test_unknown_kind_returns_none(self) -> None:
        result = _compute_next_run(CronSchedule(kind="at"), 0)  # no at_ms
        assert result is None


# ---------------------------------------------------------------------------
# _validate_schedule_for_add unit tests
# ---------------------------------------------------------------------------


class TestValidateScheduleForAdd:
    def test_tz_on_every_raises(self) -> None:
        with pytest.raises(ValueError, match="tz can only be used with cron"):
            _validate_schedule_for_add(
                CronSchedule(kind="every", every_ms=1000, tz="UTC")
            )

    def test_tz_on_at_raises(self) -> None:
        with pytest.raises(ValueError, match="tz can only be used with cron"):
            _validate_schedule_for_add(
                CronSchedule(kind="at", at_ms=9_999_999_999, tz="UTC")
            )

    def test_tz_on_cron_valid_timezone_passes(self) -> None:
        # Should not raise
        _validate_schedule_for_add(
            CronSchedule(kind="cron", expr="0 9 * * *", tz="Asia/Shanghai")
        )

    def test_tz_on_cron_invalid_timezone_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown timezone"):
            _validate_schedule_for_add(
                CronSchedule(kind="cron", expr="0 9 * * *", tz="Fake/NoWhere")
            )

    def test_no_tz_on_any_kind_passes(self) -> None:
        for kind, kwargs in [
            ("at", {"at_ms": 9_999_999_999}),
            ("every", {"every_ms": 1000}),
            ("cron", {"expr": "0 * * * *"}),
        ]:
            _validate_schedule_for_add(CronSchedule(kind=kind, **kwargs))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CronService integration tests
# ---------------------------------------------------------------------------


class TestCronServiceEdgeCases:
    def test_add_job_with_zero_every_ms_is_nonrunnable(self, tmp_path) -> None:
        """
        Documenting known silent-failure: every_ms=0 passes validation but the job
        will never run because _compute_next_run returns None.
        This test serves as a regression guard to detect if this behavior changes.
        """
        service = CronService(tmp_path / "cron.json")
        job = service.add_job(
            name="zero-interval",
            schedule=CronSchedule(kind="every", every_ms=0),
            message="hello",
        )
        # Job is created…
        assert job is not None
        # …but has no next_run time (non-runnable)
        assert job.state.next_run_at_ms is None

    def test_add_job_with_past_at_ms_is_nonrunnable(self, tmp_path) -> None:
        """
        An at-schedule with a timestamp already in the past is accepted but will
        never fire because _compute_next_run returns None.
        """
        now_ms = int(time.time() * 1000)
        service = CronService(tmp_path / "cron.json")
        job = service.add_job(
            name="past-shot",
            schedule=CronSchedule(kind="at", at_ms=now_ms - 5000),
            message="hello",
        )
        assert job.state.next_run_at_ms is None

    def test_list_jobs_sorted_nones_last(self, tmp_path) -> None:
        """Jobs with next_run_at_ms=None sort after those with a time."""
        service = CronService(tmp_path / "cron.json")
        now_ms = int(time.time() * 1000)

        # Runnable job (every 10 minutes)
        runnable = service.add_job(
            name="runnable",
            schedule=CronSchedule(kind="every", every_ms=600_000),
            message="ping",
        )
        # Non-runnable (zero interval): manually set to disabled so it appears in list
        zero_job = service.add_job(
            name="zero",
            schedule=CronSchedule(kind="every", every_ms=0),
            message="noop",
        )

        jobs = service.list_jobs(include_disabled=True)
        # runnable must come first
        runnable_idx = next(i for i, j in enumerate(jobs) if j.id == runnable.id)
        zero_idx = next(i for i, j in enumerate(jobs) if j.id == zero_job.id)
        assert runnable_idx < zero_idx

    def test_remove_job_nonexistent_returns_false(self, tmp_path) -> None:
        service = CronService(tmp_path / "cron.json")
        assert service.remove_job("no-such-id") is False

    def test_enable_job_nonexistent_returns_none(self, tmp_path) -> None:
        service = CronService(tmp_path / "cron.json")
        assert service.enable_job("no-such-id", enabled=True) is None

    def test_remove_existing_job_returns_true(self, tmp_path) -> None:
        service = CronService(tmp_path / "cron.json")
        job = service.add_job(
            name="removable",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="bye",
        )
        assert service.remove_job(job.id) is True
        assert service.list_jobs(include_disabled=True) == []

    def test_enable_then_disable_job(self, tmp_path) -> None:
        service = CronService(tmp_path / "cron.json")
        job = service.add_job(
            name="toggle",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="toggle",
        )
        # Disable
        updated = service.enable_job(job.id, enabled=False)
        assert updated is not None
        assert updated.enabled is False
        assert updated.state.next_run_at_ms is None

        # Re-enable
        updated2 = service.enable_job(job.id, enabled=True)
        assert updated2 is not None
        assert updated2.enabled is True
        assert updated2.state.next_run_at_ms is not None

    def test_status_reflects_running_state(self, tmp_path) -> None:
        service = CronService(tmp_path / "cron.json")
        status = service.status()
        assert "enabled" in status
        assert "jobs" in status
        assert "next_wake_at_ms" in status
        assert status["jobs"] == 0

    def test_persistence_roundtrip(self, tmp_path) -> None:
        """Jobs saved to disk are loaded correctly by a new CronService instance."""
        store_path = tmp_path / "cron.json"
        svc1 = CronService(store_path)
        job = svc1.add_job(
            name="persistent",
            schedule=CronSchedule(kind="every", every_ms=30_000),
            message="persist me",
        )

        svc2 = CronService(store_path)
        jobs = svc2.list_jobs(include_disabled=True)
        assert len(jobs) == 1
        assert jobs[0].id == job.id
        assert jobs[0].name == "persistent"
        assert jobs[0].payload.message == "persist me"

    @pytest.mark.asyncio
    async def test_run_job_manually_calls_on_job(self, tmp_path) -> None:
        called = []

        async def on_job(job):
            called.append(job.id)

        service = CronService(tmp_path / "cron.json", on_job=on_job)
        job = service.add_job(
            name="manual",
            schedule=CronSchedule(kind="every", every_ms=3_600_000),
            message="manual trigger",
        )
        result = await service.run_job(job.id)
        assert result is True
        assert job.id in called

    @pytest.mark.asyncio
    async def test_run_disabled_job_returns_false(self, tmp_path) -> None:
        service = CronService(tmp_path / "cron.json")
        job = service.add_job(
            name="disabled",
            schedule=CronSchedule(kind="every", every_ms=3_600_000),
            message="disabled",
        )
        service.enable_job(job.id, enabled=False)

        result = await service.run_job(job.id, force=False)
        assert result is False

    @pytest.mark.asyncio
    async def test_run_disabled_job_force_succeeds(self, tmp_path) -> None:
        called = []

        async def on_job(j):
            called.append(j.id)

        service = CronService(tmp_path / "cron.json", on_job=on_job)
        job = service.add_job(
            name="force",
            schedule=CronSchedule(kind="every", every_ms=3_600_000),
            message="force",
        )
        service.enable_job(job.id, enabled=False)

        result = await service.run_job(job.id, force=True)
        assert result is True
        assert job.id in called

    @pytest.mark.asyncio
    async def test_run_nonexistent_job_returns_false(self, tmp_path) -> None:
        service = CronService(tmp_path / "cron.json")
        result = await service.run_job("ghost-id")
        assert result is False
