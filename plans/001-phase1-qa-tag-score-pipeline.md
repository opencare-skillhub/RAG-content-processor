# Plan 001: Implement the phase-1 article QA, tag, score, grade, and library-weight pipeline

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**:
>
> ```bash
> git diff --stat 603d249..HEAD -- agents/ tests/ .env.example requirements.txt qa_agent_3phase_design.md qa_tagging_design.md
> ```
>
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts below against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED — touches the agent data model and tests, but does not change upload behavior.
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `603d249`, 2026-06-16

## Why this matters

The project is moving from a generic "content quality checker" toward a concrete phase-1 knowledge base pipeline: **manually selected article → auto-organized QA → article tags → QA score → grade → library weight**. The current `agents/qa_agent.py` still implements an older generic score model with hard-coded five dimensions (`structure`, `density`, `credibility`, `timeliness`, `citability`) and a generic `tags` field. That shape does not match the product design docs, which require `display_tags`, `structured_tags`, `qa_pairs`, `qa_score`, `grade`, `library_action`, `qa_weight`, and `score_detail`.

This plan makes the agent core match the phase-1 design while keeping the implementation testable, configurable, and safe to integrate later. It does **not** change `main.py` or automatic upload behavior.

## Current state

### Product design docs

- `qa_agent_3phase_design.md` / `qa_tagging_design.md` define phase-1 tagging and QA output.
- Key lines from `qa_agent_3phase_design.md`:
  - `qa_agent_3phase_design.md:4` — 每篇导入文章自动生成 8–10 个文章标签。
  - `qa_agent_3phase_design.md:299-314` — documented agent logic currently lists tag extraction before QA, but the user has now clarified the implementation path as `人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库`.
  - `qa_agent_3phase_design.md:351-401` — expected JSON output includes `display_tags`, `structured_tags`, `qa_pairs`, `qa_score`, `grade`, `library_action`, `qa_weight`, `score_detail`, `deduction_reasons`, `version`.
  - `qa_agent_3phase_design.md:408-415` — phase-1 requirements: display tags are required, count is 8–10, structured tags are required, tags must come from the article, and tags must avoid marketing/overclaiming.

### Current agent code

`agents/qa_agent.py` currently hard-codes a generic prompt and generic dimensions:

```python
# agents/qa_agent.py:33-46
DEFAULT_MODEL = "qwen3.7-max"
DEFAULT_PROVIDER = "qwen"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_THRESHOLD = 85
DEFAULT_TIMEOUT = 60

# 五个评分维度，每个维度满分 100，等权综合
DIMENSIONS = [
    "structure",
    "density",
    "credibility",
    "timeliness",
    "citability",
]
```

`QAReport` currently lacks the phase-1 output fields:

```python
# agents/qa_agent.py:52-64
@dataclass
class QAReport:
    identifier: str
    score: int
    passed: bool
    grade: str
    tags: list[str] = field(default_factory=list)
    dimensions: dict[str, int] = field(default_factory=dict)
    summary: str = ""
    suggestions: list[str] = field(default_factory=list)
    raw: Optional[dict] = field(default=None, repr=False)
```

The current prompt asks for generic fields only:

```python
# agents/qa_agent.py:94-107
OUTPUT_SCHEMA = {
    "score": "int 0-100，五维平均并四舍五入",
    "grade": "str，A/B/C/D 之一",
    "tags": "list[str]，主题标签",
    "dimensions": {...},
    "summary": "str，一句话评价",
    "suggestions": "list[str]，改进建议",
}
```

### Current config state

`agents/rubrics/medical.yaml` already exists but must be treated as the source of phase-1 rules. It should represent only phase-1 scope:

```yaml
# agents/rubrics/medical.yaml:1-2
# 医学/健康知识库一期 QA 整理与标签评分配置 v0.1
# 核心流程：人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库
```

Current `.env.example` includes QA agent model config but not rubric config:

```env
# .env.example:14-18
QA_AGENT_PROVIDER=qwen
QA_AGENT_MODEL=qwen3.7-max
QA_AGENT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QA_AGENT_SCORE_THRESHOLD=85
QA_AGENT_TIMEOUT=60
```

### Current tests

`tests/test_qa_agent.py` covers JSON parsing, generic score, and generic `tags` / `dimensions`. These tests need to keep passing or be updated to the phase-1 schema.

```python
# tests/test_qa_agent.py:54-78
def test_build_report_uses_model_score():
    parsed = {
        "score": 90,
        "grade": "A",
        "tags": ["肺癌", "靶向治疗"],
        "dimensions": {...},
    }
```

### Repo conventions

- Python project, no package installer config yet.
- Style: simple modules, Chinese comments/docstrings, `pathlib`, `json`, `yaml`, `dataclass`, direct pytest tests.
- Verification commands:
  - `python3 -m pytest`
  - `python3 -m pytest tests/test_qa_agent.py`
  - `python3 agents/qa_agent.py <file> --dry-run`

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run all tests | `python3 -m pytest` | exit 0, all tests pass |
| Run QA tests | `python3 -m pytest tests/test_qa_agent.py -v` | exit 0, all QA tests pass |
| Run rubric tests | `python3 -m pytest tests/test_rubric.py -v` | exit 0 |
| Run redline tests | `python3 -m pytest tests/test_redline.py -v` | exit 0 |
| Dry-run prompt | `python3 agents/qa_agent.py /tmp/qa_sample.md --dry-run` | prints system/user prompt and config, no LLM call |
| Import check | `python3 -c "from agents.qa_agent import KnowledgeBaseQAAgent, QAReport; print('ok')"` | prints `ok` |

## Scope

**In scope** (the only files you should modify/create):
- `agents/rubrics/medical.yaml`
- `agents/rubrics/general.yaml`
- `agents/rubric.py` (create)
- `agents/redline.py` (create)
- `agents/qa_agent.py`
- `agents/__init__.py`
- `.env.example`
- `tests/test_rubric.py` (create)
- `tests/test_redline.py` (create)
- `tests/test_qa_agent.py`
- `tests/README.md`

**Out of scope**:
- `main.py` — do not integrate upload gating yet.
- `fastgpt_sync.py` — do not alter upload behavior.
- `cleaners/` and `fetchers/` — do not change cleaning or downloading.
- README translations — optional docs can be updated later; keep this plan focused on the phase-1 agent core.
- Real LLM network tests — unit tests must not require DashScope/OpenAI access.

## Git workflow

- Branch: use current branch unless operator instructs otherwise.
- Commit style observed in repo: short conventional-ish messages are acceptable, e.g. `feat: add multi-language readmes, tests, and project docs`.
- Do NOT push or open a PR unless instructed by the operator.

## Steps

### Step 1: Normalize the phase-1 rubric YAML

Make `agents/rubrics/medical.yaml` the canonical phase-1 configuration. It must include:

- `version: "v0.1"`
- `profile: medical_phase1`
- `threshold: 85`
- `phase_order` exactly describing:
  1. `article_input`
  2. `qa_generation`
  3. `tag_generation`
  4. `qa_scoring`
  5. `grading`
  6. `library_weighting`
- `output_fields.required` with all required JSON output keys:
  - `article_id`, `title`, `article_type`, `domain`, `display_tags`, `structured_tags`, `qa_pairs`, `qa_score`, `grade`, `library_action`, `qa_weight`, `summary`, `score_detail`, `deduction_reasons`, `version`
- `qa_generation` with `min_pairs: 1`, `max_pairs: 5`, requirements, and `qa_pair_schema`.
- `tag_generation` matching `qa_tagging_design.md`:
  - display tag count min 8 max 10
  - structured tags required
  - tag types: disease, domain, topic, scenario, audience, content_type, qa_intent, risk_level
- `score_detail_schema` with four dimensions totaling 100:
  - source_quality max 25
  - content_clarity max 25
  - qa_usability max 35
  - safety_boundary max 15
- `tag_deduction_rules`, `marketing_tag_blacklist`, `risk_redlines`, and `grading` with A/B/C/D mapping to `library_action` and `qa_weight`.

Also keep `agents/rubrics/general.yaml` as a simple fallback with the same top-level structure where feasible. It does not need full medical examples.

**Verify**:

```bash
python3 - <<'PY'
import yaml
from pathlib import Path
p = Path('agents/rubrics/medical.yaml')
data = yaml.safe_load(p.read_text(encoding='utf-8'))
assert data['profile'] == 'medical_phase1'
assert data['phase_order'] == ['article_input', 'qa_generation', 'tag_generation', 'qa_scoring', 'grading', 'library_weighting']
assert data['tag_generation']['display_tags_count']['min'] == 8
assert data['tag_generation']['display_tags_count']['max'] == 10
assert sum(v['max'] for v in data['score_detail_schema'].values()) == 100
print('rubric yaml ok')
PY
```

Expected: `rubric yaml ok`.

### Step 2: Create `agents/rubric.py`

Create `agents/rubric.py` with a `RubricConfig` class. Keep it small and deterministic.

Required behavior:

- `RubricConfig.from_yaml(path: str | Path | None = None) -> RubricConfig`
  - If `path` is `None`, read `QA_AGENT_RUBRIC` from env.
  - If env is absent, default to `agents/rubrics/medical.yaml` relative to repo root.
  - Load YAML with `yaml.safe_load`.
  - Validate:
    - required top-level keys exist: `version`, `profile`, `threshold`, `phase_order`, `output_fields`, `qa_generation`, `tag_generation`, `score_detail_schema`, `grading`.
    - sum of `score_detail_schema.*.max` equals 100.
    - display tag min/max are present and min <= max.
- Properties / methods:
  - `version`, `profile`, `threshold`
  - `required_output_fields`
  - `score_dimensions` returning the `score_detail_schema` dict
  - `tag_config` returning `tag_generation`
  - `build_output_schema() -> dict`: return the expected JSON schema for the LLM output. It must include exactly the phase-1 fields.
  - `build_prompt_sections() -> str`: render QA rules, tag rules, scoring rules, grading rules into readable Chinese prompt text.
  - `compute_qa_score(parsed: dict) -> int`: sum `score_detail` values; clamp 0–100. If `qa_score` exists and differs from detail sum, prefer the detail sum because it is auditable.
  - `resolve_grade(score: int, requested_grade: str | None = None) -> dict`: use `grading` to return `{"grade": ..., "library_action": ..., "qa_weight": ...}`. Ignore invalid requested grade.
  - `validate_tags(display_tags: list[str], structured_tags: dict) -> list[str]`: return deduction reason strings for insufficient tags, marketing tags, or missing structured tags. Do not mutate the tags.

Design constraint:

- Do not import `openai` here.
- Do not perform network calls.
- Do not read `.env` in this file except through normal `os.getenv`; `qa_agent.py` already calls `load_dotenv()`.

**Verify**:

```bash
python3 - <<'PY'
from agents.rubric import RubricConfig
r = RubricConfig.from_yaml('agents/rubrics/medical.yaml')
assert r.version == 'v0.1'
assert r.profile == 'medical_phase1'
assert 'display_tags' in r.build_output_schema()
assert r.compute_qa_score({'score_detail': {'source_quality': 20, 'content_clarity': 20, 'qa_usability': 30, 'safety_boundary': 10}}) == 80
print('rubric config ok')
PY
```

Expected: `rubric config ok`.

### Step 3: Create `agents/redline.py`

Create `agents/redline.py` with a local detector for the `risk_redlines` section.

Required behavior:

- `RedlineChecker(rubric: RubricConfig)` stores the rubric.
- `check(text: str) -> list[dict]` returns hits. Each hit should include:
  - `id`
  - `name`
  - `action`
  - optional `max_grade`
  - `matched` — the keyword or regex pattern matched
  - `match_type` — `keyword` or `pattern`
- Matching rules:
  - `keywords`: simple substring match.
  - `patterns`: `re.search`.
  - Do not raise on invalid regex; skip invalid regex and log a warning.
- `apply_grade_constraints(grade_info: dict, hits: list[dict]) -> dict`:
  - If any hit action is `reject`, return grade D, library_action 不建议入库, qa_weight 0.0.
  - If a hit has `max_grade`, cap the grade no better than that grade. Use grade order A > B > C > D.
  - The returned dict must still include `grade`, `library_action`, `qa_weight`.

**Verify**:

```bash
python3 - <<'PY'
from agents.rubric import RubricConfig
from agents.redline import RedlineChecker
r = RubricConfig.from_yaml('agents/rubrics/medical.yaml')
c = RedlineChecker(r)
hits = c.check('这篇文章鼓吹抗癌神药可以逆转癌症')
assert hits
info = c.apply_grade_constraints({'grade': 'A', 'library_action': '高权重入库', 'qa_weight': 1.0}, hits)
assert info['grade'] in {'C', 'D'}
print('redline ok')
PY
```

Expected: `redline ok`.

### Step 4: Refactor `agents/qa_agent.py` to use the rubric

Modify `agents/qa_agent.py` while preserving its public class name and CLI.

Data model requirements:

- Extend `QAReport` to include phase-1 fields with defaults:
  - `article_id: str = ""`
  - `title: str = ""`
  - `article_type: str = ""`
  - `domain: str = "medical"`
  - `display_tags: list[str]`
  - `structured_tags: dict`
  - `qa_pairs: list[dict]`
  - `qa_score: int`
  - `score_detail: dict[str, int]`
  - `deduction_reasons: list[str]`
  - `library_action: str`
  - `qa_weight: float`
  - `redlines: list[dict]`
  - `version: str`
- Keep backward-compatible aliases if easy:
  - `score` should equal `qa_score`.
  - `passed` should mean `qa_score >= rubric.threshold` and grade/action not rejected.
  - `tags` can mirror `display_tags`.
  - `dimensions` can mirror `score_detail`.
  - `suggestions` can remain for compatibility, but new primary field is `deduction_reasons`.

Constructor requirements:

- Add optional `rubric_path: Optional[str] = None`.
- Load `self.rubric = RubricConfig.from_yaml(rubric_path or os.getenv('QA_AGENT_RUBRIC'))`.
- Set `self.threshold` from explicit argument if provided; otherwise use env `QA_AGENT_SCORE_THRESHOLD`; otherwise use `self.rubric.threshold`.
- Initialize `self.redline_checker = RedlineChecker(self.rubric)`.

Prompt requirements:

- Replace hard-coded `OUTPUT_SCHEMA` usage with `self.rubric.build_output_schema()`.
- System prompt must say the phase-1 flow explicitly:
  `人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库`.
- User prompt must include:
  - output schema
  - rubric sections from `self.rubric.build_prompt_sections()`
  - article content
- Prompt must instruct:
  - output JSON only
  - `display_tags` count 8–10
  - tags must come from article content
  - `qa_pairs` count 1–5
  - medical answers must not replace doctor judgment
  - do not use marketing tags (`神药`, `治愈`, `逆转`, etc.)

Evaluation requirements:

- `evaluate(content, identifier)` flow:
  1. `redline_hits = self.redline_checker.check(content)`
  2. call LLM and parse JSON
  3. build report using parsed result + redline hits
- `_build_report(identifier, parsed, raw_text, redline_hits=None)`:
  - Pull all phase-1 fields from `parsed` with sensible defaults.
  - Compute `qa_score` using `self.rubric.compute_qa_score(parsed)`.
  - Resolve grade/action/weight using `self.rubric.resolve_grade(qa_score, parsed.get('grade'))`.
  - Apply redline constraints with `self.redline_checker.apply_grade_constraints(...)`.
  - Validate tags with `self.rubric.validate_tags(...)`; append resulting reasons to `deduction_reasons`.
  - `passed` should be true only if `qa_score >= threshold` and `library_action` is not `不建议入库`.
- `_grade_from_score` may remain for backward compatibility but should delegate to rubric or be used only in tests.

CLI requirements:

- Add `--rubric` argument.
- Dry-run output must include rubric path/profile/version and the phase-1 prompt.

**Verify**:

```bash
printf -- '---\ntitle: 胰腺癌化疗副作用\n---\n# 胰腺癌化疗期间如何管理副作用\n常见副作用包括恶心、白细胞下降、血小板下降，应由医生结合检查结果判断。\n' > /tmp/qa_sample.md
python3 agents/qa_agent.py /tmp/qa_sample.md --dry-run | grep -E '人工精选文章|display_tags|qa_pairs|qa_score|medical_phase1'
```

Expected: grep exits 0 and prints matching lines.

### Step 5: Update environment example

Update `.env.example` to include:

```env
QA_AGENT_RUBRIC=agents/rubrics/medical.yaml
```

Keep existing qwen/DashScope configuration.

**Verify**:

```bash
grep -n 'QA_AGENT_RUBRIC=agents/rubrics/medical.yaml' .env.example
```

Expected: one match.

### Step 6: Add tests for rubric loading and scoring

Create `tests/test_rubric.py`.

Minimum tests:

1. `test_medical_rubric_loads`
   - `RubricConfig.from_yaml('agents/rubrics/medical.yaml')`
   - assert profile, version, threshold.
2. `test_score_detail_schema_sums_to_100`
   - sum max values = 100.
3. `test_output_schema_contains_phase1_fields`
   - schema includes `display_tags`, `structured_tags`, `qa_pairs`, `qa_score`, `grade`, `library_action`, `qa_weight`.
4. `test_compute_qa_score_sums_score_detail`
   - input source 20/content 20/qa 30/safety 10 → 80.
5. `test_resolve_grade_and_weight`
   - 92 → A / weight 1.0
   - 82 → B / weight 0.8
   - 75 → C / weight 0.5
   - 50 → D / weight 0.0
6. `test_validate_tags_flags_insufficient_tags`
   - fewer than 8 display tags returns a reason.
7. `test_validate_tags_flags_marketing_tags`
   - tag containing `神药` returns a reason.

**Verify**:

```bash
python3 -m pytest tests/test_rubric.py -v
```

Expected: all tests pass.

### Step 7: Add tests for redline detection

Create `tests/test_redline.py`.

Minimum tests:

1. `test_keyword_redline_hits_miracle_drug`
   - text includes `抗癌神药` and hit id is `miracle_drug`.
2. `test_keyword_redline_hits_overseas_treatment`
   - text includes `赴美就医`.
3. `test_pattern_redline_hits_single_case_hype`
   - text matches `一个案例.*奇迹`.
4. `test_no_false_positive_for_neutral_medical_text`
   - neutral chemo side-effect text returns no hits.
5. `test_reject_action_for_non_standard_treatment`
   - text includes `祖传秘方`; `apply_grade_constraints(A)` returns D / weight 0.0.
6. `test_downgrade_caps_grade`
   - miracle drug text caps A down to configured max grade.

**Verify**:

```bash
python3 -m pytest tests/test_redline.py -v
```

Expected: all tests pass.

### Step 8: Update QA agent tests for phase-1 output

Update `tests/test_qa_agent.py` to preserve existing parse tests but replace generic report tests with phase-1 report tests.

Keep these existing tests if still valid:
- JSON parse plain
- JSON parse codeblock
- JSON parse surrounding text
- empty invalid parse returns `{}`
- `QAReport.to_json()` serialization

Replace/extend report tests with:

1. `test_build_report_phase1_fields`
   - parsed dict includes article_id/title/article_type/domain/display_tags/structured_tags/qa_pairs/score_detail/summary/deduction_reasons.
   - assert report fields match.
   - assert `report.qa_score == report.score`.
   - assert `report.tags == report.display_tags`.
   - assert `report.dimensions == report.score_detail`.
2. `test_build_report_resolves_library_action_and_weight`
   - score_detail total 82 → grade B / 标准入库 / 0.8.
3. `test_build_report_below_threshold_not_passed`
   - score_detail total 70 → passed false.
4. `test_build_report_tag_deductions_are_added`
   - display_tags fewer than 8 and/or includes 神药 → deduction_reasons contains tag quality issue.
5. `test_build_report_redline_rejects_non_standard_treatment`
   - call `_build_report(..., redline_hits=[...])` or evaluate redline checker separately, assert action not recommended and passed false.
6. `test_should_upload_respects_report_passed`
   - `should_upload` returns `report.passed`.

**Verify**:

```bash
python3 -m pytest tests/test_qa_agent.py -v
```

Expected: all tests pass.

### Step 9: Update test docs

Update `tests/README.md` to list:

- `agents/rubric.py`
- `agents/redline.py`
- `agents/qa_agent.py`

Add run commands:

```bash
python3 -m pytest tests/test_rubric.py
python3 -m pytest tests/test_redline.py
python3 -m pytest tests/test_qa_agent.py
```

Mention that real LLM calls remain manual/dry-run only.

**Verify**:

```bash
grep -n 'test_rubric.py\|test_redline.py\|test_qa_agent.py' tests/README.md
```

Expected: all three names appear.

### Step 10: Final verification

Run:

```bash
python3 -m pytest
python3 -c "from agents.qa_agent import KnowledgeBaseQAAgent, QAReport; from agents.rubric import RubricConfig; from agents.redline import RedlineChecker; print('ok')"
printf -- '---\ntitle: 胰腺癌化疗副作用\n---\n# 胰腺癌化疗期间如何管理副作用\n常见副作用包括恶心、白细胞下降、血小板下降，应由医生结合检查结果判断。\n' > /tmp/qa_sample.md
python3 agents/qa_agent.py /tmp/qa_sample.md --dry-run | grep -E '人工精选文章|display_tags|qa_pairs|qa_score|medical_phase1'
```

Expected:
- all pytest tests pass
- import check prints `ok`
- dry-run grep exits 0 and prints matching lines

## Test plan

New/updated tests:

- `tests/test_rubric.py` — config loading, schema, score computation, tag validation, grade/weight resolution.
- `tests/test_redline.py` — keyword/pattern detection and grade constraint logic.
- `tests/test_qa_agent.py` — phase-1 report construction and backward-compatible aliases.

Existing test patterns to follow:

- `tests/test_qa_agent.py` currently uses direct helper calls and does not call LLM; keep that style.
- `tests/test_core_logic.py` uses small local fixtures; keep tests deterministic and network-free.

## Done criteria

ALL must hold:

- [ ] `agents/rubrics/medical.yaml` encodes phase-1 flow: article → QA → tags → score → grade → library weight.
- [ ] `agents/rubric.py` exists and loads/validates YAML.
- [ ] `agents/redline.py` exists and detects configured risk phrases locally.
- [ ] `agents/qa_agent.py` uses `RubricConfig` and emits phase-1 report fields.
- [ ] `QAReport.to_dict()` includes `display_tags`, `structured_tags`, `qa_pairs`, `qa_score`, `grade`, `library_action`, `qa_weight`, `score_detail`, `deduction_reasons`, `version`.
- [ ] Backward-compatible aliases remain: `score == qa_score`, `tags == display_tags`, `dimensions == score_detail`.
- [ ] `.env.example` includes `QA_AGENT_RUBRIC=agents/rubrics/medical.yaml`.
- [ ] `python3 -m pytest` exits 0.
- [ ] Dry-run prints phase-1 prompt fields and does not require API key.
- [ ] No files outside the in-scope list are modified, except `plans/README.md` status update when done.

## STOP conditions

Stop and report back (do not improvise) if:

- `agents/qa_agent.py` no longer matches the excerpts in this plan and the drift changes the public API materially.
- The phase-1 design docs (`qa_agent_3phase_design.md`, `qa_tagging_design.md`) are missing or contradict the user's clarified flow: `人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库`.
- Any implementation requires modifying `main.py`, `fastgpt_sync.py`, `cleaners/`, or upload behavior.
- `python3 -m pytest` fails for reasons unrelated to the agent/rubric changes after two reasonable fix attempts.
- A real LLM call is needed to pass tests. Tests must stay offline.

## Maintenance notes

- Integration into upload flow should be a separate plan after this one. That integration must enforce: score/pass first, and if not passed, ask/skip — never auto-upload low-quality content.
- The rubric YAML is now the product-facing policy. Future changes to tag types, scoring weights, risk phrases, and grade thresholds should happen in YAML first, then tests.
- Reviewers should scrutinize the prompt and rubric for medical safety language: no overclaiming, no replacing clinician judgment, no marketing tags.
- Real DashScope/qwen3.7-max behavior is intentionally not unit-tested; manual smoke tests should use `--dry-run` first and then a controlled sample article with API key configured.
