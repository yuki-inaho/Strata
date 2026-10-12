# LLMオンボーディングサマリー — Strata (Qwen3.8-Flash-Next 推論環境)

> 本書は yuki-inaho の他リポジトリ [`agent-jsonl-compact`](https://github.com/yuki-inaho/agent-jsonl-compact) の
> `docs/ONBOARDING.md` の様式を参考に、このチェックアウトで作業する次のエージェント(または担当者)向けに
> 作成した初期資料です。各項目は 2026-10-12 の実作業に基づき、`確認済み` / `未検証` / `推定` を区別して記します。

## 1. プロジェクト概要と目的

- **プロジェクト名称・領域:** `Niko1221/Strata` — Qwen3.8-Flash-Next(125B MoE)を GPU + システム RAM で動かす
  ローカル推論エンジン。C++/CUDA エンジン(`src/`)・Python サーバーと OpenAI/Anthropic 互換 API(`serve/`)・
  ワンクリックインストーラ(`setup.py` / `setup.sh`)。本チェックアウトは yuki-inaho のフォーク(`origin` = 上流、`yuki` = 自分のフォーク)。
- **最終成果物:** `http://127.0.0.1:8080` で動くローカル推論サーバー(チャット/エージェント用途)と、
  コミュニティ共有用のベンチマークレポート(`bench/results/`)、作業記録(`diary/`)。
- **ビジネス背景・価値:** クラウドに送らず手元のマシンで高品質モデルをサービングする。本環境
  (VRAM 64GB + RAM 251GB)では最高品質の約 4bit 版(UD-Q4_K_XL)を実用速度(数十 tok/s)で動かせる。
- **進捗サマリ(2026-10-12、`確認済み`):** UD-Q4_K_XL セットアップ・稼働・ベンチ完了。
  ベンチ中央値: chat decode **64.6 tok/s**、agent セッション **71.4 tok/s**、16K prompt 読込 **2,123 tok/s**。
  PR #1518(DeepSeek-V4-Flash ポーティング)も試行: ビルド可・生成可・速度 0.30–0.59 tok/s(初期段階)。
  詳細: `diary/2026-10-12-qwen3.8-flash-next-ud-q4_k_xl-report.md` と `diary/2026-10-12-worklog.md`。

## 2. クリティカルな要求・制約

> 「壊してはいけない」品質・安全ライン。

- サーバーは既定で `127.0.0.1` のみ。**外部公開は `--host 0.0.0.0` と `--api-key <長いランダム秘密>` の同時指定が必須**
  (キーなし公開は禁止。AGENTS.md / docs/AI_SETUP.md).
- モデルは約 111GB。ディスク残量に注意(空き ~120GB を推奨)。セットアップは**再実行でレジューム**する。
- この環境は cgroup メモリ上限 139.4GiB があり、**ページキャッシュも使用量に算入される**。エンジン再起動時の
  RAM 常駐化(mlock)が失敗することがある → 不要な大ファイルのページキャッシュを `posix_fadvise(…, POSIX_FADV_DONTNEED)`
  で落とす、または数分待って再試行する(`確認済み`: これで復旧)。
- エンジン停止時、**orphan プロセスが VRAM を握り続ける**ことがある(`nvidia-smi --query-compute-apps` で PID を特定して kill)。
- Hugging Face は Xet 転送。`HF_XET_HIGH_PERFORMANCE=1` を使う(`HF_HUB_ENABLE_HF_TRANSFER` は非推奨)。
  長時間ダウンロードは `setsid` でプロセス分離(ツールのタイムアウトで巻き添えにしない)。
- `origin`(Niko1221/Strata)は **read-only として扱う**。変更はフォーク(remote `yuki`)へ。
- **秘密情報・個人情報をコミットしない。** diary/ 等へ収録する際はホームパス・ユーザー名・トークンを除去する。
- ライセンス(MIT、モデルは各配布元のライセンス)とクレジット表記を無断で変更しない。

## 3. 参照すべき合意済み資料

| 種別 | ファイル/リンク | 概要・用途 |
| --- | --- | --- |
| 運用ルール(最優先) | `AGENTS.md` | Strata の開発・インストール・報告の規約 |
| セットアップ手順 | `docs/AI_SETUP.md` | AI エージェント向け非対話セットアップの正本 |
| 設計・全数値 | `docs/DETAILS.md` | エンジンの仕組み、実測値、API、環境変数 |
| モデル選択 | `docs/MODELS.md` / `docs/UNSLOTH_Q4.md` | サイズ別要件、UD-Q4_K_XL / UD-IQ4_XS の詳細 |
| ベンチ | `bench.sh` / `tools/strata_bench.py` / `docs/COMMUNITY_BENCHMARKS.md` | 計測手順と共有フォーマット |
| 本環境の実測 | `bench/results/2026-10-12-community-cmp-170hx-qwen3-8-flash-next-unsloth-ud-q4-k-xl/README.md` | 公式フォーマットのベンチ結果(ローカルに存在) |
| 作業記録 | `diary/2026-10-12-*.md` | 本作業のレポートと Findings/Tips/Struggles 記録 |
| 上流の議論 | GitHub: `Niko1221/Strata` issues / PR #1518 | DeepSeek-V4-Flash ポーティング(未マージ・初期段階) |
| 様式の参考 | `yuki-inaho/agent-jsonl-compact` の `docs/ONBOARDING.md` | 本書の構成・文体の参考 |

## 4. タスク境界(任せること / 任せないこと)

### 任せるタスク(例)
- モデルの起動・停止・動作確認(`/health`, `/v1/chat/completions`)、tok/s の計測。
- 設定チューニング(`--prefill`, `--conversation-cache-mib`, `--expert-cache`, `--calibrate`)と A/B 計測。
- `bench.sh` の実行と `bench/results/` へのレポート追加、ドキュメント更新(`docs/`, `diary/`)。
- 追加モデルの導入(ディスク容量を確認した上で)、不具合の issue 化。

### 任せないタスク(例)
- API キーなしでのサーバー外部公開、トンネル/ポート転送の設置。
- 上流(`origin`)への無断 push・force-push、既存タグの付け替え。
- モデル・`Strata-data/`・キャッシュの無断削除(再 DL に数十分〜数時間かかる)。
- 無関係ファイルのコミット、秘密情報のコミット。

## 5. インタラクション方針

- **回答スタイル:** 日本語。技術用語・コマンドは原語のまま。見出し + 箇条書き。実測値は「何で測ったか」を添える。
- **回答手順:** 前提 → 論点 → 実行と検証。変更は最小差分で、検証コマンドの出力を添える。
- **禁止事項・注意:** 未確定を断定しない。`確認済み` / `未検証` / `推定` を区別する。
- **長時間タスク:** 進捗ログを残し、`Findings / Tips / Struggles` を定期的に記録する(diary/ の形式)。

## 6. 試行タスク(オンボーディング演習)

1. `curl -s http://127.0.0.1:8080/health` で `"loaded": true` を確認する。
   未起動なら `./run-unsloth-ud-q4_k_xl.sh` で起動(ロードに 1〜2 分)。
2. 短いチャットを投げ、レスポンスの `timings.predicted_per_second` で decode tok/s を確認する。
   1 回目のリクエストはウォームアップで遅い(キャッシュ適応に数リクエストかかる)。
3. `./bench.sh` を実行し、`bench/results/<日付>-community-*/README.md` が生成されることを確認する(約 133 秒)。
4. `nvidia-smi` で VRAM を確認する。本構成では稼働中は常時 ~64.5/65.5 GiB 使用が正常(空き ~390MiB)。

## 7. 運用ルール・変更管理

- **記録:** 作業単位で `diary/YYYY-MM-DD-<topic>.md` を追加する(個人情報は除去)。既存の `diary/` の文体に合わせる。
- **ドキュメント:** AGENTS.md のスタイル(平易な言葉、実測値には測定環境を添える)に従う。
- **ベンチ共有:** `bench/results/` のフォルダをそのまま PR / Issue に添付する(公式手順)。
  実行したベンチは README に「速さのみ・正しさは未検証」等の制約を明記する。
- **バージョン:** 上流の `v0.1.x` に追従。エンジンは `setup.sh` がソースビルドまで面倒を見る(要 CUDA toolkit)。
- **git:** `origin` = 上流(read-only)、`yuki` = 自分のフォーク。push はフォークへ。

---

### 付録 A: 実測クイックリファレンス(2026-10-12・`確認済み`)

環境: NVIDIA CMP 170HX(VRAM 64GiB, sm_80, ヘッドレス)/ EPYC 7663 56C112T / RAM 251GiB /
NVMe SSD / Linux コンテナ(cgroup 上限 139.4GiB)/ driver 610.57.04 / CUDA 12.6 ソースビルド。

| 項目 | 実測 | 備考 |
| --- | ---: | --- |
| chat decode | 64.6 tok/s(45.9–82.4, n=9) | 公式ベンチ中央値 |
| agent セッション decode | 71.4 tok/s(48.1–83.6, n=15) | 公式ベンチ中央値 |
| 4K prompt 読込 | 1,071 tok/s | 公式ベンチ |
| 16K prompt 読込 | 2,123 tok/s | 公式ベンチ |
| 22K prompt 読込 | 1,710 tok/s | 追加計測 |
| DSV4(PR #1518)CUDA decode | 0.30 tok/s | 未成熟カーネル |
| DSV4 CPU + `--expert-ram all` decode | 0.59 tok/s | 最良ケース |

構成の要点(`確認済み`): エンジンは 24,576 エキスパート中 19,070 個(約78%)を VRAM キャッシュへ自動配置し、
残りは page-locked RAM 16.08GiB + OS ページキャッシュでまかなう。`--prefill auto`・KV int8・32K コンテキスト・
MTP ドラフト有効・`STRATA_ROUTE_TAIL_SKIP=7`(既定 ON)。

### 付録 B: 主要コマンドと構成

- 起動 / 停止: `./run-unsloth-ud-q4_k_xl.sh` / プロセス終了(orphan VRAM に注意)
- 検証: `/health`, `/v1/models`, `/v1/chat/completions`(`timings.predicted_per_second` で tok/s)
- 設定ファイル: `strata-unsloth-ud-q4_k_xl.json`(`--pack` / `--native` / `--expert-profile` / `--expert-cache`
  / `--prefill` / `--spec` / `--mtp` / `--max-context` / `--kv` / `--resident-budget-gib` / `--conversation-cache-mib`)
- エンジン: `engine/strata`(ソースビルドは `build/`)。サーバー: `serve/server.py`。ベンチ: `./bench.sh`
- モデル実体: `Strata-data/`(モデル・パック・MTP。リポジトリ外に置ける)

### 付録 C: 既知の落とし穴(この環境)

- 起動直後は遅い(初回 28.7 tok/s → 数リクエストで 60〜80 tok/s に安定)。
- `--prefill auto:32768` は本構成ではエンジンが #669(借用スロットの毎チャンク再読込)警告を出し改善しない
  → `auto` のまま(`確認済み`、A/B 済み)。
- 再起動時の mlock OOM / orphan エンジンの VRAM 占有 / HF Xet 切替時の `.incomplete` 残骸。
- PR #1518 の dsv4 は GPU prefill chunk≥2 で logits が壊れる既知バグ → `--prefill-chunk 1` 必須。
  トークナイザは venv の python で実行(`regex` が必要)。
- DSV4 検証で Qwen を止めるときは、終了後にフォークのページキャッシュを追い出してから Qwen を再起動すると安全。

### 付録 D: 参考リンク

- `diary/2026-10-12-qwen3.8-flash-next-ud-q4_k_xl-report.md`(本作業のレポート)
- `diary/2026-10-12-worklog.md`(Findings / Tips / Struggles 形式の作業記録)
- `bench/results/2026-10-12-community-cmp-170hx-qwen3-8-flash-next-unsloth-ud-q4-k-xl/README.md`(公式ベンチ)
- <https://github.com/yuki-inaho/agent-jsonl-compact/blob/main/docs/ONBOARDING.md>(本書の様式の参考)
