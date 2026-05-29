# tablecodec — 実装ブリーフ

**バージョン:** 1.0
**最終更新:** 2026-05-28
**ステータス:** Active — このブリーフに従って実装を進める

---

## 0. このドキュメントの位置付け

このドキュメントは `tablecodec` を **SPEC.md に厳密に準拠した実装** に到達させるための作業指示書です。

| 文書 | 役割 | 優先度 |
|---|---|---|
| `SPEC.md` | 仕様の唯一の正典。挙動・契約・不変条件はここで定義 | 最高 |
| `IMPLEMENTATION_BRIEF.md` (本書) | 実装順序、技術選定、品質基準 | 高 |
| `ROOT_AGENTS.md` (dotfiles 由来) | コーディング標準、コミット規約、共通 lint ルール | 高 |
| `CONTRIBUTING.md` | 外部コントリビュータ向けガイド (M0 で作成) | 中 |

**矛盾が生じた場合、優先順位は `SPEC.md` > `IMPLEMENTATION_BRIEF.md` > `ROOT_AGENTS.md`** とする。SPEC を破る変更を提案する場合は、先に SPEC への PR を出して合意を取ること。

---

## 1. ミッション

`SPEC.md` §1〜§2 を参照。実装側の追加ミッションとして：

- 各マイルストーン完了時点で `main` ブランチが**常にリリース可能**な状態であること
- 第三者（Docling、PaddleOCR、社内パイプライン）が**読まずに動かせる**ドキュメント密度を維持すること
- パフォーマンス回帰を**コミット単位で検知**できる体制（M3 以降）

---

## 2. 運用原則

### 2.1 TDD: Red-Green-Refactor を厳守

Kent Beck の流儀に従う。例外なし：

1. **Red**: 失敗するテストを 1 件書く。コミットメッセージ `test(scope): describe failing case`
2. **Green**: 最小実装でテストを通す。コミットメッセージ `feat(scope): minimal impl`
3. **Refactor**: 振る舞いを変えずに構造を整える。コミットメッセージ `refactor(scope): tidy`

1 ステップ = 1 コミットを基本とする。複数ステップをまとめたコミットは PR レビューで reject 対象。

### 2.2 Tidy First

構造変更と振る舞い変更を**同じコミットに混ぜない**。リネーム、ファイル分割、import 整理は独立した tidy コミットとして提出。コミットメッセージは `refactor(scope): tidy first - <description>`。

### 2.3 Conventional Commits

`type(scope): subject` 形式を厳守。scope は概ね SPEC の章番号またはモジュール名 (`ir`, `codec`, `cli`, `ci` など)。

許可された type: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `build`, `ci`, `perf`.

### 2.4 1 PR = 1 マイルストーン以下

PR は M0/M1/... 単位、または同マイルストーン内の論理的に分離可能な単位で出す。1 PR に複数マイルストーンを詰め込むのは reject。

### 2.5 ROOT_AGENTS.md 準拠

社の dotfiles で定義された Semgrep meta-rules、justfile 規約、Conventional Commits フォーマッタ、`.yaml` 拡張子（`.yml` ではない）の規律はそのまま継承する。本ブリーフはそれらに**追加で**課す制約のみを記述する。

---

## 3. 技術選定（決定済み）

| 項目 | 選定 | 根拠 |
|---|---|---|
| Python 最小バージョン | **3.11** | PEP 604 (`int \| None`), `dataclass(slots=True)`, `Self` 型 |
| パッケージマネージャ | **uv** | 社の標準 |
| ビルドバックエンド | **hatchling** | uv との相性、シンプル |
| Lint | **ruff** | `ROOT_AGENTS.md` 準拠 |
| 型チェック | **pyright (strict)** | mypy より速く、推論が強い |
| テストランナー | **pytest** | デファクト |
| Property-based test | **hypothesis** | M1 の IR 不変条件テストで必須 |
| カバレッジ | **coverage.py** | pytest-cov 経由 |
| CLI フレームワーク | **click** | M6、`[cli]` extra でのみ依存 |
| タスクランナー | **just** | 社の標準 |
| CI | **GitHub Actions** | OSS デファクト |
| ライセンス | **MIT** | SPEC §16 で確定済み |

**コアパッケージ**は上記のうち `ruff`、`pyright`、`pytest`、`hypothesis`、`coverage` のみを **開発依存**として持つ。**ランタイム依存はゼロ**（SPEC §13）。

---

## 4. ターゲットリポジトリ構成

最終的に到達すべきレイアウト（M8 時点）：

```
tablecodec/
├── .github/
│   └── workflows/
│       ├── ci.yaml             # lint + type + test on push/PR
│       ├── benchmark.yaml      # M3 以降、パフォーマンス回帰検知
│       └── release.yaml        # tag push で PyPI 公開
├── docs/
│   ├── loss_matrix.md          # M5 で自動生成
│   └── format_support.md       # 各 codec の対応表
├── src/
│   └── tablecodec/
│       ├── __init__.py         # public API のみ re-export
│       ├── ir.py               # GridCell, TableSample, BBox
│       ├── _invariants.py      # I-01〜I-07 (private)
│       ├── validate.py         # validate(), profiles
│       ├── io.py               # open(), detect(), streaming utilities
│       ├── loss.py             # analyze_loss()
│       ├── cli.py              # click app (only in [cli] extra)
│       └── codecs/
│           ├── __init__.py     # registry: get(), register(), detect()
│           ├── _base.py        # Codec protocol
│           ├── pubtabnet.py    # pubtabnet-1.0.0, pubtabnet-2.0.0
│           ├── fintabnet.py
│           ├── otsl.py         # otsl-1.0.0
│           ├── tableformer.py
│           ├── doctags.py      # doctags-tables
│           ├── pubtables1m.py  # read-only
│           └── tablebank.py
├── tests/
│   ├── conftest.py
│   ├── strategies.py           # hypothesis strategies
│   ├── test_ir.py
│   ├── test_invariants.py
│   ├── test_invariants_hypothesis.py
│   ├── test_validate.py
│   ├── test_io_streaming.py
│   ├── test_loss.py
│   ├── test_cli.py
│   ├── codecs/
│   │   ├── test_pubtabnet.py
│   │   ├── test_otsl.py
│   │   └── ...
│   └── fixtures/
│       ├── pubtabnet/
│       ├── otsl/
│       └── ...
├── pyproject.toml
├── justfile
├── ruff.toml                   # またはpyproject.toml内
├── pyrightconfig.json
├── .gitignore
├── .pre-commit-config.yaml
├── semgrep.yaml                # 「コアに3rd party import 禁止」を強制
├── LICENSE                     # MIT
├── README.md
├── SPEC.md
├── IMPLEMENTATION_BRIEF.md
├── CONTRIBUTING.md
└── CHANGELOG.md                # Keep a Changelog 形式
```

---

## 5. マイルストーン

各マイルストーンは独立した PR として提出する。Acceptance Criteria が**すべて**緑になるまで次に進まない。

### M0 — Bootstrap（半日〜1日）

**Goal**: リポジトリの土台を整え、`just ci` が空のテスト一式に対してグリーンになる状態を作る。

**Deliverables**:
- `pyproject.toml` (hatchling, Python 3.11+, extras: `teds`, `cli`, `hf`, `all`, `dev`)
- `justfile` (targets: `install`, `test`, `lint`, `type`, `fmt`, `cov`, `ci`, `clean`)
- `ruff.toml`, `pyrightconfig.json`
- `.github/workflows/ci.yaml` (matrix: Python 3.11, 3.12, 3.13 / Ubuntu, macOS)
- `.gitignore`, `.pre-commit-config.yaml`
- `semgrep.yaml`: ルール「`src/tablecodec/` 配下で許可された stdlib モジュール以外の import を禁止」を含む
- `LICENSE` (MIT)
- `README.md` (最小限のあいさつと SPEC へのリンクのみ)
- `CONTRIBUTING.md` (TDD 必須、Conventional Commits、PR テンプレ)
- `CHANGELOG.md` (Unreleased セクションのみ)
- `src/tablecodec/__init__.py`: `__version__ = "0.0.1"` のみ
- `tests/test_smoke.py`: import と version assertion

**Acceptance Criteria**:
- [ ] `just ci` がローカルで成功
- [ ] CI が GitHub で緑
- [ ] `pip install -e .` が成功
- [ ] `semgrep --config semgrep.yaml src/` がノイズなく走る

**TDD ノート**: M0 は土台整備なので Red-Green-Refactor は test_smoke.py のみに適用。それ以外は構造変更コミット。

---

### M1 — Internal Representation（1〜2日）

**Goal**: SPEC §5 の IR と §5.2 の不変条件 I-01〜I-07 を実装し、property-based testing で網羅する。

**Deliverables**:
- `src/tablecodec/ir.py`: `BBox`, `GridCell`, `TableSample`
- `src/tablecodec/_invariants.py`: 各 I-XX を独立した関数として実装
- `src/tablecodec/validate.py`: `validate(sample, profile=...)`, `profiles.{LENIENT,DEFAULT,PUBTABNET_2_0,TABLEFORMER,STRICT}`
- `tests/strategies.py`: `gridcell_st`, `tablesample_st`, `valid_tablesample_st`
- `tests/test_ir.py`: dataclass の frozen / slots / hashable 性質
- `tests/test_invariants.py`: I-01〜I-07 を 1 関数 1 テストで網羅
- `tests/test_invariants_hypothesis.py`: 「valid な TableSample を生成 → すべての invariant がパス」「特定の invariant を壊した時、その invariant のみが失敗を報告」

**Acceptance Criteria**:
- [ ] I-01〜I-07 のすべてに positive / negative テストあり
- [ ] hypothesis が 10,000 ケース回って fail なし
- [ ] `TableSample` が pickle 可能、hashable、`__slots__` 持ち
- [ ] coverage 100%（`_invariants.py`, `ir.py`）
- [ ] pyright strict で warning ゼロ

**TDD 順序の指針**:
1. `test_ir.py::test_gridcell_is_frozen` を Red → `GridCell` の最小定義で Green
2. 同様に `TableSample` を進める
3. I-01 から順に Red → Green → Refactor を繰り返す
4. 全 invariant が個別関数で揃ってから `validate.py` を組み立てる
5. 最後に hypothesis テストで網羅

---

### M2 — First Codec: `pubtabnet-2.0.0`（2〜3日）

**Goal**: SPEC §6 の Codec 契約を確定し、最初の codec として `pubtabnet-2.0.0` を実装。

**Deliverables**:
- `src/tablecodec/codecs/_base.py`: `Codec` Protocol
- `src/tablecodec/codecs/__init__.py`: registry (`register`, `get`, `detect`, `list_codecs`)
- `src/tablecodec/codecs/pubtabnet.py`: `PubTabNet20Codec` (read + write)
- `tests/codecs/test_pubtabnet.py`: 単体テスト + round-trip + 損失申告検証
- `tests/fixtures/pubtabnet/`: 公式サンプル数件（PMC license 上問題なし、`exploring_PubTabNet_dataset.ipynb` の examples フォルダから借用、出典明記）

**Acceptance Criteria**:
- [ ] `codecs.get("pubtabnet-2.0.0").read(f)` がストリームで `TableSample` を yield
- [ ] read → write → read の往復で `lossy_read()` 申告以外のフィールドが完全一致
- [ ] HTML トークン列の rowspan/colspan パースが正しく `GridCell.rowspan/colspan` に反映
- [ ] 空セル（`bbox` 欠落）が `bbox=None` で表現される
- [ ] 巨大ファイル（10,000 件以上）で peak memory が定数（M3 で正式測定するが、M2 でも観察）
- [ ] `lossy_read()` と `lossy_write()` の申告が round-trip テストと一致

**TDD 順序**:
1. `Codec` Protocol を `_base.py` に置く
2. registry の `register/get` を Red → Green
3. `PubTabNet20Codec` のシンプルな単一サンプル read を Red → Green
4. rowspan/colspan のあるサンプルを追加 Red → Green
5. write を追加、round-trip テスト
6. lossy_* を実装、整合性テスト

---

### M3 — Streaming I/O と pubtabnet-1.0.0（1〜2日）

**Goal**: SPEC §10 のストリーミング保証を担保し、レガシー codec を追加。

**Deliverables**:
- `src/tablecodec/io.py`: `open(path, codec=None)`, `detect(source)`
- `src/tablecodec/codecs/pubtabnet.py`: `PubTabNet10Codec` を追加（bbox なし）
- `tests/test_io_streaming.py`: メモリ使用量がデータサイズに依存しないことを assert（`tracemalloc` で確認）
- `.github/workflows/benchmark.yaml`: pytest-benchmark で baseline 計測
- `docs/format_support.md`: 対応 codec 表（自動生成スクリプト含む）

**Acceptance Criteria**:
- [ ] 100,000 件の jsonl をストリーミング処理しても peak memory < 50MB
- [ ] `detect()` が先頭 5 行で codec 名を返す
- [ ] benchmark の baseline が `main` に commit される
- [ ] 1.0.0 と 2.0.0 が同じ jsonl で誤判定なく区別される

---

### M4 — OTSL Codec（2〜3日）

**Goal**: 異なる token language である OTSL を実装し、Codec 契約の汎用性を実証する。

**Deliverables**:
- `src/tablecodec/codecs/otsl.py`: `OTSL10Codec`
- `tests/codecs/test_otsl.py`: round-trip + IBM 公式 reference（`docling-ibm-models/tableformer/otsl.py`）との挙動一致テスト（テスト時のみ optional 依存）
- IBM の OTSL リファレンスを `[dev]` extra でインストールし、cross-validation テストを optional に実行

**Acceptance Criteria**:
- [ ] OTSL の 5 トークン語彙（`fcel`, `ecel`, `lcel`, `ucel`, `xcel` + `nl`）すべてが正しく解釈される
- [ ] square table assumption の検証ロジックを持つ
- [ ] OTSL → IR → OTSL のラウンドトリップが完全一致
- [ ] OTSL → IR → PubTabNet HTML の変換が SPEC §9 の loss 申告どおりに動作

**重要（2026-05-28 更新, ADR 0005 で改訂）**: 当初はクリーンルーム方針（IBM の `otsl.py` を逐語コピーせず論文から自前実装）だった。しかし live e2e で SynthTabNet の複雑な span 構造に対し自前 reconstruction が誤動作することが判明し（HTML 経路は同一テーブルを正しく解釈）、docling の `otsl_to_html` アルゴリズムを **帰属付きで適応移植**する方針に改めた。docling-ibm-models は私たち同様 **MIT**（Copyright (c) 2024 IBM）なので、著作権表示と MIT 文を保持すれば再利用可。帰属は `_otslgrid.py` ヘッダ・`THIRD_PARTY_NOTICES.md`・ADR 0005 に記録。ライセンスは MIT のまま（Apache 化は不要）。クリーンルームは依然デフォルトで、許諾ライセンス + 帰属記録 + core invariant 維持を満たす場合のみ適応移植を許す。

---

### M5 — Loss Analysis（1日）

**Goal**: SPEC §9 を実装。`tablecodec` の独自価値の核を完成させる。

**Deliverables**:
- `src/tablecodec/loss.py`: `analyze_loss(source: str, target: str) -> LossReport`
- `tests/test_loss.py`: 全 codec 組み合わせの分析が安定して動作
- `docs/loss_matrix.md`: スクリプトで自動生成、CI で更新が必須

**Acceptance Criteria**:
- [ ] `analyze_loss` が静的に動作（実データを読まずに codec の `lossy_*` メタから判定）
- [ ] `round_trip_classification` が `"lossless"` / `"structure-preserving"` / `"lossy"` を正しく返す
- [ ] loss_matrix.md がコミット差分なしで再生成可能

---

### M6 — CLI（1〜2日）

**Goal**: SPEC §12 の CLI サブコマンドを実装。

**Deliverables**:
- `src/tablecodec/cli.py`: click ベース、`[cli]` extra
- `pyproject.toml` の `[project.scripts]` に `tablecodec = "tablecodec.cli:main"`
- `tests/test_cli.py`: click の `CliRunner` で各サブコマンドを検証
- `README.md` に CLI セクション追加

**Acceptance Criteria**:
- [ ] `tablecodec validate` が validation failure で非ゼロ exit code
- [ ] `tablecodec convert --dry-run` がデータを読まずに loss レポートのみ返す
- [ ] `tablecodec stats` がストリーミングで動作
- [ ] CLI なしでも core が動く（`[cli]` extra が optional であることを CI で確認）

---

### M7 — Conformance Suite Skeleton（1〜2日）

**Goal**: 別リポジトリ `tablecodec/conformance` を立ち上げ、SPEC §11 の初期 fixtures を配置。

**Deliverables**:
- 別リポジトリ作成: `github.com/hironow/tablecodec-conformance`（個人 org 配下、後で `tablecodec` org に移行可能）
- `INDEX.json` の JSON Schema 定義
- 初期 fixtures: pubtabnet-2.0.0 と otsl-1.0.0 各 3 件以上
- `tablecodec` 本体側に `tests/test_conformance.py`: conformance リポジトリを git submodule または HF dataset として取得して通す

**Acceptance Criteria**:
- [ ] Conformance リポジトリが MIT で公開
- [ ] `INDEX.json` Schema が dereferenceable
- [ ] 本体側のテストが Conformance を取得して PASS

---

### M8 — Public Release（PyPI、**保留中**）

**方針変更（実行時の決定）**: 当初は M1-M8 を経て v0.1.0 で公開する計画だったが、
codec を 1 つずつ **0.0.x の patch bump** として出荷する方針に切り替えた（現在
0.0.10、9 codec すべて出荷済み）。PyPI 公開は人間側の Trusted Publishing 設定が
済むまで **保留**。手順は gitignore 下の `private/PYPI_RELEASE_STEPS.md`。

**Goal**: PyPI 公開、GitHub Release、告知（設定完了後）。

**Deliverables**:
- version は 0.0.x のまま（codec 追加 = patch bump、`pyproject.toml` +
  `src/tablecodec/__init__.py` を同期）
- リリース時に `CHANGELOG.md` の `[Unreleased]` を `[0.0.N]` へ昇格
- `.github/workflows/release.yaml`（`v*` タグで発火、Trusted Publishing / OIDC）
  — PyPI 側設定が済むまで inert
- README に installation / basic usage / SPEC リンク（済）
- （任意）GitHub Discussions / Issues テンプレート

**Acceptance Criteria（公開を実施する場合）**:
- [ ] `pip install tablecodec` が動作（core は zero-dep）
- [ ] `pip install "tablecodec[cli]"` が動作
- [ ] `import tablecodec; tablecodec.__version__` が現行 0.0.x と一致
- [ ] PyPI ページに README が正しく表示される
- [ ] GitHub の "About" 欄に SPEC リンクと一文の説明

---

## 6. アンチパターン（PR レビューで即 reject）

以下を含む PR は内容によらず reject、または該当箇所の修正を要求する：

| アンチパターン | 検出方法 |
|---|---|
| `src/tablecodec/` 配下に stdlib 以外の import（CLI/loss/io 除く） | semgrep meta-rule |
| `ir.py` または `_invariants.py` に Pydantic を持ち込む | semgrep |
| `pytest.mark.skip` をコメントなしで使う | ruff custom rule |
| `# type: ignore` をコメントなしで使う | pyright |
| 構造変更と振る舞い変更が同一コミットに含まれる | コードレビュー |
| 1 PR に複数マイルストーン | PR テンプレ + レビュー |
| Conventional Commits 違反 | commit lint |
| テストなしのバグ修正 | レビュー |
| jsonl 全体を `f.read()` でメモリにロード | semgrep meta-rule + コードレビュー |
| `numpy`, `pillow`, `opencv` のいずれかを core にコミット | semgrep meta-rule |
| 公式コード（IBM otsl.py 等）からの逐語コピー | ライセンスチェッカ + 人間レビュー |

---

## 7. Definition of Done（全マイルストーン共通）

マイルストーン PR を merge する前に、以下を**すべて**満たすこと：

- [ ] そのマイルストーンの Acceptance Criteria が全て✓
- [ ] `just ci` がローカルでグリーン
- [ ] GitHub Actions がグリーン（matrix 全組み合わせ）
- [ ] coverage が 95% 以上（M1 以降の新規モジュール）
- [ ] ruff、pyright strict が clean
- [ ] semgrep がノイズなく走る
- [ ] CHANGELOG.md に Unreleased エントリ追加
- [ ] Conventional Commits 違反なし
- [ ] PR description に SPEC のどのセクションを実装したか明記
- [ ] 公開 API を追加した場合、docstring と型ヒント完備

---

## 8. v1.0 へのロードマップ

**実績（0.0.x で達成済み）**: 当初は codec を 0.2.0〜0.4.0 の minor で追加する計画
だったが、実際には全 9 codec（pubtabnet 1.0/2.0、otsl、fintabnet、fintabnet-otsl、
tableformer、tablebank、pubtables-1m、doctags-tables）を **0.0.x の patch bump** で
出荷した（現在 0.0.16）。TEDS extra は 0.0.16 で実装済み（`tablecodec.teds`、
ADR 0011）。docling bridge は未着手。

v1.0 までの残作業：

| バージョン | 内容 |
|---|---|
| 0.0.x（継続） | docling bridge (`tablecodec-docling`)、Open Questions §17 の解消、Conformance Suite を別 repo へ抽出（ADR 0001） |
| 0.0.x | PyPI 公開（M8、Trusted Publishing 設定後） |
| 0.9.0 | Public API freeze、RC1 |
| **1.0.0** | API frozen、3 年 LTS スタート |

各バージョンで Conformance Suite を拡充する。

---

## 9. 質問・例外申請

実装中に SPEC で曖昧な点や、本ブリーフのルールを破る必要が生じた場合：

1. **小規模な疑義**: Linear のチケットコメントで議論し、決定を SPEC または本書の更新 PR に反映
2. **SPEC を変更する必要がある場合**: 先に `SPEC.md` への PR を出し、merge 後に実装に着手
3. **本ブリーフのルールを一時的に緩める必要**: PR description に明記し、レビュアの明示的な承認を得る（例：M1 で型ヒントの一部省略を許可、など）

「黙って迂回する」「コメントなしで例外を作る」は禁止。

---

## 10. 環境セットアップ（着手前に1回だけ）

```bash
# Prerequisites
brew install just uv  # mise でも可

# Repo clone & setup
git clone https://github.com/hironow/tablecodec
cd tablecodec
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev,cli,teds]"

# Pre-commit
uv pip install pre-commit
pre-commit install --install-hooks

# 動作確認
just ci
```

`just ci` が緑になれば着手可能。

---

## 11. 着手順序（推奨）

1. **本書と SPEC.md を熟読** — 不明点を Linear にチケット化
2. **M0 を着手** — リポジトリの土台を確実に
3. **M0 の PR を merge してから M1** — 早期に CI 緑を実現
4. M1 → M2 → ... と順番に
5. 各マイルストーン完了時に Linear のチケットをクローズし、CHANGELOG を更新

**並行作業は M5 と M6 以降のみ許容**（依存関係が独立しているため）。M0〜M4 は厳密に逐次。

---

## 付録 A: justfile テンプレート（M0 で作成）

```just
default:
    @just --list

install:
    uv pip install -e ".[dev,cli,teds]"

test:
    pytest tests/ -v

lint:
    ruff check src/ tests/
    ruff format --check src/ tests/

type:
    pyright src/

fmt:
    ruff format src/ tests/
    ruff check --fix src/ tests/

cov:
    pytest tests/ --cov=tablecodec --cov-report=term-missing --cov-report=html

semgrep:
    semgrep --config semgrep.yaml src/

ci: lint type test semgrep
    @echo "✓ All checks passed"

clean:
    rm -rf .pytest_cache .ruff_cache htmlcov .coverage dist build *.egg-info
    find . -type d -name __pycache__ -exec rm -rf {} +
```

---

## 付録 B: semgrep.yaml のコアルール例（M0 で作成）

```yaml
rules:
  - id: no-third-party-imports-in-core
    pattern-either:
      - pattern: import pydantic
      - pattern: from pydantic import ...
      - pattern: import numpy
      - pattern: import PIL
      - pattern: from PIL import ...
      - pattern: import cv2
      - pattern: import pandas
    paths:
      include:
        - src/tablecodec/ir.py
        - src/tablecodec/_invariants.py
        - src/tablecodec/validate.py
        - src/tablecodec/io.py
        - src/tablecodec/codecs/_base.py
        - src/tablecodec/codecs/pubtabnet.py
        - src/tablecodec/codecs/otsl.py
        # cli.py, loss.py は extra で許容するため除外
    message: |
      Core modules must not depend on third-party packages. See SPEC.md §13.
    severity: ERROR
    languages: [python]

  - id: no-full-file-read
    pattern-either:
      - pattern: $F.read()
      - pattern: $F.readlines()
    paths:
      include:
        - src/tablecodec/io.py
        - src/tablecodec/codecs/
    message: |
      Codecs and io must stream. Full-file reads violate SPEC.md §10.
    severity: WARNING
    languages: [python]
```

---

## 付録 C: 推奨される最初のコミット 5 件（M0）

```
chore: initial empty repository                              # README, LICENSE
build: pyproject.toml, hatchling, Python 3.11+               # 設定のみ
build(ci): justfile and GitHub Actions skeleton              # CI 土台
chore(lint): ruff, pyright, semgrep configurations           # lint 設定
test(smoke): verify package imports and exposes version      # 最初のテスト
```

これで M0 完了。M1 への着手はここから。

---

**このブリーフは生きたドキュメントです。マイルストーン完了時にレビューし、必要に応じて更新の PR を出してください。**
