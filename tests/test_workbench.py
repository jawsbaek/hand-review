import json
import os
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from hand_review.recommendations import AnalysisOptions
from hand_review.workbench import Session, handler_for


@pytest.fixture
def session(tmp_path):
    source = Path(__file__).parents[1] / "samples/pokerist/demo.jsonl"
    s = Session(source, AnalysisOptions(samples=16, solver=False), tmp_path)
    yield s
    s.close()


def wait(session, job):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = session.poll(job)
        if state["status"] != "running":
            return state
        time.sleep(0.02)
    pytest.fail("analysis did not finish")


def test_private_session_computes_range_changes_and_coalesces_duplicate_requests(session):
    first = {"hand": 0, "decision": 0, "ranges": {"1": "AA"}}
    job = session.submit(first)
    assert session.submit(first) == job
    strong = wait(session, job)
    weak = wait(session, session.submit({**first, "ranges": {"1": "22"}}))
    assert strong["status"] == weak["status"] == "complete"
    assert strong["analysis"]["model"]["actions"] != weak["analysis"]["model"]["actions"]
    assert "context" not in strong["analysis"]
    assert session.report["hands"][0]["decisions"][0]["analysis"]["status"] == "pending"
    for bad in (
        {"hand": -1},
        {"hand": True, "decision": 0},
        {"hand": 0, "decision": 500},
        {"hand": 0, "decision": 0, "ranges": {"99": "AA"}},
        {"hand": 0, "decision": 0, "ranges": {"1": "AA:NaN"}},
    ):
        with pytest.raises(ValueError):
            session.submit(bad)


def test_loopback_api_rejects_cross_origin_bad_host_and_missing_token(session):
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(session))
    except PermissionError:
        if os.environ.get("CI"):
            raise
        pytest.skip("workspace sandbox forbids loopback listeners; CI runs the real HTTP test")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    payload = json.dumps({"hand": 0, "decision": 0}).encode()
    try:
        for headers in (
            {},
            {"X-Review-Token": session.token, "Origin": "https://example.invalid"},
            {"X-Review-Token": session.token, "Host": "example.invalid"},
        ):
            with pytest.raises(HTTPError) as rejected:
                urlopen(
                    Request(
                        origin + "/api/analyze", data=payload, headers={"Content-Type": "application/json", **headers}
                    ),
                    timeout=5,
                )
            assert rejected.value.code == 403
        req = Request(
            origin + "/api/analyze",
            data=payload,
            headers={"Content-Type": "application/json", "X-Review-Token": session.token, "Origin": origin},
        )
        with urlopen(req, timeout=5) as response:
            assert response.status == 202
            job = json.load(response)["job"]
        wait(session, job)
        with urlopen(
            Request(origin + "/api/jobs/" + job, headers={"X-Review-Token": session.token}), timeout=5
        ) as response:
            assert json.load(response)["status"] == "complete"
        with urlopen(origin, timeout=5) as response:
            assert response.headers["X-Frame-Options"] == "DENY"
            assert session.token.encode() in response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
