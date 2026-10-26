"""Dedicated real PostgreSQL per destructive postmaster test (#598).

The shared pytest_auto_postgres database must never be stopped by a fault test:
an unready postmaster otherwise poisons unrelated conformance nodes. A true
Docker stop/start still occurs inside the caller's test, using a fixed host
port so the original DSN keeps referring to the same instance after restart.
"""
from __future__ import annotations

import json
import os
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


def _capture_postgres_evidence(container_id: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, args in (
        ("docker-logs.txt", ("logs", "--timestamps", "--tail", "200", container_id)),
        ("docker-inspect.json", ("inspect", container_id)),
        ("docker-port.txt", ("port", container_id, "5432/tcp")),
    ):
        try:
            result = _docker(*args, timeout=15)
            (directory / name).write_text(
                result.stdout + result.stderr, encoding="utf-8",
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            (directory / name).write_text(
                f"Failed to obtain Docker diagnostic: {exc}", encoding="utf-8",
            )


@pytest.fixture
def isolated_postgres_service(request, monkeypatch, tmp_path):
    """Only real postmaster-death variants receive an independent database.

    Tests exercising a proxy-only disruption keep their standard shared DSN.
    Import-time DSN/CONTAINER_ID globals on the specifically requesting module
    are patched, and child process environment is patched for the test lifetime.
    """
    parameters = getattr(getattr(request.node, "callspec", None), "params", {})
    if parameters.get("transport") == "proxy":
        yield
        return

    # A chosen fixed binding survives docker stop/start. Never use
    # '-p 127.0.0.1::5432': Docker can rebind a new port upon restart.
    port = _fixed_host_port()
    name = f"sose-pg-chaos-{uuid4().hex[:16]}"
    run = _docker(
        "run", "-d", "--name", name,
        "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
        "-e", "POSTGRES_DB=postgres",
        "-p", f"127.0.0.1:{port}:5432",
        "postgres:16-alpine", timeout=45,
    )
    if run.returncode != 0:
        pytest.fail(
            "real isolated PostgreSQL container provisioning failed: "
            + run.stderr[-1500:]
        )
    container_id = run.stdout.strip()
    if not container_id:
        pytest.fail("docker run returned no PostgreSQL container identifier")
    diagnostics = tmp_path / "isolated-postgres"
    dsn = f"postgresql://postgres@127.0.0.1:{port}/postgres"

    try:
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

        published = _docker("port", container_id, "5432/tcp").stdout.strip()
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
    finally:
        _capture_postgres_evidence(container_id, diagnostics)
        _docker("rm", "-f", container_id, timeout=45)
