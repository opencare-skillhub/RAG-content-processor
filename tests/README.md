# Tests

This directory contains focused tests for the project's local logic.

## Scope

The initial test set focuses on the most stable and important parts of the codebase:

- `utils/hash.py`
- `utils/dedup.py`
- `cleaners/format_cleaner.py`
- `cleaners/frontmatter_doctor.py`
- `cleaners/markdown.py`
- `cleaners/text.py`
- `cleaners/wechat_article.py`
- `agents/qa_agent.py`（离线部分：解析、等级、阈值判断）
- `agents/rubric.py` / `agents/redline.py`（评分配置与红线检测）
- `agents/qa_ingest.py`（精选文章入库工作流：文件发现、frontmatter 合并、上传门控）
- `agents/llm_client.py`（共享 LLM 层：env fallback 链、JSON 容错解析）
- `agents/frontmatter_enricher.py`（frontmatter LLM 富化：summary/description/tags 生成）
- `fastgpt_sync.py`（上传 payload 的 QA 元数据序列化，离线 mock）

## What these tests try to protect

- content normalization does not accidentally remove valid content
- frontmatter is standardized consistently
- URL extraction continues to work
- duplicate detection remains stable
- file hashing is deterministic
- HTML/Markdown cleaning stays safe for common inputs
- QA agent JSON parsing is robust against code blocks and surrounding text

## Suggested future test themes

- CLI argument parsing and help output
- FastGPT API wrapper with mocked HTTP responses
- MCP downloader with mocked remote responses
- file scanning and extension filtering
- error-path coverage for malformed input
- regression tests for newly added cleaner rules
- QA agent LLM call with mocked OpenAI client

## Run

```bash
python3 -m pytest
```

Run only the core logic set:

```bash
python3 -m pytest tests/test_core_logic.py
```

Run only the QA agent tests:

```bash
python3 -m pytest tests/test_qa_agent.py
```

Run the rubric / redline / QA ingest / FastGPT sync tests:

```bash
python3 -m pytest tests/test_rubric.py tests/test_redline.py
python3 -m pytest tests/test_qa_ingest.py tests/test_fastgpt_sync.py
```

Run the LLM client and frontmatter enricher tests:

```bash
python3 -m pytest tests/test_llm_client.py tests/test_frontmatter_enricher.py
```

Run all WeChat cleanup and frontmatter tests:

```bash
python3 -m pytest tests/test_format_cleaner_wechat.py tests/test_core_logic.py
```

## QA agent manual check (dry-run)

The QA agent's real LLM call is not covered by unit tests.
Use the built-in CLI dry-run to inspect the prompt without calling the model:

```bash
# 直接运行模块文件（避免 agents 包名与标准库冲突）
python3 agents/qa_agent.py article.md --dry-run
```

To run a real evaluation, ensure the API key is available
(`QA_AGENT_API_KEY` or `DASHSCOPE_API_KEY`):

```bash
python3 agents/qa_agent.py article.md
```

## QA ingest workflow (dry-run)

The phase-1 ingest workflow (`人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库`)
has an explicit `qa-ingest` CLI command. Inspect the plan without calling the LLM
or FastGPT:

```bash
python3 main.py qa-ingest \
  --input ./cleaned-articles \
  --output ./qa-output \
  --report-dir ./qa-reports \
  --dry-run
```

A real run evaluates each article, writes a structured `.qa.json` report and an
enriched Markdown file. Add `--dataset-id` only to upload passing articles;
failed or low-quality content is recorded as `skipped_by_qa` and never
auto-uploaded.

## Frontmatter enrichment (dry-run)

The `download-and-clean` command supports `--enrich` to fill empty
`summary`/`description`/`tags` via a low-cost LLM call. By default it reuses
`QA_AGENT_*` config; you can override with `ENRICHER_*` env vars for a cheaper
or free model (e.g. `glm-4.5-air`).

```bash
# Without --enrich: only rule-based cleaning (author/title from regex, rest empty)
python3 main.py download-and-clean --urls urls.txt

# With --enrich: + LLM-generated summary/description/tags
python3 main.py download-and-clean --urls urls.txt --enrich
```


