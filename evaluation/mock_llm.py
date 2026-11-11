"""OpenAI-compatible stand-in for the proxy that records what the framework sends.

GET /stats returns totals and one row per request; GET /first returns the first
request body. Each conversation makes one shell call, then answers.
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"requests": 0, "spent": 0.0, "rows": [], "first": None, "rejected": 0}
BUDGET = float("inf")
DELAY = 0.0
NO_USAGE = False
FAIL_EVERY = 0  # --fail-every N: every Nth POST answers 502, like a proxy hiccup
POSTS = [0]
ANSWER = "389"
OUTPUT_TOKENS = 12


def _shell_call(request: dict, number: int) -> dict | None:
    names = [t["function"]["name"] for t in request.get("tools") or []]
    if any(m.get("role") == "tool" for m in request["messages"]):
        return None
    if "bash" in names:
        name, args = "bash", {"command": "python3 -c 'print(1669 - 36 * 3)'", "description": "compute", "timeout": 10}
    elif "sh" in names:
        name, args = "sh", {"command": "echo ok"}
    else:
        return None
    return {"id": f"call_{number}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, json.dumps(STATE["first"] if self.path == "/first" else STATE).encode())

    def do_POST(self):
        time.sleep(DELAY)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        POSTS[0] += 1
        if FAIL_EVERY and POSTS[0] % FAIL_EVERY == 0:
            STATE["failed"] = STATE.get("failed", 0) + 1
            self._send(502, b'{"error":{"message":"bad gateway"}}')
            return
        if STATE["spent"] >= BUDGET:
            STATE["rejected"] += 1
            self._send(429, b'{"error":{"message":"budget exhausted"}}')
            return
        request = json.loads(raw)
        STATE["first"] = STATE["first"] or request
        messages_chars, tools_chars = len(json.dumps(request["messages"])), len(json.dumps(request.get("tools") or []))
        input_tokens = (messages_chars + tools_chars) // 4
        STATE["requests"] += 1
        STATE["spent"] += input_tokens / 10 + OUTPUT_TOKENS
        STATE["rows"].append({
            "path": self.path, "model": request.get("model"), "messages": len(request["messages"]),
            "messages_chars": messages_chars, "tools_chars": tools_chars, "stream": bool(request.get("stream")),
            "tools": [t["function"]["name"] for t in request.get("tools") or []],
            "tool_sizes": {t["function"]["name"]: len(json.dumps(t)) for t in request.get("tools") or []},
            "last": str(request["messages"][-1].get("content"))[:500],
            "system": str(request["messages"][0].get("content"))[:300],
        })
        call = _shell_call(request, STATE["requests"])
        message = {"role": "assistant", "content": ""} if call else {"role": "assistant", "content": ANSWER}
        if call:
            message["tool_calls"] = [call]
        finish = "tool_calls" if call else "stop"
        usage = {} if NO_USAGE else {"prompt_tokens": input_tokens, "completion_tokens": OUTPUT_TOKENS,
                                     "total_tokens": input_tokens + OUTPUT_TOKENS}
        if request.get("stream"):
            delta = dict(message)
            if call:
                delta["tool_calls"] = [dict(call, index=0)]
            events = [
                {"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                {"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
                {"id": "x", "object": "chat.completion.chunk", "choices": [], "usage": usage},
            ]
            self._send(200, ("".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n").encode(), "text/event-stream")
            return
        self._send(200, json.dumps({
            "id": "x", "object": "chat.completion", "model": request.get("model"),
            "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage,
        }).encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--budget", type=float, default=float("inf"))
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--no-usage", action="store_true")
    parser.add_argument("--fail-every", type=int, default=0)
    options = parser.parse_args()
    BUDGET, DELAY, NO_USAGE, FAIL_EVERY = options.budget, options.delay, options.no_usage, options.fail_every
    ThreadingHTTPServer(("0.0.0.0", options.port), Handler).serve_forever()
