# Plan 002: Add the phase-1 QA ingest workflow from selected articles to weighted FastGPT admission

> **Executor instructions**: Use `gpt-5.4-mini` or an equivalent smaller implementation model for the code work. Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**:
>
> ```bash
> git diff --stat 603d249..HEAD -- main.py fastgpt_sync.py agents/ tests/ .env.example README.md README.en.md tests/README.md qa_agent_3phase_design.md qa_tagging_design.md
> ```
>
> This repo already has uncommitted work. If any in-scope file changed after this plan was written, compare the "Current state" excerpts below against the live code before proceeding; on a mismatch that changes the public API or phase-1 flow, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED — integrates the QA agent into upload-related CLI paths, but keeps failed/low-quality content from auto-uploading.
- **Depends on**: `plans/001-phase1-qa-tag-score-pipeline.md`
- **Category**: direction
- **Planned at**: commit `603d249`, 2026-06-16

## Why this matters

Plan 001 built the phase-1 QA/tag/scoring core, but the user-facing workflow still uploads Markdown files directly without the required admission path. The requested phase-1 product path is: **人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库**. This plan adds a concrete CLI workflow for manually selected local articles: evaluate them with the QA agent, persist structured QA reports, write enriched Markdown with tags/QA metadata, and upload only reports that pass the score/grade gate with FastGPT metadata carrying the入库权重.

This remains phase-1 only. Do not build multi-agent orchestration, recommendation, scheduling, full platform workflows, or automatic low-score override behavior.

## Current state

### Product requirements from design docs

- `qa_tagging_design.md:4` — each imported article should get 8–10 display tags.
- `qa_tagging_design.md:295-315` — the design doc describes article processing through tags, QA, scoring, and JSON output.
- `qa_tagging_design.md:319-345` — tag quality affects QA usability; no separate complex tag score in phase 1.
- `qa_tagging_design.md:351-401` — expected JSON contains `display_tags`, `structured_tags`, `qa_pairs`, `qa_score`, `grade`, `library_action`, `qa_weight`, `score_detail`, and `deduction_reasons`.
- `qa_tagging_design.md:406-417` — phase-1 requirements: `display_tags` and `structured_tags` are required, display tags count is 8–10, tags must come from the article, must not be marketing/overclaiming, and the core flow is `人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库`.

### Existing QA agent core

`agents/qa_agent.py` already encodes the phase-1 flow and rubric-backed report fields:

```python
# agents/qa_agent.py:0-8
"""知识库一期 QA 整理 Agent。

一期核心流程：人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库。

设计目标：
- 单一 Agent + 提示词，不引入多 Agent 框架。
- 评分与标签规则来自 YAML rubric，便于后续迭代。
- 默认使用 DashScope OpenAI 兼容接口，模型 qwen3.7-max。
"""
```

`QAReport` has phase-1 primary fields:

```python
# agents/qa_agent.py:32-54
@dataclass
class QAReport:
    """单篇文章的一期 QA 整理报告。"""

    identifier: str
    qa_score: int
    passed: bool
    grade: str
    library_action: str = "询问"
    qa_weight: float = 0.0
    title: str = ""
    article_id: str = ""
    article_type: str = ""
    domain: str = "medical"
    display_tags: list[str] = field(default_factory=list)
    structured_tags: dict = field(default_factory=dict)
    qa_pairs: list[dict] = field(default_factory=list)
    score_detail: dict[str, int] = field(default_factory=dict)
    summary: str = ""
    deduction_reasons: list[str] = field(default_factory=list)
    redlines: list[dict] = field(default_factory=list)
    version: str = "v0.1"
    raw: Optional[dict] = field(default=None, repr=False)
```

Compatibility note: `score` exists as an alias, but `tags` and `dimensions` aliases described in Plan 001 are not present yet. If legacy callers need them, add them in this plan while you touch the report model.

```python
# agents/qa_agent.py:56-63
# 兼容旧测试/旧调用：report.score
@property
def score(self) -> int:
    return self.qa_score

@score.setter
def score(self, value: int):
    self.qa_score = value
```

The QA agent evaluates content but is not wired into upload commands:

```python
# agents/qa_agent.py:110-120
def evaluate(self, content: str, identifier: str = "<unknown>") -> QAReport:
    """对文章执行一期流程，返回结构化报告。"""
    redlines = self.redline_checker.check(content)
    user_prompt = self.rubric.build_prompt(content)
    raw_text = self._call_llm(user_prompt)
    parsed = self._parse_json(raw_text)
    return self._build_report(identifier, parsed, raw_text, redlines)

def should_upload(self, report: QAReport) -> bool:
    """综合分达到阈值且权重大于 0 才允许自动上传。"""
    return report.qa_score >= self.threshold and report.qa_weight > 0
```

### Existing CLI uploads bypass QA

`main.py` currently exposes upload commands without a QA gate:

```python
# main.py:94-103
# 4. upload-file
p_upload_file = subparsers.add_parser('upload-file', help='上传单个文件')
p_upload_file.add_argument('--file', required=True, help='文件路径')
p_upload_file.add_argument('--dataset-id', required=True, help='目标知识库 ID')

# 5. upload-folder
p_upload_folder = subparsers.add_parser('upload-folder', help='上传整个文件夹')
p_upload_folder.add_argument('--folder', required=True, help='文件夹路径')
p_upload_folder.add_argument('--dataset-id', required=True, help='目标知识库 ID')
p_upload_folder.add_argument('--extensions', default='.md,.txt', help='文件扩展名（逗号分隔）')
```

`cmd_upload_file` uploads directly:

```python
# main.py:316-328
syncer = FastGPTSyncer(base_url, api_key, args.dataset_id)

with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    TaskProgressColumn(),
    console=console
) as progress:
    task = progress.add_task("上传文件...", total=1)
    result = syncer.upload_file(str(file_path))
    progress.update(task, completed=1)
```

`download-and-clean` currently has only 3 stages; QA admission is absent:

```python
# main.py:542-570
# 阶段 1: 下载
console.print("[bold]阶段 1/3: 下载文章[/bold]\n")
...
# 阶段 2: 清理
console.print("[bold]阶段 2/3: 清理文章[/bold]\n")
```

### Existing FastGPT upload metadata is hard-coded empty

`fastgpt_sync.py` hard-codes `metadata: {}` in the local file upload payload:

```python
# fastgpt_sync.py:101-152
def upload_file(self, file_path: str,
               collection_name: Optional[str] = None) -> str:
    ...
    data_payload = {
        "datasetId": self.dataset_id,
        "parentId": collection_id,
        "trainingType": "chunk",
        "chunkSize": 512,
        "chunkSplitter": "",
        "qaPrompt": "",
        "metadata": {}
    }
```

This must become optional metadata so `qa_score`, `grade`, `library_action`, `qa_weight`, `display_tags`, and `structured_tags` can travel with the uploaded file.

### Existing frontmatter utilities

`FrontmatterDoctor` standardizes frontmatter and normalizes tags. Reuse the repo's YAML/frontmatter style instead of inventing another format:

```python
# cleaners/frontmatter_doctor.py:257-260
def _assemble(self, frontmatter: Dict[str, Any], body: str) -> str:
    """重新组装 frontmatter 和正文"""
    fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f"---\n{fm_yaml}---\n\n{body}"
```

### Repo conventions and verification baseline

- Python CLI project; no `pyproject.toml` yet.
- Style: small modules, direct functions/classes, Chinese comments/docstrings, `pathlib`, `dataclass`, `yaml`, deterministic pytest tests.
- Existing tests are offline and must not call real LLM or FastGPT.
- Verified baseline during planning: `python3 -m pytest -q` → `40 passed in 0.33s`.
- Recent commit style: `feat: add multi-language readmes, tests, and project docs`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run all tests | `python3 -m pytest` | exit 0, all tests pass |
| Run QA tests | `python3 -m pytest tests/test_qa_agent.py -v` | exit 0 |
| Run new workflow tests | `python3 -m pytest tests/test_qa_ingest.py -v` | exit 0 |
| Run FastGPT wrapper tests | `python3 -m pytest tests/test_fastgpt_sync.py -v` | exit 0 |
| Dry-run QA ingest | `python3 main.py qa-ingest --input /tmp/qa_sample.md --output /tmp/qa-output --report-dir /tmp/qa-reports --dry-run` | exit 0; prints phase-1 summary; no upload |
| Import check | `python3 -c "from agents.qa_ingest import QAIngestResult, process_selected_article; print('ok')"` | prints `ok` |

## Scope

**In scope** (the only files you should modify/create):

- `agents/qa_agent.py` — add missing compatibility aliases only if needed by tests/callers.
- `agents/qa_ingest.py` (create) — pure workflow functions/classes for article → QA report → enriched Markdown → optional upload decision.
- `agents/__init__.py` — export the new workflow symbols if useful.
- `fastgpt_sync.py` — add optional metadata support to `upload_file` and `upload_folder` without changing default behavior.
- `main.py` — add a `qa-ingest` command and optionally wire QA as an explicit opt-in flag for `download-and-clean` only if the new command is already stable.
- `tests/test_qa_ingest.py` (create) — offline unit tests for the workflow.
- `tests/test_fastgpt_sync.py` (create) — offline tests for payload metadata using mocked HTTP/session behavior.
- `tests/test_qa_agent.py` — add alias tests if you add `tags` / `dimensions` properties.
- `tests/README.md` — document new tests and manual dry-run command.
- `README.md` and `README.en.md` — document the new phase-1 command briefly.
- `.env.example` — add report/output defaults only if you introduce corresponding env vars.

**Out of scope**:

- Do not change the default behavior of existing `upload-file`, `upload-folder`, or `download-and-clean` unless the operator explicitly asks for automatic QA gating there.
- Do not upload failed/low-quality reports automatically. No `--force` in this phase-1 plan.
- Do not add multi-agent architecture, queues, databases, schedulers, web UI, recommendation, or ranking beyond `qa_weight` metadata.
- Do not perform real LLM or FastGPT network calls in tests.
- Do not modify `cleaners/` or `fetchers/` unless a tiny import-only helper is impossible; prefer a new `agents/qa_ingest.py` module.
- Do not commit, push, or open a PR unless the operator explicitly instructs you.

## Git workflow

- Branch: use the current branch unless the operator instructs otherwise.
- Commit style if asked to commit later: conventional-ish short messages, e.g. `feat: add phase1 qa ingest workflow`.
- Do not push or open a PR unless instructed by the operator.

## Steps

### Step 1: Repair QAReport compatibility aliases while preserving phase-1 primary fields

In `agents/qa_agent.py`, add read/write compatibility properties if they are absent:

- `tags` mirrors `display_tags`.
- `dimensions` mirrors `score_detail`.
- `suggestions` can mirror `deduction_reasons` if any old tests/callers still expect it.

Do not change the primary schema: `display_tags`, `structured_tags`, `qa_pairs`, `qa_score`, `grade`, `library_action`, `qa_weight`, `score_detail`, `deduction_reasons`, and `version` remain authoritative.

Add tests in `tests/test_qa_agent.py`:

- `report.tags == report.display_tags` and assigning `report.tags = [...]` updates `display_tags`.
- `report.dimensions == report.score_detail` and assigning `report.dimensions = {...}` updates `score_detail`.

**Verify**:

```bash
python3 -m pytest tests/test_qa_agent.py -v
```

Expected: all QA agent tests pass.

### Step 2: Create a pure `agents/qa_ingest.py` workflow module

Create `agents/qa_ingest.py`. Keep it deterministic and testable. Do not import `rich` here; leave terminal rendering to `main.py`.

Suggested data model:

```python
@dataclass
class QAIngestResult:
    source_path: str
    report_path: str
    output_path: str
    uploaded: bool
    upload_result: str
    passed: bool
    qa_score: int
    grade: str
    library_action: str
    qa_weight: float
    display_tags: list[str]
```

Required functions:

1. `load_markdown_files(input_path: str | Path, extensions: tuple[str, ...] = ('.md', '.txt')) -> list[Path]`
   - If input is a file, return `[file]` if suffix matches.
   - If input is a directory, recursively return matching files sorted by path.
   - Raise `FileNotFoundError` for missing input.
   - Raise `ValueError` if no matching files are found.

2. `build_qa_frontmatter(report: QAReport) -> dict`
   - Return serializable frontmatter metadata:
     - `qa_score`, `qa_grade`, `qa_library_action`, `qa_weight`, `qa_version`
     - `display_tags`
     - `structured_tags`
     - `qa_summary`
     - `qa_pairs`
     - `qa_deduction_reasons`
   - Do not include `raw` LLM text in frontmatter.

3. `merge_frontmatter(content: str, report: QAReport) -> str`
   - Preserve existing frontmatter keys where possible.
   - Set/overwrite `tags` to `report.display_tags` because existing repo frontmatter uses `tags`.
   - Add the `qa_*` fields above.
   - Use `yaml.dump(..., allow_unicode=True, sort_keys=False, default_flow_style=False)` to match `FrontmatterDoctor` style.
   - Keep body content unchanged except for reassembling frontmatter.

4. `build_fastgpt_metadata(report: QAReport) -> dict`
   - Return compact metadata for FastGPT upload:
     - `qa_score`, `qa_grade`, `qa_library_action`, `qa_weight`, `display_tags`, `structured_tags`, `qa_version`.
   - Keep values JSON-serializable.

5. `process_selected_article(path: Path, agent: KnowledgeBaseQAAgent, output_dir: Path, report_dir: Path, syncer: FastGPTSyncer | None = None, dry_run: bool = False) -> QAIngestResult`
   - Read Markdown.
   - If `dry_run` is true, do not call `agent.evaluate`; instead use a deterministic local placeholder report only for CLI plumbing tests? Prefer not to fake production output in the module. Better: expose a CLI `--dry-run` that prints what would be processed without calling this function. Unit tests can pass a fake agent.
   - Call `agent.evaluate(content, identifier=str(path))`.
   - Write report JSON to `report_dir / f"{path.stem}.qa.json"`.
   - Write enriched Markdown to `output_dir / path.name`.
   - If `syncer is None`, set `uploaded=False`, `upload_result='not_configured'`.
   - If `syncer is not None` and `agent.should_upload(report)` is true, call `syncer.upload_file(str(output_path), collection_name=report.title or path.stem, metadata=build_fastgpt_metadata(report))`.
   - If `syncer is not None` and report does not pass, do not upload; set `upload_result='skipped_by_qa'`.
   - Never upload `D` / `不建议入库` reports.

6. `process_selected_articles(input_path, agent, output_dir, report_dir, syncer=None) -> list[QAIngestResult]`
   - Use `load_markdown_files`.
   - Ensure output/report directories exist.
   - Process files in sorted order.

**Verify**:

```bash
python3 -c "from agents.qa_ingest import QAIngestResult, load_markdown_files, build_fastgpt_metadata; print('ok')"
```

Expected: `ok`.

### Step 3: Add offline tests for the QA ingest workflow

Create `tests/test_qa_ingest.py` with fake agent and fake syncer classes. Do not call real LLM or FastGPT.

Minimum tests:

1. `test_load_markdown_files_accepts_single_file`
   - Create `tmp_path / 'a.md'`; assert returned list is `[path]`.

2. `test_load_markdown_files_sorts_directory`
   - Create `b.md`, `a.md`, and `ignore.jpg`; assert sorted Markdown paths only.

3. `test_merge_frontmatter_adds_phase1_fields`
   - Input Markdown with existing frontmatter (`title`, `author`).
   - Fake report with 8+ display tags, QA score, grade, weight, QA pairs.
   - Assert output YAML contains `tags`, `qa_score`, `qa_grade`, `qa_weight`, `qa_pairs`, and preserves `author`.

4. `test_build_fastgpt_metadata_is_compact_and_serializable`
   - `json.dumps(build_fastgpt_metadata(report), ensure_ascii=False)` succeeds.
   - Assert metadata does not contain `raw`.

5. `test_process_selected_article_writes_report_and_output_without_syncer`
   - Fake agent returns a passing `QAReport`.
   - Assert report JSON and enriched Markdown are written.
   - Assert upload result is `not_configured`.

6. `test_process_selected_article_uploads_only_when_passed`
   - Fake syncer records calls.
   - Passing report triggers one `upload_file` call with metadata containing `qa_weight`.
   - Failing report triggers no upload and returns `skipped_by_qa`.

**Verify**:

```bash
python3 -m pytest tests/test_qa_ingest.py -v
```

Expected: all new workflow tests pass.

### Step 4: Add optional FastGPT metadata support without changing default uploads

Modify `fastgpt_sync.py`:

- Change signature to:

```python
def upload_file(self, file_path: str, collection_name: Optional[str] = None, metadata: Optional[dict] = None) -> str:
```

- In `data_payload`, replace hard-coded `"metadata": {}` with `"metadata": metadata or {}`.
- Keep all existing defaults unchanged.
- In dedup metadata at `fastgpt_sync.py:175-183`, include QA metadata only under a nested key if provided, e.g. `"qa_metadata": metadata or {}`. Do not break existing `filename`, `collection_name`, `collection_id` fields.
- Optional: if `upload_folder` gets metadata support, keep it simple: either no metadata for folder uploads or a `metadata_builder: Callable[[Path], dict] | None` callback. Do not add unused complexity unless tests require it.

Create `tests/test_fastgpt_sync.py`. Use monkeypatching to avoid network:

- Instantiate `FastGPTSyncer('https://example.com', 'key', 'dataset')` with a temp state file.
- Monkeypatch `_get_or_create_collection` to return `'collection-id'`.
- Monkeypatch `requests.post` to capture `data['data']` and return a fake object whose `status_code` is `200` and `json()` returns `{'code': 200}`.
- Call `upload_file(..., metadata={'qa_score': 90, 'qa_weight': 1.0})`.
- Assert captured payload contains that metadata.
- Add a second test calling `upload_file(..., metadata=None)` and assert metadata is `{}`.

**Verify**:

```bash
python3 -m pytest tests/test_fastgpt_sync.py -v
```

Expected: both metadata tests pass, with no real network call.

### Step 5: Add the `qa-ingest` CLI command

Modify `main.py` to add a new explicit command. Do not change default upload commands.

Parser requirements:

```text
qa-ingest
  --input PATH              # required; manually selected file or folder
  --output PATH             # default ./qa-output
  --report-dir PATH         # default ./qa-reports
  --dataset-id ID           # optional; if absent, only writes local outputs/reports
  --rubric PATH             # optional; forwarded to KnowledgeBaseQAAgent
  --threshold INT           # optional; forwarded to KnowledgeBaseQAAgent
  --extensions .md,.txt     # default .md,.txt
  --dry-run                 # list files and print configuration; no LLM call, no upload, no writes except none
```

Implementation requirements:

- Import `KnowledgeBaseQAAgent` and the new `process_selected_articles` / `load_markdown_files` lazily inside the command function so normal CLI startup remains lightweight.
- `--dry-run` must:
  - list matching files,
  - print output/report paths,
  - print whether upload is configured,
  - print rubric/model/threshold,
  - not call the LLM and not upload.
- Non-dry-run must:
  - create `KnowledgeBaseQAAgent(threshold=args.threshold, rubric_path=args.rubric)`,
  - create `FastGPTSyncer` only if `--dataset-id` is provided and `FASTGPT_BASE_URL` / `FASTGPT_API_KEY` are configured,
  - if `--dataset-id` is provided but FastGPT env vars are missing, do not crash; print a warning and run local report/output only,
  - call `process_selected_articles`,
  - print a summary table with: file, score, grade, action, weight, uploaded/upload result.
- Add command mapping in `main()`.
- Add interactive menu item only if it is straightforward; otherwise document that `qa-ingest` is CLI-only for phase 1. If you add it, keep it as item 9 and do not disturb existing items.

**Verify**:

```bash
printf -- '---\ntitle: 胰腺癌化疗副作用\n---\n# 胰腺癌化疗期间如何管理副作用\n常见副作用包括恶心、白细胞下降、血小板下降，应由医生结合检查结果判断。\n' > /tmp/qa_sample.md
python3 main.py qa-ingest --input /tmp/qa_sample.md --output /tmp/qa-output --report-dir /tmp/qa-reports --dry-run
```

Expected:

- exit 0,
- output mentions `/tmp/qa_sample.md`, `/tmp/qa-output`, `/tmp/qa-reports`, and phase-1 QA/rubric configuration,
- no LLM/API key is required,
- no upload is attempted.

### Step 6: Decide whether to add an explicit opt-in QA gate to `download-and-clean`

Only after `qa-ingest` works, add an opt-in flag to `download-and-clean` if it is still small and low risk:

```text
--qa-ingest             # after cleaning, evaluate cleaned files before upload
--qa-report-dir PATH    # default ./qa-reports
--qa-output PATH        # default cleaned output enriched in place or ./qa-output
--qa-rubric PATH
```

Rules:

- Without `--qa-ingest`, existing `download-and-clean` behavior must stay unchanged.
- With `--qa-ingest` and `--dataset-id`, upload the enriched QA outputs, not raw cleaned files.
- With `--qa-ingest`, skipped-by-QA files must not upload.
- If this requires broad rewrites of `cmd_download_and_clean`, STOP and leave this as a separate future plan. The new `qa-ingest` command is the required phase-1 deliverable; this step is optional.

**Verify if implemented**:

```bash
python3 main.py download-and-clean --help | grep -E -- '--qa-ingest|--qa-report-dir|--qa-output'
```

Expected: grep exits 0 and shows the new opt-in flags.

### Step 7: Update docs

Update `README.md`, `README.en.md`, and `tests/README.md`.

`README.md` should add a concise Chinese section under usage examples:

```bash
python3 main.py qa-ingest \
  --input ./selected-articles \
  --output ./qa-output \
  --report-dir ./qa-reports \
  --dataset-id 697b19a113081cf58b45cac3
```

Explain:

- This is phase-1 manual selected-article ingestion.
- Flow: 人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库.
- If `--dataset-id` is omitted, it only writes local reports and enriched Markdown.
- Failed/low-quality content is skipped and recorded; it is not automatically uploaded.

`README.en.md` should mirror this briefly.

`tests/README.md` should list `tests/test_qa_ingest.py` and `tests/test_fastgpt_sync.py`, plus the dry-run command.

**Verify**:

```bash
grep -n 'qa-ingest' README.md README.en.md tests/README.md
```

Expected: matches in all three files.

### Step 8: Final verification

Run:

```bash
python3 -m pytest
python3 -c "from agents.qa_ingest import QAIngestResult, process_selected_article; print('ok')"
printf -- '---\ntitle: 胰腺癌化疗副作用\n---\n# 胰腺癌化疗期间如何管理副作用\n常见副作用包括恶心、白细胞下降、血小板下降，应由医生结合检查结果判断。\n' > /tmp/qa_sample.md
python3 main.py qa-ingest --input /tmp/qa_sample.md --output /tmp/qa-output --report-dir /tmp/qa-reports --dry-run
```

Expected:

- full pytest exits 0,
- import check prints `ok`,
- dry-run exits 0 and does not require API key or network,
- dry-run output lists the selected article and phase-1 configuration.

## Test plan

New/updated tests:

- `tests/test_qa_agent.py` — compatibility aliases (`tags`, `dimensions`) if added.
- `tests/test_qa_ingest.py` — file discovery, frontmatter merge, metadata construction, local report/output writing, upload gating.
- `tests/test_fastgpt_sync.py` — metadata payload serialization without real network.

Existing patterns to follow:

- `tests/test_qa_agent.py` uses direct helper calls and fake inputs; keep tests deterministic and offline.
- `tests/test_core_logic.py` uses `tmp_path` and local fixture strings; follow this for file/report tests.
- Do not add tests that need `QA_AGENT_API_KEY`, `DASHSCOPE_API_KEY`, or real FastGPT credentials.

## Done criteria

ALL must hold:

- [ ] A new explicit `qa-ingest` CLI command exists.
- [ ] `qa-ingest --dry-run` lists selected local articles and configuration without LLM or FastGPT calls.
- [ ] Non-dry-run `qa-ingest` evaluates selected articles with `KnowledgeBaseQAAgent`.
- [ ] Each processed article writes a structured `.qa.json` report containing `display_tags`, `structured_tags`, `qa_pairs`, `qa_score`, `grade`, `library_action`, `qa_weight`, and `score_detail`.
- [ ] Each processed article writes enriched Markdown with display tags and QA metadata in frontmatter.
- [ ] Upload happens only when `--dataset-id` is provided, FastGPT env vars are configured, and `agent.should_upload(report)` is true.
- [ ] Failed / low-quality / D-grade content is skipped and recorded; it is not automatically uploaded.
- [ ] `FastGPTSyncer.upload_file(..., metadata=...)` sends QA metadata in the FastGPT payload while preserving old default behavior with `{}` metadata.
- [ ] `python3 -m pytest` exits 0.
- [ ] README and tests docs mention `qa-ingest` and the phase-1 flow.
- [ ] No real secrets or `.env` values are printed, committed, or copied into tests/docs.

## STOP conditions

Stop and report back (do not improvise) if:

- `agents/qa_agent.py` or `agents/rubric.py` no longer exposes the phase-1 fields shown above.
- Implementing `qa-ingest` appears to require broad rewrites of existing upload, cleaning, or downloading behavior.
- FastGPT metadata support requires changing API endpoint shape beyond adding the optional `metadata` object.
- Any test would require a real LLM call, a real FastGPT request, or a real API key.
- The design docs contradict the required user flow `人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库`.
- A step's verification fails twice after reasonable local fixes.

## Maintenance notes

- `qa-ingest` is the phase-1 safe integration point. Future work can wire it into `download-and-clean` by explicit flag after this lands.
- Keep scoring/tag policy in `agents/rubrics/*.yaml`; do not bury policy in `main.py`.
- Reviewers should scrutinize upload gating carefully: low score / `不建议入库` must never auto-upload.
- If FastGPT later supports first-class per-chunk weights, map `qa_weight` there; for now it is preserved in upload metadata/frontmatter for traceability.
- If reports become large, consider storing `qa_pairs` in report JSON only and keeping frontmatter compact. That is out of scope for this phase-1 implementation.
