#!/usr/bin/env python3
"""Portable client checks for a running Strata server.

Only the standard library is used, so any Python 3.8 or newer can run it from a
checkout, a container or a laptop. Nothing here writes into the repository.

    probe_client.py models   --url http://127.0.0.1:8080
    probe_client.py bench    --url http://127.0.0.1:8080 --prompt short --max-tokens 64
    probe_client.py bench    --url http://127.0.0.1:8080 --prompt 2k
    probe_client.py vision   --url http://127.0.0.1:8080 [--image picture.png]
    probe_client.py queue    --url http://127.0.0.1:8080 --count 2
    strata launch --plan ... --output json | probe_client.py plan
    probe_client.py opencode-config --url http://127.0.0.1:8080 --out opencode.jsonc

The model defaults to the first one the server reports, so the same command
works whatever size is loaded.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

FILLER = ("The maintenance log for the north greenhouse records rows of sensor readings, valve states and "
          "irrigation windows. Each entry repeats the same wording so that the page reads like the others, and "
          "only one line carries the fact you need. ")
NEEDLE = "The spare valve key for row seven is CODE 4217. "
PROMPTS = {"short": "Write one short sentence about a greenhouse.\n",
           "2k": (FILLER * 18).strip() + "\n\n" + NEEDLE + "\n\n" + (FILLER * 18).strip(),
           "8k": (FILLER * 65).strip() + "\n\n" + NEEDLE + "\n\n" + (FILLER * 65).strip()}
QUESTIONS = {"short": "Write one short sentence about a greenhouse.",
             "2k": "Find the spare valve key in the text and answer with the code only.",
             "8k": "Find the spare valve key in the text and answer with the code only."}

# 448x224 PNG: "CODE 4217", a red circle and a blue rectangle, so `vision` needs no file.
DEFAULT_IMAGE = (
    "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"
)

def _request(url: str, path: str, body: dict | None = None, key: str | None = None, timeout: float = 3600):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url.rstrip("/") + path, data=data,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": "Bearer " + key} if key else {})})
    return urllib.request.urlopen(request, timeout=timeout)


def model_id(url: str, key: str | None, wanted: str | None) -> str:
    """The model to talk to: the one asked for, else the first the server reports."""
    if wanted:
        return wanted
    with _request(url, "/v1/models", key=key, timeout=60) as response:
        data = json.load(response).get("data") or []
    if not data:
        raise SystemExit("the server reports no model; is one loaded?")
    return data[0]["id"]


def cmd_models(args) -> int:
    with _request(args.url, "/v1/models", key=args.api_key, timeout=60) as response:
        data = json.load(response).get("data") or []
    if not data:
        print("no model is loaded")
        return 1
    for item in data:
        meta = item.get("meta") or {}
        status = (item.get("status") or {}).get("value", "?")
        print(f"{item['id']}\t{status}\tn_ctx={meta.get('n_ctx', '?')}")
    return 0


def _stream_chat(args, prompt: str, max_tokens: int, model: str) -> dict:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0, "stream": True,
            "reasoning_effort": args.reasoning_effort,
            "stream_options": {"include_usage": True}}
    start = time.time()
    first = None
    pieces: list[str] = []
    usage: dict = {}
    with _request(args.url, "/v1/chat/completions", body, args.api_key) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                event = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if event.get("usage"):
                usage = event["usage"]
            for choice in event.get("choices") or []:
                delta = choice.get("delta") or {}
                piece = delta.get("content") or delta.get("reasoning_content")
                if piece:
                    first = first or time.time()
                    pieces.append(piece)
    end = time.time()
    completion = usage.get("completion_tokens") or 0
    decode_seconds = end - (first or start)
    return {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": completion,
            "ttft_s": round(first - start, 2) if first else None,
            "wall_s": round(end - start, 1),
            "decode_tok_s": round(completion / decode_seconds, 2) if completion and decode_seconds > 0 else None,
            "prompt_tok_s": round((usage.get("prompt_tokens") or 0) / (first - start), 1) if first and usage.get("prompt_tokens") else None,
            "answer": "".join(pieces)[:160].replace("\n", " ")}


def cmd_bench(args) -> int:
    model = model_id(args.url, args.api_key, args.model)
    prompt = PROMPTS[args.prompt]
    if args.question:
        prompt = args.question + "\n\n" + (prompt if args.prompt != "short" else "")
    for run in range(args.repeat):
        result = _stream_chat(args, prompt, args.max_tokens, model)
        result["run"] = run + 1
        print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_vision(args) -> int:
    model = model_id(args.url, args.api_key, args.model)
    if args.image:
        data = base64.b64encode(open(args.image, "rb").read()).decode()
        mime = "image/png" if args.image.lower().endswith(".png") else "image/jpeg"
    else:
        data, mime = DEFAULT_IMAGE, "image/png"
    body = {"model": model, "messages": [{"role": "user", "content": [
        {"type": "text", "text": args.question},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}]}],
        "max_tokens": args.max_tokens, "temperature": 0, "reasoning_effort": args.reasoning_effort}
    start = time.time()
    with _request(args.url, "/v1/chat/completions", body, args.api_key) as response:
        payload = json.load(response)
    usage = payload.get("usage") or {}
    message = payload["choices"][0]["message"]
    print(json.dumps({"wall_s": round(time.time() - start, 1),
                      "prompt_tokens": usage.get("prompt_tokens"),
                      "completion_tokens": usage.get("completion_tokens"),
                      "answer": (message.get("content") or "")[:200],
                      "reasoning": (message.get("reasoning_content") or "")[:120]}, ensure_ascii=False))
    return 0


def cmd_queue(args) -> int:
    model = model_id(args.url, args.api_key, args.model)
    start = time.time()
    results: dict[int, dict] = {}

    def ask(index: int) -> None:
        began = time.time()
        result = _stream_chat(args, "Name one fruit in one word.", 32, model)
        results[index] = {"start_s": round(began - start, 1), "end_s": round(time.time() - start, 1),
                          "completion_tokens": result["completion_tokens"],
                          "decode_tok_s": result["decode_tok_s"]}

    threads = [threading.Thread(target=ask, args=(index,)) for index in range(args.count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for index in sorted(results):
        print(json.dumps({"request": index + 1, **results[index]}))
    started = sorted(item["start_s"] for item in results.values())
    ended = sorted(item["end_s"] for item in results.values())
    if len(ended) > 1 and ended[0] <= started[1]:
        print("overlapped: more than one request ran at the same time")
    else:
        print("serialized: requests ran one after another")
    return 0


def cmd_plan(args) -> int:
    payload = json.load(sys.stdin)
    plan = payload.get("plan") or payload
    model = plan.get("model") or {}
    settings = plan.get("settings") or {}
    download = plan.get("download") or {}
    warnings = plan.get("warnings") or []
    print(f"model     {model.get('title', '?')}  {model.get('model_gb', '?')} GB")
    print(f"context   {settings.get('context', '?')}  parallel {settings.get('parallel') or 'fit to the card'}")
    print(f"download  {download.get('gb', 0)} GB  engine missing: {download.get('engine_missing')}")
    print(f"drafting  {plan.get('drafting', '')}")
    for warning in warnings:
        print(f"warning   {warning}")
    refused = any("does not fit" in warning for warning in warnings)
    print("verdict   does not fit" if refused else "verdict   fits (no fit warning)")
    return 2 if refused else 0


def cmd_opencode_config(args) -> int:
    model = model_id(args.url, args.api_key, args.model)
    output = 16384          # issue #5006: the 4096 default breaks compaction in long sessions
    context = args.context
    config = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"strata/{model}",
        "small_model": f"strata/{model}",
        "autoupdate": False,
        "compaction": {"auto": True, "buffer": output},
        "share": "disabled",
        "provider": {"strata": {"npm": "@ai-sdk/openai-compatible", "name": "Strata (local)",
                                "options": {"baseURL": args.url.rstrip("/") + "/v1",
                                            "apiKey": args.api_key or "strata-local"},
                                "models": {model: {"name": "Qwen3.8-Flash-Next (local)", "tool_call": True,
                                                   "reasoning": True,
                                                   "limit": {"context": context,
                                                             "input": context - output,
                                                             "output": output}}}}}}
    text = json.dumps(config, indent=2)
    if args.out:
        with open(args.out, "w") as handle:
            handle.write(text + "\n")
        print(args.out)
    else:
        print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Portable checks for a running Strata server")
    parser.add_argument("--url", default=os.environ.get("STRATA_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--api-key", default=os.environ.get("STRATA_API_KEY"))
    parser.add_argument("--model", default=None, help="default: the first model the server reports")
    # --url and friends may come before or after the subcommand (SUPPRESS keeps the first one)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", default=argparse.SUPPRESS)
    common.add_argument("--api-key", default=argparse.SUPPRESS)
    common.add_argument("--model", default=argparse.SUPPRESS)

    effort = argparse.ArgumentParser(add_help=False)
    effort.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high"), default="none",
                        help="thinking budget for this check (default none, so one run is short and comparable)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("models", help="what the server has loaded", parents=[common]).set_defaults(func=cmd_models)

    bench = sub.add_parser("bench", help="decode and prompt speed", parents=[common, effort])
    bench.add_argument("--prompt", choices=sorted(PROMPTS), default="short")
    bench.add_argument("--max-tokens", type=int, default=64)
    bench.add_argument("--repeat", type=int, default=1)
    bench.add_argument("--question", default=None, help="ask this instead of the built-in question")
    bench.set_defaults(func=cmd_bench)

    vision = sub.add_parser("vision", help="send one picture", parents=[common, effort])
    vision.add_argument("--image", default=None, help="default: a built-in 448x224 test picture")
    vision.add_argument("--question", default="What code is written at the top of the picture? "
                                             "Then name the colour of the circle and of the rectangle. One short line.")
    vision.add_argument("--max-tokens", type=int, default=320)
    vision.set_defaults(func=cmd_vision)

    queue = sub.add_parser("queue", help="fire several requests at once and see if they queue", parents=[common, effort])
    queue.add_argument("--count", type=int, default=2)
    queue.set_defaults(func=cmd_queue)

    sub.add_parser("plan", help="summarise `strata launch --plan --output json` from stdin", parents=[common]).set_defaults(func=cmd_plan)

    oc = sub.add_parser("opencode-config", help="write an OpenCode config for this server", parents=[common])
    oc.add_argument("--out", default=None)
    oc.add_argument("--context", type=int, default=131072)
    oc.set_defaults(func=cmd_opencode_config)

    args = parser.parse_args()
    try:
        return args.func(args)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")[:400]
        print(f"HTTP {error.code}: {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"cannot reach {args.url}: {error.reason}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
