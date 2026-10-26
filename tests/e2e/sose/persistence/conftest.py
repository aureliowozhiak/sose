"""Dedicated real PostgreSQL per destructive postmaster test (#598).

A shared PostgreSQL instance must never be stopped by real fault injection.
Each destructive test receives its own fixed-port container and fails closed
if provisioning, recovery verification or teardown is unsuccessful.
"""
from __future__ import annotations

from pathlib import Path
import socket
import subprocess
import time
from uuid import uuid4

import psycopg
import pytest


def _docker(*arguments: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("docker", *arguments),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _fixed_host_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _capture_postgres_evidence(name: str, directory: Path) -> None:
    """Capture a bounded forensic record before removing the dedicated DB."""
    directory.mkdir(parents=True, exist_ok=True)
    for filename, args in (
        ("docker-logs.txt", ("logs", "--timestamps", "--tail", "200", name)),
        ("docker-inspect.json", ("inspect", name)),
        ("docker-port.txt", ("port", name, "5432/tcp")),
    ):
        try:
            result = _docker(*args, timeout=15)
            (directory / filename).write_text(
                result.stdout + result.stderr, encoding="utf-8",
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            (directory / filename).write_text(
                f"Failed to obtain Docker diagnostic: {exc}", encoding="utf-8",
            )


def _remove_isolated_postgres(name: str, directory: Path, *, provisioned: bool) -> None:
    """Find/remove by assigned name even if 'docker run' timed out before ID reply."""
    _capture_postgres_evidence(name, directory)
    try:
        inspected = _docker("inspect", name, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.fail(f"cannot inspect isolated PostgreSQL for cleanup: {exc}")
    if inspected.returncode != 0:
        if provisioned or "No such object" not in inspected.stderr:
            pytest.fail(
                "cannot prove isolated PostgreSQL was cleaned up: "
                + inspected.stderr[-1500:]
            )
        # Container was never created; preserve the original provisioning error.
        return

    try:
        removed = _docker("rm", "-f", name, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.fail(f"cannot remove isolated PostgreSQL {name}: {exc}")
    if removed.returncode != 0:
        pytest.fail(
            f"isolated PostgreSQL container removal failed ({name}): "
            + removed.stderr[-1500:]
        )


@pytest.fixture
def isolated_postgres_service(request, monkeypatch, tmp_path):
    """Physically destructive variants only; proxy cases keep the shared DB.

    Use one real fixed-port Docker PostgreSQL per test. All callers' DSN globals
    and subprocess environments are temporarily patched only for this testcase.
    """
    parameters = getattr(getattr(request.node, "callspec", None), "params", {})
    if parameters.get("transport") == "proxy":
        yield
        return

    port = _fixed_host_port()
    name = f"sose-pg-chaos-{uuid4().hex[:16]}"
    dsn = f"postgresql://postgres@127.0.0.1:{port}/postgres"
    diagnostics = tmp_path / "isolated-postgres"
    provisioned = False

    # This try/finally includes docker run itself. Even a timeout or lost
    # container-ID reply must trigger discovery and cleanup by known name.
    try:
        try:
            run = _docker(
                "run", "-d", "--name", name,
                "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                "-e", "POSTGRES_DB=postgres",
                "-p", f"127.0.0.1:{port}:5432",
                "postgres:16-alpine", timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            pytest.fail(f"isolated PostgreSQL provisioning command failed: {exc}")

        if run.returncode != 0:
            pytest.fail(
                "real isolated PostgreSQL container provisioning failed: "
                + run.stderr[-1500:]
            )
        container_id = run.stdout.strip()
        if not container_id:
            pytest.fail("docker run returned no PostgreSQL container identifier")
        provisioned = True

        deadline = time.monotonic() + 120.0
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with psycopg.connect(dsn, connect_timeout=2) as connection:
                    assert connection.execute("SELECT 1").fetchone() == (1,)
                break
            except (psycopg.Error, AssertionError) as error:
                last_error = error
                time.sleep(0.25)
        else:
            pytest.fail(f"isolated PostgreSQL never became ready: {last_error}")

        published = _docker("port", name, "5432/tcp").stdout.strip()
        if published != f"127.0.0.1:{port}":
            pytest.fail(
                f"isolated PostgreSQL must preserve fixed host port: {published}"
            )

        module = request.module
        monkeypatch.setattr(module, "DSN", dsn)
        monkeypatch.setattr(module, "CONTAINER_ID", container_id)
        monkeypatch.setenv("SOSE_TEST_POSTGRES_DSN", dsn)
        monkeypatch.setenv("SOSE_POSTGRES_CONTAINER_ID", container_id)
        yield

        # A passing physical recovery must restore the same host TCP endpoint
        # and a real SQL connection, not merely restart a container process.
        after = _docker("port", name, "5432/tcp").stdout.strip()
        if after != f"127.0.0.1:{port}":
            pytest.fail(
                f"PostgreSQL host port changed after physical restart: "
                f"{after!r}; original was {port}"
            )
        with psycopg.connect(dsn, connect_timeout=3) as connection:
            assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        _remove_isolated_postgres(name, diagnostics, provisioned=provisioned)
