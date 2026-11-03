# Strata: portable checks and runs
#
# `just` lists the recipes. `just verify` looks at the machine and the Terminal
# without starting a model. The rest talk to a running server, or start one.
# Every value can be overridden from the environment, for example:
#
#     STRATA_MODEL=iq3_s STRATA_CONTEXT=64k just launch
#     STRATA_URL=http://127.0.0.1:9000 just models
#
# The checks need only Python 3.8 or newer and the standard library. A model is
# not required for verify, plan, test-setup or report.
set shell := ["sh", "-c"]

default_model   := env_var_or_default("STRATA_MODEL", "gyro-s")
default_family  := env_var_or_default("STRATA_FAMILY", "gyro")
default_context := env_var_or_default("STRATA_CONTEXT", "128k")
default_port    := env_var_or_default("STRATA_PORT", "8080")
default_url     := env_var_or_default("STRATA_URL", "http://127.0.0.1:" + default_port)
default_key     := env_var_or_default("STRATA_API_KEY", "")
default_python  := env_var_or_default("PYTHON", "python3")

strata := env_var_or_default("STRATA_BIN", "strata")
probe  := "tools/probe_client.py"

# List the recipes
default:
    @just --list

# Machine, Terminal components and a dry-run plan; nothing is started or downloaded
verify:
    @printf '== Terminal ==\n'
    @{{strata}} --version
    @printf '\n== components ==\n'
    @{{strata}} doctor --output json | {{default_python}} -c 'import json,sys; d=json.load(sys.stdin); print("ok" if d.get("ok") else "not ok"); [print("  %-14s %s" % (c["name"], c["status"])) for c in d["report"]["components"]]'
    @printf '\n== hardware ==\n'
    @(nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader 2>/dev/null || echo "no NVIDIA card in nvidia-smi")
    @awk '/MemTotal|MemAvailable/ {printf "%-12s %.1f GB\n", $1, $2/1048576}' /proc/meminfo 2>/dev/null || true
    @df -h . | tail -1
    @printf '\n== plan (%s %s, %s) ==\n' "{{default_model}}" "{{default_family}}" "{{default_context}}"
    @{{strata}} launch --plan --model {{default_model}} --family {{default_family}} --context {{default_context}} --output json | {{default_python}} {{probe}} plan

# Print the plan in plain words (model=, context= to change it)
plan model=default_model context=default_context:
    {{strata}} launch --plan --model {{model}} --family {{default_family}} --context {{context}}

# Start a model and return (extra= adds flags, for example '--parallel 2')
launch model=default_model context=default_context extra="":
    {{strata}} launch --model {{model}} --family {{default_family}} --context {{context}} --vision cpu --drafting auto --tune skip --yes --no-tui {{extra}}

# What is running, and what the server says it has loaded
status:
    @{{strata}} launch --status
    @{{default_python}} {{probe}} models --url {{default_url}}

# Stop what `just launch` started
stop:
    {{strata}} launch --stop

# Follow the Terminal's log (Ctrl-C detaches, the server keeps running)
logs:
    {{strata}} logs --follow

# Loaded model, context and status as one line
models:
    {{default_python}} {{probe}} models --url {{default_url}}

# Decode and prompt speed for one prompt (short, 2k or 8k)
bench prompt="short" max_tokens="64" repeat="1":
    {{default_python}} {{probe}} bench --url {{default_url}} --prompt {{prompt}} --max-tokens {{max_tokens}} --repeat {{repeat}}

# The short, 2k and 8k prompts one after another
bench-all:
    @just bench short 64
    @just bench 2k 128
    @just bench 8k 128

# Send one picture (a built-in test picture unless image= is given)
vision image="":
    @if [ -n "{{image}}" ]; then {{default_python}} {{probe}} vision --url {{default_url}} --image "{{image}}"; else {{default_python}} {{probe}} vision --url {{default_url}}; fi

# Fire several requests at once and report whether they overlapped or queued
queue count="2":
    {{default_python}} {{probe}} queue --url {{default_url}} --count {{count}}

# Write an OpenCode config for this server (output cap raised for issue #5006)
opencode-config dir=".":
    {{default_python}} {{probe}} opencode-config --url {{default_url}} --out "{{dir}}/opencode.jsonc"

# The Terminal's own check: one prompt and one tool call, the way OpenCode sends them
opencode-check:
    {{strata}} connect opencode --check

# Run one OpenCode task against the server (dir= the project folder)
opencode-run dir="." task="Read notes/key.txt in this folder and reply with only the access code.":
    @m=$(cd "{{dir}}" && opencode models | grep '^strata/' | head -1); \
     test -n "$m" || { echo "no strata provider in {{dir}}/opencode.jsonc; run: just opencode-config {{dir}}" >&2; exit 1; }; \
     cd "{{dir}}" && opencode run --model "$m" --auto "{{task}}" < /dev/null

# Bundle versions, status and the last checks into one tarball (out= the folder)
report out="":
    @dir="{{out}}"; \
     if [ -z "$dir" ]; then dir=$(mktemp -d "${TMPDIR:-/tmp}/strata-report-XXXXXX"); else mkdir -p "$dir"; fi; \
     {{strata}} --version > "$dir/version.txt" 2>&1 || true; \
     {{strata}} doctor --output json > "$dir/doctor.json" 2>&1 || true; \
     {{strata}} launch --status > "$dir/launch-status.txt" 2>&1 || true; \
     {{strata}} status --url {{default_url}} --json > "$dir/server.json" 2>&1 || true; \
     {{default_python}} {{probe}} models --url {{default_url}} > "$dir/models.txt" 2>&1 || true; \
     (nvidia-smi > "$dir/nvidia-smi.txt" 2>&1 || true); \
     if [ "${STRATA_REPORT_LOGS:-0}" = "1" ]; then cp ${XDG_STATE_HOME:-$HOME/.local/state}/strata/launch/*.engine.log "$dir/" 2>/dev/null || true; fi; \
     tar -czf "$dir.tgz" -C "$dir" . && echo "$dir.tgz"

# Run the setup tests (file= the name after test_setup_, or all for every file)
test-setup file="choices":
    @if [ "{{file}}" = "all" ]; then \
       fails=0; total=0; \
       for f in tools/test_setup_*.py; do total=$((total+1)); \
         if ! {{default_python}} "$f" >/tmp/strata-setup-test.log 2>&1; then echo "FAIL $f"; fails=$((fails+1)); fi; \
       done; \
       echo "$((total-fails))/$total setup tests passed"; \
       test "$fails" -eq 0; \
     else \
       {{default_python}} tools/test_setup_{{file}}.py; \
     fi

# The Terminal and Control tests (needs pytest in PYTHON; point PYTHON at the Terminal's own python)
test-terminal:
    {{default_python}} -m pytest tests/terminal -q
