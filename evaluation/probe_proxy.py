"""One short request per allowed model: shows the proxy's usage format. Never prints the key."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MODELS = ["qwen3.8-27b", "qwen3.8-27b-noreason", "qwen3.6-35b-a3b", "qwen3.6-35b-a3b-noreason"]
PROMPT = "What is 17*23? Reply with only the number."


def main() -> None:
    url = os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['LLM_API_KEY']}"}
    for model in MODELS:
        body = json.dumps({"model": model, "max_tokens": 600, "temperature": 0,
                           "messages": [{"role": "user", "content": PROMPT}]}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=120) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            print(model, "HTTP", exc.code, exc.read()[:200].decode(errors="replace"))
            continue
        except OSError as exc:
            print(model, "ERROR", type(exc).__name__, str(exc)[:200])
            continue
        message = data["choices"][0]["message"]
        reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
        print(json.dumps({
            "model": model, "answer": (message.get("content") or "")[:60], "reasoning_chars": len(reasoning),
            "finish": data["choices"][0].get("finish_reason"), "usage": data.get("usage"),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
