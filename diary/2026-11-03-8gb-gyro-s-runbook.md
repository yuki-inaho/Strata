# 作業手順書: 8GB カードで Strata 0.2.10 を起動して opencode まで繋ぐ (2026-11-03)

> 個人情報・ローカルパスを除去して diary/ に収録 (2026-11-03)。
> [2026-11-03 の作業記録](2026-11-03-rtx2070-8gb-gyro-s-0.2.10.md) の結果を、別の機体でも同じように
> 再現できる形に落としたもの。数値は RTX 2070 8GB / RAM 24.5GB / NVMe の実測で、期待値として使える。

## 0. 対象と前提

| 項目 | この手順の前提 |
| --- | --- |
| GPU | NVIDIA 8GB（この記録は sm_75 / Turing。sm_86 以上でも同じ手順） |
| RAM | 24.5GB（8GB カード 1 枚に対する下限級。増やすほど速くなる） |
| ディスク | 空き 100GB 以上（モデル 58.5 + パック 26 + ドラフト 0.8） |
| OS | Linux x86_64、NVIDIA ドライバ 575.51 以上（CUDA 12） / 580.65 以上（CUDA 13） |
| ネット | 初回だけ必要（エンジン 668MB + モデル 59.4GB） |

VRAM と RAM の合計が **モデルの実メモリ以上**あることが起動の条件。足りない分は SSD 読みになる
（起動はするが遅い）。8GB + 24.5GB では Qwen3.8-Flash-Next 系のうち **Gyro-S (27.6GB)** だけが警告なしで通る。

## 1. 環境チェック（変更なし）

```sh
nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader
awk '/MemTotal|MemAvailable/{print $1, $2/1048576 " GB"}' /proc/meminfo
df -h ~ | tail -1
```

期待値の例: `NVIDIA GeForce RTX 2070, 8192 MiB, 7.5` / MemTotal 23.4GiB / 空き 600GB 超。
`compute_cap` が 7.5 でも CUDA 13 パッケージに sm_75 が入っているので追加ビルドは不要。

## 2. Terminal のインストール

```sh
curl -fsSL https://github.com/Niko1221/Strata/releases/latest/download/install.sh -o install.sh
sh install.sh
export PATH="$HOME/.local/bin:$PATH"
strata --version          # 例: strata 0.2.10 (build 0.1.56; python 3.12.x ...)
strata doctor             # terminal_cli / monitor_tui が ok
```

- 管理者権限不要。`~/.local/share/strata/terminal/<version>` に入り、`~/.local/bin/strata` が張られる。
- 失敗時は何も残らない設計（署名とハッシュを検証してから切り替え）。

## 3. モデル選定（プランで決める）

```sh
strata launch --plan --family qwen --model iq3_s     # 8GB/24.5GB では "does not fit" 警告
strata launch --plan --model gyro-s                  # 警告なし → これを採用
```

`--plan` は何もダウンロードせず、モデル・context・drafter・ダウンロード量・fit 判定を出す。
機械可読が要るときは `--output json`（`plan.download.parts`、`plan.warnings`、`plan.drafting` を見る）。

この機体の判定（実測）:

| モデル | ダウンロード | 判定 |
| --- | ---: | --- |
| IQ3_S | 84GB | does not fit |
| IQ2_XS | 68GB | does not fit |
| Q2_0 | 66GB | does not fit |
| Gyro-M | 92GB | tight fit（他のプログラムを閉じることを推奨） |
| **Gyro-S** | **58.5GB** | **警告なし（採用）** |

## 4. 起動

```sh
strata launch --model gyro-s --family gyro --context 128k \
  --vision cpu --drafting auto --tune skip --yes --no-tui
```

- `--vision cpu`: 8GB カードでは画像リーダーを CPU で動かす（`on` でも 24GB 未満なら CPU が選ばれる）。
- `--drafting auto`: Qwen3.8 系では DFlash2。1 リクエスト専用なので slot も 1 に固定される。
- `--tune skip`: 初回のチューニングを省く（この機体では時間の無駄。後で `--tune quick` も可）。
- `--no-tui`: 画面を開かず、アドレスを出して戻る（サーバは残る）。

所要時間の目安（実測）:

| 段階 | 時間 |
| --- | --- |
| エンジン取得〜検証〜切替 | 約 1 分（668MB） |
| モデル 59.4GB のダウンロード | 約 30 分（35〜43MB/s、中断しても再開） |
| experts のパック作成（26GB） | 数分 |
| DFlash2 の取得と変換（1.2GB→0.52GB） | 1〜2 分 |
| ロード | 15 秒 |

完了すると次のように出る:

```
Ready: http://127.0.0.1:8080
Engine log  ~/.local/state/strata/launch/gyro-s-128k.engine.log
[!] DFlash2 answers one request at a time, so Strata set this model to one request at a time.
```

## 5. 起動確認（ここで異常を早く見つける）

```sh
strata launch --status
curl -sS http://127.0.0.1:8080/v1/models
strata status --url http://127.0.0.1:8080 --json
strata logs --follow            # 実行ログ（--source harness でクライアント側）
```

`/v1/models` の `meta.n_ctx` が **131072**、`status.value` が `loaded` であること。

エンジンログで必ず確認する行（この機体の実値）:

| ログ行 | 意味 | この機体 |
| --- | --- | --- |
| `KV streaming: N of 131072 cells ... K/V in X GiB of pinned RAM` | context は縮めず、VRAM 側の窓だけ段を下げる | 20,480 / 1.55GiB |
| `expert cache ... -> N slots` | VRAM に常駐する expert 数 | 445（24,576 中 1.8%） |
| `short of GPU memory: ... the loan keeps 16` | プロンプト経路の借りスロット縮小 | 256 トークン刻み |
| `prefill plan: ... about X GB read ... per 32768-token prompt` | 長文 1 本あたりの SSD 読み予測 | 3,346.6GB |
| `WARNING: only N MiB of VRAM free` | 512MiB 未満だと driver が VRAM を page する | 504MiB（`--vram-reserve-mib 704` 推奨） |
| `--draft dflash2: ... 625 MiB`, `no MTP layer is loaded` | ドラフターは 1 本だけ | DFlash2 のみ |

## 6. 計測（スクリプトは下に全文）

```sh
printf 'Write one short sentence about a greenhouse.\n' > short.txt
python3 bench.py http://127.0.0.1:8080 qwen3.8-flash-next-gyro-gyro-s short.txt 64
python3 bench.py http://127.0.0.1:8080 qwen3.8-flash-next-gyro-gyro-s prompt2k.txt 320
```

期待値（暖機後、この機体）:

| 入力 | 結果 |
| --- | --- |
| 60 トークン | 54 生成 / 5.8s = **9.4 tok/s** |
| 1,653 トークン | 36.2s で読込（45.7 tok/s）、生成 8.2 tok/s、SSD 25.1GB |
| 17,948 トークン | 481s で読込（37.3 tok/s）、生成 10.5 tok/s |
| 同 2 ターン目 | 18,050 再利用 → 45 読み 3.4s、生成 11.8 tok/s |

- **最初の 1 本は必ず遅い**（page cache が空）。比較は 2 本目以降で行う。
- 正確な値はエンジンログの `prompt N tokens = R reused + P read in X ms (...), G generated in Y ms (...)` を使う。
- `content` が空で `reasoning_content` だけのときは、`max_tokens` を増やす（思考で使い切っている）。

### bench.py

```python
#!/usr/bin/env python3
"""Measure one chat completion against a Strata server: TTFT, decode speed, token counts.
Usage: bench.py URL MODEL PROMPT_FILE MAX_TOKENS [--stream]"""
import json, sys, time, urllib.request

url, model, prompt_file, max_tokens = sys.argv[1:5]
stream = "--stream" in sys.argv
body = {"model": model, "messages": [{"role": "user", "content": open(prompt_file).read()}],
        "max_tokens": int(max_tokens), "temperature": 0, "stream": stream}
if stream:
    body["stream_options"] = {"include_usage": True}
req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
start = time.time(); first = None; text = []; usage = {}
with urllib.request.urlopen(req, timeout=3600) as response:
    if not stream:
        payload = json.load(response)
        text = [payload["choices"][0]["message"].get("content") or ""]
        usage = payload.get("usage") or {}
    else:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            event = json.loads(chunk)
            if event.get("usage"):
                usage = event["usage"]
            for choice in event.get("choices") or []:
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    first = first or time.time()
                    text.append(piece)
end = time.time()
completion = usage.get("completion_tokens") or 0
decode = end - (first or start)
print(json.dumps({"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": completion,
                  "wall_s": round(end - start, 2), "ttft_s": round(first - start, 2) if first else None,
                  "decode_tok_s": round(completion / decode, 2) if completion and decode > 0 else None,
                  "answer_head": "".join(text)[:200].replace("\n", " ")}, ensure_ascii=False))
```

### vision.py（画像 1 枚）

```python
#!/usr/bin/env python3
"""Send one picture to a Strata server (OpenAI chat completions, image_url data URL)."""
import base64, json, sys, time, urllib.request

url, model, image_path = sys.argv[1:4]
question = sys.argv[4] if len(sys.argv) > 4 else "Read the code in the picture, say the colour of each shape."
body = {"model": model, "messages": [{"role": "user", "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(open(image_path, "rb").read()).decode()}}]}],
        "max_tokens": 320, "temperature": 0}
req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
start = time.time()
with urllib.request.urlopen(req, timeout=1800) as response:
    payload = json.load(response)
usage = payload.get("usage") or {}
message = payload["choices"][0]["message"]
print(json.dumps({"wall_s": round(time.time() - start, 1), "prompt_tokens": usage.get("prompt_tokens"),
                  "completion_tokens": usage.get("completion_tokens"),
                  "answer": (message.get("content") or "")[:300]}, ensure_ascii=False))
```

期待値: 896x448 の「CODE 4217 + 赤丸 + 青四角」で **15.9 秒 / 「4217: red, blue」**（CPU リーダー）。
1 枚目だけモデルの読み込みが入るので、2 枚目以降で測る。

## 7. 同時リクエスト（slot の確認）

```sh
# 2 本を同時に投げる（どちらも「Name one fruit in one word.」など短いもの）
python3 - <<'PY'
import json, threading, time, urllib.request
def ask(tag, out):
    body = {"model": "qwen3.8-flash-next-gyro-gyro-s",
            "messages": [{"role": "user", "content": "Name one fruit in one word."}],
            "max_tokens": 40, "temperature": 0}
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        json.load(r)
    out[tag] = round(time.time() - start, 1)
start = time.time(); out = {}
ts = [threading.Thread(target=ask, args=(i, out)) for i in (1, 2)]
[t.start() for t in ts]; [t.join() for t in ts]
print(out)
PY
```

期待値: DFlash2 では slot=1 なので **8.6s / 13.0s** のように直列化する（失敗はしない）。
複数同時にさばきたいときは MTP を選ぶ:

```sh
strata launch --model gyro-s --family gyro --context 64k --drafting mtp --parallel 2 --yes --no-tui
```

MTP 層（約 5.2GB）を追加でダウンロードする。`--plan --drafting mtp --parallel 2` で先に確認できる。

## 8. opencode 連携

### 8.1 ツール側の自己チェック

```sh
strata connect opencode --check --output json
```

期待値: `checks` が 2 件とも `ok`（この機体: prompt 7.1 秒で "pong"、tool call 21.9 秒で
`get_weather {"city":"Paris"}`）。`ok` が false なら `error` に理由が出る。

### 8.2 設定（#5006 の回避込み）

`strata connect opencode` が印字する設定はそのまま使えるが、**既定の `limit.output: 4096` は
長いセッションで compaction を壊す**（未解決 issue #5006）。次のように `output` を 16384 に上げる。
グローバル設定（`~/.config/opencode/opencode.json`）は触らず、検証用フォルダの `opencode.jsonc` に置く。

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "strata/qwen3.8-flash-next-gyro-gyro-s",
  "small_model": "strata/qwen3.8-flash-next-gyro-gyro-s",
  "autoupdate": false,
  "compaction": { "auto": true, "buffer": 24576 },
  "share": "disabled",
  "provider": {
    "strata": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Strata (local)",
      "options": { "baseURL": "http://127.0.0.1:8080/v1", "apiKey": "strata-local" },
      "models": {
        "qwen3.8-flash-next-gyro-gyro-s": {
          "name": "Qwen3.8-Flash-Next Gyro-S (local)",
          "tool_call": true,
          "reasoning": true,
          "limit": { "context": 131072, "input": 114688, "output": 16384 }
        }
      }
    }
  }
}
```

- OpenCode 2.1.3 ではこの旧フィールド形（`npm` / `options` / `tool_call`）でも登録できた。
  `opencode models | grep strata` で `strata/qwen3.8-flash-next-gyro-gyro-s` が出ることを確認する。
- 出ないときは V2 形（`package` / `settings` / `capabilities`）も試す（#4528 の報告形）。
- `limit.output` を上げたら `limit.input` は `context - output` に、`compaction.buffer` は
  `context - input` 相当（ここでは 24576）に合わせる。

### 8.3 実走

```sh
cd <検証用フォルダ>
mkdir -p notes && printf 'The access code for the greenhouse door is ZX-4419.\n' > notes/key.txt
opencode models | grep strata
time opencode run --model strata/qwen3.8-flash-next-gyro-gyro-s --auto \
  "Read the file notes/key.txt in this folder and reply with only the access code." < /dev/null
```

期待値: `→ Read notes/key.txt` のあと **`ZX-4419`**。この機体で **8 分 44 秒**。

| 内訳 | 実測 |
| --- | --- |
| 1 回目（システムプロンプト込み 17,948 トークン） | prefill 481s（37.3 tok/s）、生成 10.5 tok/s |
| 2 回目（ツール結果 18,095 トークン） | 18,050 再利用、45 読み 3.4s、生成 11.8 tok/s |

- `strata connect` の説明どおり、初回は npm プラグイン取得で 1 分以上かかることがある。
- スクリプトや ssh では `< /dev/null` を付ける（付けないと入力待ちで止まる）。
- opencode のシステムプロンプト + ツールで **約 7.4K トークン**を使う。RAM の少ない機体では
  これがそのまま初回 prefill の長さになる。

## 9. 停止と後片付け

```sh
strata launch --stop          # 起動したものを止める
strata launch --status        # 何も出なければ停止済み
du -sh ~/.local/share/strata/Strata-data   # 合計 82GB 程度
```

内訳: `models/gyro-Gyro-S` 55GB、`packs` 26GB、`dflash2` 0.8GB。
ディスクを戻すときは `Strata-data` ごと削除してよい（再起動時に再取得・再パック）。
設定を残したいときは起動時に `--save-preset <名前>` を付ける（次回 `--preset <名前>`）。

## 10. トラブルシュート

| 症状 | 原因 / 対処 |
| --- | --- |
| プランが `does not fit` | VRAM+RAM 不足。Gyro-S に落とす。`--context` を下げても重みは減らない |
| `only N MiB of VRAM free` 警告 | `--vram-reserve-mib 704` を付ける、または context / parallel を下げる |
| 起動が `Loading the model…` で止まる | `strata logs` とエンジンログを見る。`strata launch --stop` 後に再実行（パックは再利用） |
| 答えの `content` が空 | 思考が `reasoning_content` に出ている。`max_tokens` を増やす |
| 同じ質問が毎回 3 倍遅い | 1 本目は page cache が空。2 本目以降で比較する |
| 長いプロンプトが異常に遅い | 想定内。`prefill plan` の SSD 読み予測を見る。RAM を増やすかプロンプトを短くする |
| compaction で `reached the output token limit` | #5006。`limit.output` を 16384 以上にする |
| opencode がモデルを出さない | 設定ファイル名（`opencode.jsonc`）とフィールド形を確認。#4528 / #5006 を参照 |

## 11. 別の機体に適用するときの分岐

- **RAM 32GB 以上**: 同じ Gyro-S で expert の常駐が増え、decode が上がる。まず `--plan` で確認。
- **RAM 64GB 以上 / VRAM 12GB 以上**: IQ3_S (84GB) が候補。`strata launch --plan --family qwen --model iq3_s`。
- **VRAM 16GB 以上 / RAM 64GB 以上**: `--vision gpu` も選べる（24GB 未満は CPU が既定）。
- **複数カード（Linux）**: 2 枚の sm_86 / sm_120 か 4 枚の R9700 なら all-cards split が Auto で選ばれる
  （`docs/SPLIT_ENGINE.md`）。それ以外は layer split + DFlash2。
- **並列を優先**: `--drafting mtp --parallel N`。DFlash2 は 1 リクエスト専用。

## 12. 再現性チェックリスト

- [ ] `strata --version` が 0.2.10 / 0.1.56
- [ ] `--plan` で選んだモデルに警告が出ない
- [ ] `/v1/models` の `n_ctx` が要求した context（ここでは 131072）
- [ ] エンジンログに `KV streaming: ... of 131072` と `expert cache ... slots` がある
- [ ] 暖機後の decode が 8〜12 tok/s（この機体）、prefill が 35〜46 tok/s
- [ ] 画像 1 枚が正しく読める（CPU リーダー）
- [ ] `strata connect opencode --check` が 2 件とも ok
- [ ] `opencode run` でツール呼び出し→正答
- [ ] `strata launch --stop` で停止、`--status` が空

## 参考

- [作業記録 (2026-11-03)](2026-11-03-rtx2070-8gb-gyro-s-0.2.10.md)
- [2026-10-12 の作業記録](2026-10-12-worklog.md)（大きい VRAM 機での Qwen3.8 の測り方）
- `docs/TERMINAL_LAUNCH.md`、`docs/TERMINAL_QUICKSTART.md`、`docs/GYRO.md`、`docs/SPLIT_ENGINE.md`
- issue: #5006（open, OUTPUT_CAP 4096）、#4528（closed, cannot reproduce）
