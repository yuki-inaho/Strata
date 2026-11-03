# 作業手順書: 8GB カードで Strata 0.2.10 を起動して opencode まで繋ぐ (2026-11-03)

> 個人情報・ローカルパスを除去して diary/ に収録 (2026-11-03)。結果の要約は
> [2026-11-03 の作業記録](2026-11-03-rtx2070-8gb-gyro-s-0.2.10.md) にある。
> ここでは別の機体でも同じ結果を出せるように、手順と確認点を順番に並べる。数値は RTX 2070 8GB、
> RAM 24.5GB、NVMe の実測で、そのまま期待値として使える。

## 0. 前提

| 項目 | この手順の前提 |
| --- | --- |
| GPU | NVIDIA 8GB（この記録は sm_75。sm_86 以上でも手順は同じ） |
| RAM | 24.5GB（8GB カード 1 枚に対する下限に近い。増やすほど速くなる） |
| ディスク | 空き 100GB 以上（モデル 58.5GB、パック 26GB、ドラフト 0.8GB） |
| OS | Linux x86_64。NVIDIA ドライバは CUDA 12 なら 575.51 以上、CUDA 13 なら 580.65 以上 |
| ネット | 初回だけ必要（エンジン 668MB とモデル 59.4GB） |

起動の条件は、VRAM と RAM の合計がモデルの実メモリ以上あることだ。足りない分は SSD から読むので、
起動はするが遅くなる。8GB と 24.5GB の組み合わせでは、Qwen3.8-Flash-Next 系で警告なしに収まるのは
Gyro-S (27.6GB) だけだった。

## 1. 環境を確認する

```sh
nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader
awk '/MemTotal|MemAvailable/{print $1, $2/1048576 " GB"}' /proc/meminfo
df -h ~ | tail -1
```

期待する出力の例は `NVIDIA GeForce RTX 2070, 8192 MiB, 7.5`、MemTotal 23.4GiB、空き 600GB 超。
compute_cap が 7.5 でも CUDA 13 パッケージに sm_75 のコードが入っているので、自分でビルドする必要はない。

## 2. Terminal を入れる

```sh
curl -fsSL https://github.com/Niko1221/Strata/releases/latest/download/install.sh -o install.sh
sh install.sh
export PATH="$HOME/.local/bin:$PATH"
strata --version          # 例: strata 0.2.10 (build 0.1.56; python 3.12.x ...)
strata doctor             # terminal_cli と monitor_tui が ok
```

管理者権限は要らない。`~/.local/share/strata/terminal/<version>` に入り、`~/.local/bin/strata` が
張られる。インストーラは署名とハッシュを確かめてから切り替えるので、途中で失敗しても半端な状態は残らない。

## 3. モデルを選ぶ

```sh
strata launch --plan --family qwen --model iq3_s     # 8GB/24.5GB では "does not fit" の警告
strata launch --plan --model gyro-s                  # 警告なし。これを採用する
```

`--plan` はダウンロードも起動もせず、モデル、context、drafter、ダウンロード量、fit 判定を出す。
機械可読が要るときは `--output json` を付ける（`plan.download.parts`、`plan.warnings`、`plan.drafting`）。

この機体で見た判定は次のとおり。

| モデル | ダウンロード | 判定 |
| --- | ---: | --- |
| IQ3_S | 84GB | does not fit |
| IQ2_XS | 68GB | does not fit |
| Q2_0 | 66GB | does not fit |
| Gyro-M | 92GB | tight fit（他のプログラムを閉じる） |
| Gyro-S | 58.5GB | 警告なし（採用） |

## 4. 起動する

```sh
strata launch --model gyro-s --family gyro --context 128k \
  --vision cpu --drafting auto --tune skip --yes --no-tui
```

`--vision cpu` は画像リーダーを CPU で動かす指定だ。8GB カードでは `--vision on` でも CPU が選ばれる。
`--drafting auto` は Qwen3.8 系なら DFlash2 を選ぶ。DFlash2 は 1 リクエスト専用なので、slot も 1 に固定される。
`--tune skip` は初回のチューニングを省く。`--no-tui` は画面を開かず、アドレスを出して戻る。
サーバはそのまま残る。

所要時間の目安は次のとおり。

| 段階 | 時間 |
| --- | --- |
| エンジンの取得、検証、切り替え | 約 1 分（668MB） |
| モデル 59.4GB のダウンロード | 約 30 分（35〜43MB/s、中断しても再開する） |
| experts のパック作成（26GB） | 数分 |
| DFlash2 の取得と変換（1.2GB から 0.52GB） | 1〜2 分 |
| ロード | 15 秒 |

終わると次のように出る。

```
Ready: http://127.0.0.1:8080
Engine log  ~/.local/state/strata/launch/gyro-s-128k.engine.log
[!] DFlash2 answers one request at a time, so Strata set this model to one request at a time.
```

## 5. 起動を確認する

```sh
strata launch --status
curl -sS http://127.0.0.1:8080/v1/models
strata status --url http://127.0.0.1:8080 --json
strata logs --follow
```

`/v1/models` の `meta.n_ctx` が 131072、`status.value` が loaded なら意図どおり起動している。
あわせてエンジンログで次の行を確かめる。左が実際にこの機体で出た値だ。

| ログ行 | 意味 | 実測値 |
| --- | --- | --- |
| `KV streaming: N of 131072 cells ... K/V in X GiB of pinned RAM` | context を縮めず、VRAM 側の窓だけ段を下げる | 20,480 / 1.55GiB |
| `expert cache ... -> N slots` | VRAM に常駐する expert の数 | 445（24,576 中 1.8%） |
| `short of GPU memory: ... the loan keeps 16` | プロンプト経路の借りスロットを縮小 | 256 トークン刻み |
| `prefill plan: ... about X GB read ... per 32768-token prompt` | 長文 1 本あたりの SSD 読み込み予測 | 3,346.6GB |
| `WARNING: only N MiB of VRAM free` | 512MiB を切ると driver が VRAM を page する | 504MiB（`--vram-reserve-mib 704` を推奨） |
| `--draft dflash2: ... 625 MiB`、`no MTP layer is loaded` | ドラフターは 1 本だけ | DFlash2 のみ |

## 6. 計測する

`tools/probe_client.py` が計測、画像、同時リクエストをまとめて受け持つ。標準ライブラリだけで動くので、
どの Python 3.8 以降でも実行できる。Justfile のレシピからも同じことをできる。

```sh
python3 tools/probe_client.py bench --url http://127.0.0.1:8080 --prompt short --max-tokens 64
python3 tools/probe_client.py bench --url http://127.0.0.1:8080 --prompt 2k --max-tokens 128
just bench short 64          # 同じことを just で
```

期待値は次のとおり。計測は思考を切ってある（`--reasoning-effort none` が既定）。

| 入力 | 結果 |
| --- | --- |
| 60 トークン | 54 生成 / 5.8s = 9.4 tok/s |
| 1,653 トークン | 36.2s で読み込み（45.7 tok/s）、生成 8.2 tok/s、SSD 25.1GB |
| 17,948 トークン | 481s で読み込み（37.3 tok/s）、生成 10.5 tok/s |
| 同じ 2 ターン目 | 18,050 を再利用し、45 だけ読んで 3.4s、生成 11.8 tok/s |

最初の 1 本は page cache が空なので必ず遅い。比較は 2 本目以降で行う。正確な値はエンジンログの
`prompt N tokens = R reused + P read in X ms (...), G generated in Y ms (...)` を使う。
回答の `content` が空で `reasoning_content` だけのときは、思考でトークンを使い切っている。
`max_tokens` を増やすか、`--reasoning-effort none` を付ける。

## 7. 画像を試す

```sh
just vision                       # 組み込みのテスト画像（CODE 4217、赤丸、青四角）
just vision path/to/picture.png   # 自分の画像
```

この機体では 7.0 秒で `CODE 4217; circle: red, rectangle: blue` と答えた。CPU リーダーなので
1 枚目だけモデルの読み込みが入る。2 枚目以降で測るとよい。

## 8. 同時リクエストを試す

```sh
just queue 2
```

DFlash2 では slot が 1 なので、`serialized: requests ran one after another` と出て、1.9 秒と 3.3 秒のように
順番に終わる。失敗はしない。複数を同時にさばきたいときは MTP に切り替える。

```sh
strata launch --model gyro-s --family gyro --context 64k --drafting mtp --parallel 2 --yes --no-tui
```

MTP 層（約 5.2GB）を追加でダウンロードする。先に `--plan --drafting mtp --parallel 2` で確認できる。

## 9. opencode に繋ぐ

まず Terminal 側の自己チェックを実行する。

```sh
just opencode-check      # strata connect opencode --check と同じ
```

checks が 2 件とも ok なら、prompt と tool call は通っている。この機体では prompt が 7.1 秒で "pong"、
tool call が 21.9 秒で `get_weather {"city":"Paris"}` を返した。ok が false のときは error に理由が出る。

次に設定ファイルを書く。グローバル設定（`~/.config/opencode/opencode.json`）は触らず、検証用の
フォルダに置く。

```sh
just opencode-config /path/to/project
```

出力は `strata connect opencode` の設定と同じ形で、`limit.output` だけ 4096 から 16384 に上げてある。
4096 のままだと長いセッションで compaction が切れる（issue #5006）。OpenCode 2.1.3 では
`npm`、`options`、`tool_call` という旧フィールド形でもプロバイダが登録できた。登録されないときは
`package`、`settings`、`capabilities` の新しい形も試す（#4528 の報告形）。

`opencode models | grep strata` で `strata/<model>` が出ることを確かめてから実行する。

```sh
mkdir -p notes && printf 'The access code for the greenhouse door is ZX-4419.\n' > notes/key.txt
just opencode-run /path/to/project "Read the file notes/key.txt and reply with only the access code."
```

この機体では `→ Read notes/key.txt` のあと `ZX-4419` と答え、全体で 8 分 44 秒かかった。内訳は
1 回目の prefill が 481 秒（17,948 トークン、37.3 tok/s）、2 回目が 18,050 トークンの再利用で 3.4 秒。
opencode のシステムプロンプトとツール定義だけで約 7.4K トークン使うので、RAM の少ない機体では
この長さがそのまま初回の待ち時間になる。スクリプトや ssh から実行するときは `< /dev/null` を付ける。

## 10. 止める

```sh
strata launch --stop
strata launch --status        # 何も出なければ止まっている
du -sh ~/.local/share/strata/Strata-data   # 合計 82GB 程度
```

内訳はモデル 55GB、パック 26GB、DFlash2 0.8GB。ディスクを戻すときは `Strata-data` ごと削除してよい。
次回の起動で再取得と再パックが走る。設定を残すときは起動時に `--save-preset <名前>` を付ける。

## 11. 困ったとき

| 症状 | 原因と対処 |
| --- | --- |
| プランが does not fit と言う | VRAM と RAM が足りない。Gyro-S に落とす。context を下げても重みは減らない |
| `only N MiB of VRAM free` の警告 | `--vram-reserve-mib 704` を付ける。context か parallel を下げる |
| `Loading the model…` で止まる | `strata logs` とエンジンログを見る。`strata launch --stop` のあと再実行する（パックは再利用される） |
| 回答の content が空 | 思考が reasoning_content に出ている。max_tokens を増やすか思考を切る |
| 同じ質問が毎回 3 倍遅い | 1 本目は page cache が空。2 本目以降で比較する |
| 長いプロンプトが異常に遅い | 想定内。prefill plan の SSD 読み込み予測を見る。RAM を増やすかプロンプトを短くする |
| compaction で output token limit になる | #5006。limit.output を 16384 以上にする |
| opencode がモデルを出さない | 設定ファイル名（opencode.jsonc）とフィールド形を確認する。#4528 と #5006 を参照 |

## 12. 別の機体に当てるとき

RAM が 32GB 以上あるなら、Gyro-S のままでも expert の常駐が増えて decode が上がる。まず `just plan` で
確認する。RAM 64GB 以上で VRAM 12GB 以上なら IQ3_S (84GB) が候補になる。VRAM 16GB 以上なら
`--vision gpu` も選べる。複数カードで Linux なら、sm_86 か sm_120 の 2 枚、または R9700 の 4 枚で
all-cards split が Auto で選ばれる（`docs/SPLIT_ENGINE.md`）。それ以外は layer split と DFlash2 になる。
並列を優先するときは `--drafting mtp --parallel N` にする。

## 13. 再現できたかの確認

- [ ] `strata --version` が 0.2.10 / 0.1.56
- [ ] `just plan` で選んだモデルに警告が出ない
- [ ] `/v1/models` の n_ctx が要求した context（ここでは 131072）
- [ ] エンジンログに `KV streaming: ... of 131072` と `expert cache ... slots` がある
- [ ] 暖機後の decode が 8〜12 tok/s、prefill が 35〜46 tok/s
- [ ] `just vision` が CODE 4217 と色を答える
- [ ] `just opencode-check` が 2 件とも ok
- [ ] `just opencode-run` でツール呼び出しのあと正答する
- [ ] `strata launch --stop` で止まり、`--status` が空になる

## 参考

- [作業記録 (2026-11-03)](2026-11-03-rtx2070-8gb-gyro-s-0.2.10.md)
- [2026-10-12 の作業記録](2026-10-12-worklog.md)（大きい VRAM 機で Qwen3.8 を測ったときの記録）
- `docs/TERMINAL_LAUNCH.md`、`docs/TERMINAL_QUICKSTART.md`、`docs/GYRO.md`、`docs/SPLIT_ENGINE.md`
- issue: #5006（open、OUTPUT_CAP 4096）、#4528（closed、cannot reproduce）
