# FastGPT Content Processor

A command-line tool for managing and processing FastGPT knowledge base content, including knowledge base queries, content search, file uploads, and WeChat article download/cleanup/upload workflows.

## Features

- **list-datasets**: list all FastGPT datasets
- **list-collections**: list articles/collections in a dataset
- **search**: semantic search inside a knowledge base
- **upload-file**: upload a single Markdown file
- **upload-folder**: batch upload Markdown files from a folder
- **download-wechat**: batch download WeChat articles via MCP
- **clean-wechat**: two-stage WeChat Markdown cleanup
- **download-and-clean**: one-stop workflow: download → clean → upload

## Installation and Usage

### Recommended: uv

```bash
cd fastgpt-content-processor
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

### Alternative: standard venv

```bash
cd fastgpt-content-processor
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

### Run commands

```bash
python3 main.py --help
python3 main.py list-datasets
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS mutation"
```

## Usage Examples

### List all datasets

```bash
python3 main.py list-datasets
```

### List articles in a dataset

```bash
python3 main.py list-collections --dataset-id 697b19a113081cf58b45cac3
```

### Search in a knowledge base

```bash
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS mutation"
```

### Upload a single file

```bash
python3 main.py upload-file --file article.md --dataset-id 697b19a113081cf58b45cac3
```

### Batch upload a folder

```bash
python3 main.py upload-folder --folder ./articles --dataset-id 697b19a113081cf58b45cac3
```

### Download WeChat articles

Create a `urls.txt` file with one WeChat article URL per line, then:

```bash
python3 main.py download-wechat --urls urls.txt --output ./wechat-downloads
```

### Clean WeChat articles

```bash
python3 main.py clean-wechat --input ./wechat-downloads --output ./cleaned-articles
```

### One-stop workflow (download → clean → upload)

```bash
python3 main.py download-and-clean \
  --urls urls.txt \
  --output ./wechat-downloads \
  --cleaned-output ./cleaned-articles \
  --dataset-id 697b19a113081cf58b45cac3
```

#### LLM frontmatter enrichment (optional)

By default `summary`/`description`/`tags` in frontmatter remain empty (no rule-based source).
Add `--enrich` to generate them with one low-cost LLM call.

```bash
# Reuse QA_AGENT_* config (works out of the box)
python3 main.py download-and-clean \
  --urls "https://mp.weixin.qq.com/s/xxx" \
  --enrich

# Recommended: use a free/low-cost model for speed
# In .env: ENRICHER_MODEL=glm-4.5-air + ENRICHER_BASE_URL + ENRICHER_API_KEY
```

### Manually selected article QA ingestion (phase 1)

Phase-1 core flow: **manual selection → auto QA → article tags → QA score → graded admission**.
`qa-ingest` evaluates locally selected articles, produces structured reports and
enriched Markdown, and decides whether to upload by score/grade. Low-quality or
D-grade content is recorded as `skipped_by_qa` and **never auto-uploaded**.

```bash
# Score only, write local reports and enriched Markdown (no FastGPT call)
python3 main.py qa-ingest \
  --input ./cleaned-articles \
  --output ./qa-output \
  --report-dir ./qa-reports

# Score + weighted upload (omit --dataset-id to keep it local only)
python3 main.py qa-ingest \
  --input ./cleaned-articles \
  --output ./qa-output \
  --report-dir ./qa-reports \
  --dataset-id 697b19a113081cf58b45cac3

# dry-run: list files and configuration without an LLM call or upload
python3 main.py qa-ingest --input ./cleaned-articles --dry-run
```

- `./qa-reports/*.qa.json` contains `display_tags`, `structured_tags`, `qa_pairs`,
  `qa_score`, `grade`, `library_action`, `qa_weight`, `score_detail`.
- `./qa-output/` holds enriched Markdown with QA frontmatter.
- Scoring policy lives in `agents/rubrics/medical.yaml`; default threshold is 85.

## Project Structure

```
fastgpt-content-processor/
├── main.py                      # CLI entry point
├── fastgpt_sync.py              # FastGPT API wrapper
├── fetchers/                    # Content fetchers
│   ├── wechat_mcp.py           # WeChat article downloader (MCP)
│   └── file.py                 # Local file reader
├── cleaners/                    # Content cleaners
│   ├── format_cleaner.py       # Stage 1: format cleanup
│   ├── frontmatter_doctor.py   # Stage 2: frontmatter normalization
│   ├── wechat_markdown.py      # WeChat Markdown cleaner (combined)
│   └── markdown.py             # General Markdown cleaner
├── utils/                       # Utilities
│   ├── hash.py                 # Hash calculation
│   └── dedup.py                # Deduplication logic
├── tests/                       # Test directory
├── .env.example                 # Environment variable template
├── requirements.txt             # Python dependencies
└── README.md                    # This document
```

## Testing

See [`tests/README.md`](tests/README.md) for the initial test scope and suggested themes.

```bash
python3 -m pytest
```

Core logic tests only:

```bash
python3 -m pytest tests/test_core_logic.py
```

## Roadmap

### Short-term: Reproducibility & Verification
- Unify `python3` usage and virtual environment documentation
- Add core logic tests
- Clarify boundaries for FastGPT, MCP, and example scripts
- Improve documentation consistency

### Mid-term: Knowledge Base QA Agent (core direction)
Introduce a "pre-upload quality gate" mechanism, repositioning the previously unimplemented translation capability as a **content quality admission Agent**. The goal is to ensure that only qualified content enters the knowledge base.

Design highlights:
- **Content grading**: assign a level (e.g., A/B/C or 1-5) based on professionalism, completeness, and source credibility
- **Tagging**: automatically extract topic tags and domain tags (disease / drug / clinical)
- **Multi-dimensional scoring**: score content across dimensions such as
  - structural completeness (heading / body / summary presence)
  - information density (ratio of valid content)
  - source credibility (account authority, marketing noise)
  - timeliness and citability
- **Score admission threshold**: auto-upload only when the overall score ≥ threshold (default 85); below the threshold, pause and ask the user — **never auto-upload**
- **Configurable**: threshold, dimension weights, and enable/disable via `QA_AGENT_*` env vars
- **Observable**: each QA run emits a structured report (score, dimension breakdown, suggestions) for traceability

Interaction modes:
- Auto mode: score passes → upload directly; fails → skip and record to report
- Interactive mode: score fails → prompt user to "skip / force upload / re-clean"

### Long-term: Extensibility & Platform-ization
- Plugin-based fetchers / cleaners / QA agents / upload adapters
- Support more content sources
- Support more knowledge base targets and export formats
- Workflow-based processing pipelines (download → clean → QA → upload)
- Configurable rules and batch job orchestration

## Contributing

Contributions of code, documentation, tests, and usage experience are welcome.

### Recommended practices
- Open an issue first to describe the requirement or problem
- Add tests before changing logic
- Keep documentation in sync with code
- Provide sample input/output when adding new cleanup rules
- Describe the applicable scenario when adding new fetchers or upload adapters

### Areas to contribute
- New content cleanup rules
- New data source fetchers
- FastGPT API adapter enhancements
- CLI experience improvements
- Test coverage improvements
- Examples and tutorials

## Acknowledgements

Thanks to the following projects and resources for inspiration and reference:

- [wechat-article-downloader](https://github.com/qiye45/wechatDownload)
- [baoyu-format-markdown](https://github.com/baoyu-tech/markdown-formatter)
- [markdown-frontmatter-doctor](https://github.com/example/frontmatter-doctor)
- [FastGPT API Documentation](https://doc.fastgpt.in/docs/development/api/)

## License

MIT License

---

**Other languages**: [中文](README.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [한국어](README.ko.md)
