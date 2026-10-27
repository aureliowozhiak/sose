"""Dedicated real PostgreSQL per destructive postmaster test (#598).

A shared PostgreSQL instance must never be stopped by real fault injection.
Each destructive test receives its own Docker container with a stable published
host port and fails closed if provisioning, recovery verification or teardown
is unsuccessful.
"""
from __future__ import annotations

from pathlib import Path
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


def _published_host_port(name: str) -> int:
    """Return Docker's assigned loopback port, failing closed on bad mappings."""
    result = _docker("port", name, "5432/tcp", timeout=15)
    if result.returncode != 0:
        pytest.fail(
            f"cannot inspect isolated PostgreSQL host port ({name}): "
            + result.stderr[-1500:]
        )

    published = result.stdout.strip()
    host, separator, raw_port = published.rpartition(":")
    if not separator or host != "127.0.0.1":
        pytest.fail(
            "isolated PostgreSQL must publish exactly one loopback endpoint; "
            f"got {published!r}"
        )
    try:
        port = int(raw_port)
    except ValueError:
        pytest.fail(f"invalid isolated PostgreSQL host port: {published!r}")
    if not 1 <= port <= 65535:
        pytest.fail(f"invalid isolated PostgreSQL host port: {published!r}")
    return port


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
    """Always attempt named-container removal, including after inspect failure.

    Inspection is best-effort discovery, never a prerequisite for cleanup. A
    successful docker rm -f is sufficient for a previously unknown container;
    any failed removal fails the test rather than leaking trust-auth PostgreSQL.
    """
    inspect_error = None
    try:
        _capture_postgres_evidence(name, directory)
    except (OSError, subprocess.TimeoutExpired) as exc:
        # Diagnostic errors must never prevent the teardown attempt.
        inspect_error = f"diagnostic capture failed: {exc}"

    try:
        inspected = _docker("inspect", name, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        inspect_error = f"container inspection failed: {exc}"
    else:
        if inspected.returncode != 0:
            if "No such object" in inspected.stderr and not provisioned:
                return
            inspect_error = (
                "container inspection returned nonzero: " + inspected.stderr[-1500:]
            )

    # Crucial: even when inspect timed out or failed, use the known unique
    # container name to remove any object docker run might have left behind.
    try:
        removed = _docker("rm", "-f", name, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.fail(
            f"cannot remove isolated PostgreSQL {name}: {exc}; "
            f"inspection: {inspect_error}"
        )
    if removed.returncode != 0:
        pytest.fail(
            f"isolated PostgreSQL container removal failed ({name}): "
            + removed.stderr[-1500:]
            + (f"; inspection: {inspect_error}" if inspect_error else "")
        )


@pytest.fixture
def isolated_postgres_service(request, monkeypatch, tmp_path):
    """Physically destructive variants only; proxy cases keep the shared DB.

    Docker allocates the loopback host port atomically, avoiding the race in
    bind(127.0.0.1, 0) -> close -> docker run -p <port>. The published port is
    then read from Docker and must remain stable across postmaster restarts.
    """
    parameters = getattr(getattr(request.node, "callspec", None), "params", {})
    if parameters.get("transport") == "proxy":
        yield
        return

    name = f"sose-pg-chaos-{uuid4().hex[:16]}"
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
                "-p", "127.0.0.1::5432",
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

        port = _published_host_port(name)
        dsn = f"postgresql://postgres@127.0.0.1:{port}/postgres"

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

        if _published_host_port(name) != port:
            pytest.fail(
                "isolated PostgreSQL host port changed during readiness check"
            )

        module = request.module
        monkeypatch.setattr(module, "DSN", dsn)
        monkeypatch.setattr(module, "CONTAINER_ID", container_id)
        monkeypatch.setenv("SOSE_TEST_POSTGRES_DSN", dsn)
        monkeypatch.setenv("SOSE_POSTGRES_CONTAINER_ID", container_id)
        yield

        # A passing physical recovery must restore the same host TCP endpoint
        # and a real SQL connection, not merely restart a container process.
        after = _published_host_port(name)
        if after != port:
            pytest.fail(
                f"PostgreSQL host port changed after physical restart: "
                f"{after!r}; original was {port}"
            )
        with psycopg.connect(dsn, connect_timeout=3) as connection:
            assert connection.execute("SELECT 1").fetchone() == (1,)
    finally:
        _remove_isolated_postgres(name, diagnostics, provisioned=provisioned)
