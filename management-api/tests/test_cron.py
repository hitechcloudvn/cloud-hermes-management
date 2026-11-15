"""Cron job tests. / Test job cron."""

from __future__ import annotations

import json

from conftest import assert_fail, assert_ok

JOBS = [
    {"id": "job-1", "name": "daily-report", "status": "running"},
    {"id": "job-2", "name": "digest", "status": "paused"},
    {"id": "job-3", "name": "cleanup", "status": "failed"},
    {"name": "unnamed", "status": "whatever"},
]


def _seed_jobs(runner, jobs=None):
    payload = jobs if jobs is not None else JOBS
    runner.set_result("hermes", "cron", "list", stdout=json.dumps(payload))


def test_list_jobs(client, auth_headers, runner):
    _seed_jobs(runner)
    payload = assert_ok(client.get("/api/cron", headers=auth_headers))
    assert payload["data"]["count"] == 4
    assert payload["data"]["jobs"][0]["id"] == "job-1"


def test_list_jobs_accepts_wrapped_json(client, auth_headers, runner):
    runner.set_result("hermes", "cron", "list", stdout=json.dumps({"jobs": [{"id": "a"}]}))
    payload = assert_ok(client.get("/api/cron", headers=auth_headers))
    assert payload["data"]["count"] == 1


def test_list_jobs_garbage_output(client, auth_headers, runner):
    runner.set_result("hermes", "cron", "list", stdout="not json at all")
    payload = assert_ok(client.get("/api/cron", headers=auth_headers))
    assert payload["data"] == {"jobs": [], "count": 0}


def test_cron_status_counts(client, auth_headers, runner):
    _seed_jobs(runner)
    payload = assert_ok(client.get("/api/cron/status", headers=auth_headers))
    assert payload["data"] == {"total": 4, "running": 1, "paused": 1, "failed": 1, "other": 1}


def test_create_job_empty_body_422(client, auth_headers):
    response = client.post("/api/cron", headers=auth_headers, json={})
    assert response.status_code == 422


def test_create_job_happy(client, auth_headers, runner):
    runner.set_result("hermes", "cron", "create", stdout=json.dumps([{"id": "fresh", "name": "n"}]))
    payload = assert_ok(
        client.post(
            "/api/cron",
            headers=auth_headers,
            json={"name": "n", "schedule": "0 9 * * *", "prompt": "do it", "job_id": "fresh", "description": "d"},
        ),
    )
    assert payload["data"]["created"] is True
    assert payload["data"]["job"]["id"] == "fresh"
    assert runner.called_with("hermes", "cron", "create")


def test_create_job_cli_failure_500(client, auth_headers, runner):
    runner.set_result("hermes", "cron", "create", exit_code=1, stderr="bad schedule\n")
    response = client.post(
        "/api/cron",
        headers=auth_headers,
        json={"name": "n", "schedule": "nope", "prompt": "p"},
    )
    assert_fail(response, 500)


def test_delete_job_unknown_404(client, auth_headers, runner):
    _seed_jobs(runner)
    assert_fail(client.delete("/api/cron/__nonexistent__", headers=auth_headers), 404)
    assert not runner.called_with("hermes", "cron", "remove")


def test_delete_job_happy(client, auth_headers, runner):
    _seed_jobs(runner)
    payload = assert_ok(client.delete("/api/cron/job-1", headers=auth_headers))
    assert payload["data"] == {"id": "job-1", "deleted": True}
    assert runner.called_with("hermes", "cron", "remove", "job-1")


def test_pause_job(client, auth_headers, runner):
    _seed_jobs(runner)
    payload = assert_ok(client.post("/api/cron/job-2/pause", headers=auth_headers))
    assert payload["data"]["paused"] is True
    assert runner.called_with("hermes", "cron", "pause", "job-2")


def test_resume_job_unknown_404(client, auth_headers, runner):
    _seed_jobs(runner)
    assert_fail(client.post("/api/cron/nope/resume", headers=auth_headers), 404)


def test_run_job_happy(client, auth_headers, runner):
    _seed_jobs(runner)
    payload = assert_ok(client.post("/api/cron/job-3/run", headers=auth_headers))
    assert payload["data"]["triggered"] is True
    assert runner.called_with("hermes", "cron", "run", "job-3")


def test_job_found_by_name_when_no_id(client, auth_headers, runner):
    _seed_jobs(runner)
    payload = assert_ok(client.post("/api/cron/unnamed/run", headers=auth_headers))
    assert payload["data"]["id"] == "unnamed"
