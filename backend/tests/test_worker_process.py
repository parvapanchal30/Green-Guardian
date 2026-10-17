"""The worker as a real operating-system process: configuration from the environment, a scheduled run, a heartbeat, and a
clean exit (status 0) on a termination signal. Uses a throwaway SQLite file; no network, no shared state."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.orm import Base
from app.models import AgentRun
from app.modules.identity.models import Organization
from app.modules.workspaces.models import Workspace

BACKEND = Path(__file__).resolve().parents[1]


def worker_env(db_file: Path, heartbeat: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "TEST_DATABASE_URL")}
    env.update(
        ENV="test",
        DATABASE_URL=f"sqlite+pysqlite:///{db_file.as_posix()}",
        JWT_SECRET="process-test-secret-process-test-secret",
        WEATHER_PROVIDER="mock",
        WORKER_POLL_INTERVAL_S="1",
        WORKER_HEARTBEAT_FILE=str(heartbeat),
        LOG_LEVEL="INFO",
        PYTHONIOENCODING="utf-8",
    )
    return env


def wait_for(predicate, seconds: float = 30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


@pytest.fixture
def seeded_db(tmp_path):
    db_file = tmp_path / "worker.db"
    engine = create_engine(f"sqlite+pysqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(engine)
    ws_id = uuid.uuid4()
    with Session(engine) as db:
        org = Organization(name="Org", slug=f"org-{uuid.uuid4().hex[:8]}")
        db.add(org)
        db.flush()
        db.add(Workspace(id=ws_id, organization_id=org.id, name="Process test", mode="green_management"))
        db.commit()
    yield db_file, engine, ws_id
    engine.dispose()


def start(env: dict[str, str], *args: str) -> subprocess.Popen:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0  # type: ignore[attr-defined]
    return subprocess.Popen(
        [sys.executable, "-m", "app.worker", *args],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=flags,
    )


def terminate_politely(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
    else:
        proc.send_signal(signal.SIGTERM)


def test_the_worker_runs_the_schedule_beats_and_exits_cleanly_on_a_termination_signal(seeded_db, tmp_path):
    db_file, engine, ws_id = seeded_db
    heartbeat = tmp_path / "heartbeat"
    proc = start(worker_env(db_file, heartbeat))
    try:

        def has_run() -> bool:
            with Session(engine) as db:
                return db.scalar(select(AgentRun).where(AgentRun.workspace_id == ws_id)) is not None

        assert wait_for(has_run), "no scheduled run appeared"
        assert wait_for(heartbeat.exists), "no heartbeat file"
        terminate_politely(proc)
        code = proc.wait(timeout=30)
        output = proc.stdout.read() if proc.stdout else ""
    finally:
        if proc.poll() is None:
            proc.kill()
    assert code == 0, output
    assert "worker_started" in output and "worker_stopped" in output
    with Session(engine) as db:
        runs = list(db.scalars(select(AgentRun).where(AgentRun.workspace_id == ws_id)))
    assert len(runs) == 1  # it did not re-run the workspace on the following passes (interval is a day)
    assert runs[0].trigger == "scheduled" and runs[0].status == "succeeded" and runs[0].worker_id
    assert runs[0].finished_at is not None


def test_once_runs_a_single_pass_and_exits_zero(seeded_db, tmp_path):
    db_file, engine, ws_id = seeded_db
    proc = start(worker_env(db_file, tmp_path / "hb"), "--once")
    output, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0, output
    with Session(engine) as db:
        assert len(list(db.scalars(select(AgentRun)))) == 1


def test_the_healthcheck_command_reflects_the_heartbeat(seeded_db, tmp_path):
    db_file, _, _ = seeded_db
    heartbeat = tmp_path / "hb"
    env = worker_env(db_file, heartbeat)

    def run() -> int:
        cmd = [sys.executable, "-m", "app.worker", "--healthcheck"]
        return subprocess.run(cmd, cwd=BACKEND, env=env, capture_output=True, timeout=60).returncode

    assert run() == 1  # no heartbeat yet: unhealthy
    heartbeat.write_text(str(time.time()))
    assert run() == 0
    heartbeat.write_text(str(time.time() - 3600))
    assert run() == 1  # stale
