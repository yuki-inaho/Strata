# Community benchmark on NVIDIA CMP 170HX

Measured on 2026-10-12 with `tools/strata_bench.py` (suite 1, 3 runs per test, medians with ranges). Speeds are the engine's own timings; first-token times are measured by the client over HTTP. Speed only: no correctness check was run.

## Hardware and software

- GPU and VRAM: NVIDIA CMP 170HX, 64 GiB VRAM
- CPU: AMD EPYC 7663 56-Core Processor (56 cores, 112 threads); installed RAM: 251.5 GiB; storage: not measured
- OS: Linux 6.8.0-138-generic; GPU driver: 610.57.04; CUDA: not read
- Strata: project 0.1.43, commit 7695859a; engine 0.1.43
- Background workloads and power limits: not recorded

## Model and configuration

- Model and quantization: qwen3.8-flash-next-unsloth-ud-q4_k_xl
- Context: 32768 tokens; parallel slots: 1
- Settings: the install's own configuration, unchanged; thinking off for the suite; temperature 0

```text
strata --pack unsloth-ud-q4_k_xl --native Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf --expert-profile expert-profile.bin --expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5 --mtp rt --max-context 32768 --kv int8 --resident-budget-gib 71
```

## Method

Run by `python tools/strata_bench.py` against the HTTP API of a Strata server (already running); model loading is not timed. One warm-up chat and a 1K prompt are discarded first. Every prompt starts with a unique tag, so the conversation cache cannot help the fresh-prompt tests.

- short chat: the three questions of `tools/ab_engine.py`, up to 100 new tokens, 3 runs
- 4K / 16K prompts: generated word lists sized by a calibration request, 24 new tokens, 3 fresh prompts each
- agent session: system prompt and four tools, then 5 turns that each add about 1500 words of a project file and continue from the model's own earlier answers (the way agent clients resend a conversation), 64 new tokens per turn, 3 sessions; the cache numbers come from the answer's usage (`cached_tokens`) and timings (`prompt_n`)
- concurrency (when run): N requests sent at the same moment, total tokens over the wall time of the burst, latency over all requests

## Results

| Configuration | Actual prompt tokens | Reused tokens | Generated tokens | Runs | Prompt tok/s median and range | Decode tok/s median and range | TTFT seconds median and range |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| short chat | 46 (43-51) | 0 | 100 (100-100) | 9 | not measured | 64.6 (45.9-82.4) | 0.52 (0.47-0.56) |
| 4K prompt, fresh | 4019 (4019-4019) | 0 (0-0) | 24 cap | 3 | 1071.0 (1020.1-1072.5) | not measured | 3.77 (3.77-3.96) |
| 16K prompt, fresh | 16058 (16058-16058) | 0 (0-0) | 24 cap | 3 | 2123.2 (2090.6-2130.7) | not measured | 7.59 (7.57-7.71) |
| agent session, follow-up turns | 14455 (14450-14474) at the last turn | see below | up to 64 | 3 | see below | 71.4 (48.1-83.6) | 3.54 (3.21-3.85) |

Ranges are the lowest and highest of the runs; `Runs` counts requests that returned a token.

### Agent session (conversation cache)

Cache hit over the follow-up turns: 68.8 % (68.6-68.8); earlier-turn tokens read again per session: 3 (3-74) (earlier turns that the cache did not hold; the 13633 (13633-13635) new tokens of the files are read once); first turn (nothing cached) first token: 2.05 s (1.98-2.16).

| Turn (run 1) | Prompt tokens | Reused | Read | Prompt tok/s | First token (s) | Decode tok/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 609 | 0 | 609 | 284.0 | 2.164 | 38.1 |
| 1 | 3701 | 620 | 3081 | 834.3 | 3.722 | 57.7 |
| 2 | 5234 | 3764 | 1470 | 453.7 | 3.304 | 57.3 |
| 3 | 8678 | 5298 | 3380 | 883.8 | 3.854 | 48.1 |
| 4 | 11602 | 8741 | 2861 | 770.9 | 3.744 | 72.3 |
| 5 | 14450 | 11604 | 2846 | 781.1 | 3.679 | 58.2 |

Per-request data: `results.json`. Engine log lines from the start: `engine-log-excerpt.txt` (when this run started the server).

## Correctness and limitations

Not measured: this is a speed suite. The conversation uses the model's own replies, so token counts differ a little between runs. Machine details come from the server, `nvidia-smi`/`rocm-smi` and the OS; background load and power limits are not recorded. Total time of the suite: 133 s.
