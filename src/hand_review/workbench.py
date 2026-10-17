"""A loopback-only workbench for editable ranges and private on-demand analysis.

The report remains usable as an offline file. Recalculation uses this optional
local process; there are no third-party APIs, arbitrary file paths or commands.
"""

import copy
import hmac
import json
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hand_review.coaching import default_ranges, parse_range
from hand_review.pokerist import load_pokerist, replay_hand
from hand_review.profiles import Evidence
from hand_review.recommendations import analyze_cached
from hand_review.replay import build_report, render_report


class Session:
    def __init__(self, path, options, cache_dir=None):
        records, _, _ = load_pokerist(path)
        self.hands = [replay_hand(raw, i) for i, raw in enumerate(records, 1)]
        self.evidence = Evidence(self.hands)
        self.options, self.cache_dir = options, cache_dir
        self.token = secrets.token_hex(32)
        self.report = build_report(path)
        self.report["version"] = 2
        self.report["analysis"] = {"samples": options.samples, "solver": options.solver, "live_token": self.token}
        for hi, hand in enumerate(self.report["hands"]):
            for di, decision in enumerate(hand["decisions"]):
                context = self.hands[hi]["decisions"][di]["context"]
                decision["analysis"] = {"status": "pending"}
                if context["trustworthy"]:
                    decision["analysis"]["initial_ranges"] = default_ranges(context)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="review-analysis")
        self.jobs, self.requests = {}, {}
        self.lock = threading.RLock()

    def submit(self, body):
        if not isinstance(body, dict):
            raise ValueError("분석 요청은 JSON 객체여야 합니다.")
        hi, di = body.get("hand"), body.get("decision")
        if type(hi) is not int or type(di) is not int or not 0 <= hi < len(self.hands):
            raise ValueError("핸드 번호를 확인하세요.")
        hand = self.hands[hi]
        if not 0 <= di < len(hand["decisions"]):
            raise ValueError("결정 번호를 확인하세요.")
        context = hand["decisions"][di]["context"]
        overrides = body.get("ranges", {})
        if not isinstance(overrides, dict) or len(overrides) > 10:
            raise ValueError("좌석별 레인지 객체를 입력하세요.")
        allowed = {str(p["seat"]) for p in context["players"] if not p["folded"] and (not p["departed"] or p["all_in"])}
        if set(overrides) - allowed:
            raise ValueError("참가 중인 좌석의 레인지만 수정할 수 있습니다.")
        for text in overrides.values():
            parse_range(text)
        key = json.dumps({"hand": hi, "decision": di, "ranges": overrides}, sort_keys=True)
        with self.lock:
            if key in self.requests:
                return self.requests[key]
            if sum(not job.done() for job in self.jobs.values()) >= 8:
                raise ValueError("먼저 요청한 분석이 끝난 뒤 다시 시도하세요.")
            ident = secrets.token_hex(16)
            prior = self.evidence.before(hand)
            self.jobs[ident] = self.pool.submit(
                analyze_cached, copy.deepcopy(context), prior, self.options, copy.deepcopy(overrides), self.cache_dir
            )
            self.requests[key] = ident
            return ident

    def poll(self, ident):
        with self.lock:
            future = self.jobs.get(ident)
        if future is None:
            raise KeyError("없는 분석 작업입니다.")
        if not future.done():
            return {"status": "running"}
        try:
            return {"status": "complete", "analysis": future.result()}
        except Exception:
            return {"status": "failed", "note": "분석을 완료하지 못했습니다. 입력 레인지와 기록을 확인하세요."}

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)


def handler_for(session):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Do not write session data or request bodies into access logs.

        def valid_host(self):
            port = self.server.server_port
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def authorized(self):
            origin = self.headers.get("Origin")
            port = self.server.server_port
            return (
                self.valid_host()
                and hmac.compare_digest(self.headers.get("X-Review-Token", ""), session.token)
                and (origin is None or origin in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"})
            )

        def send(self, status, payload, html=False):
            data = payload.encode() if html else json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8" if html else "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "허용되지 않은 Host입니다."})
            if self.path == "/":
                return self.send(200, render_report(session.report), html=True)
            if self.path == "/health":
                return self.send(200, {"status": "ok"})
            match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})", self.path)
            if match and self.authorized():
                try:
                    return self.send(200, session.poll(match[1]))
                except KeyError:
                    return self.send(404, {"error": "없는 분석 작업입니다."})
            return self.send(403 if self.path.startswith("/api/") else 404, {"error": "요청을 허용하지 않았습니다."})

        def do_POST(self):
            if self.path != "/api/analyze" or not self.authorized():
                return self.send(403, {"error": "허용되지 않은 분석 요청입니다."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 64000:
                    raise ValueError("분석 요청은 64KB 이하여야 합니다.")
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("JSON 요청만 지원합니다.")
                body = json.loads(self.rfile.read(length))
                return self.send(202, {"job": session.submit(body)})
            except (ValueError, TypeError) as error:
                return self.send(400, {"error": str(error)})

    return Handler


def serve(path, options, port=8765, cache_dir=None):
    # Bind first: a denied port should not start expensive computations or threads.
    server = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    session = None
    try:
        session = Session(path, options, cache_dir or Path("reports/.hand-review-cache"))
        server.RequestHandlerClass = handler_for(session)
        print(f"로컬 복기: http://127.0.0.1:{server.server_port}/", flush=True)
        print("레인지를 수정하면 이 로컬 프로세스에서 재계산합니다. 종료: Ctrl+C", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if session:
            session.close()
