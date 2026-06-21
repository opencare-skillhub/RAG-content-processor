"""一期 QA 精选文章入库工作流的离线测试。

不调用真实 LLM，也不访问 FastGPT：用 fake agent / fake syncer 验证
文件发现、frontmatter 合并、元数据构造、本地报告产出与上传门控。
"""

import json
from pathlib import Path

from agents.qa_agent import QAReport
from agents.qa_ingest import (
    build_fastgpt_metadata,
    build_qa_frontmatter,
    load_markdown_files,
    merge_frontmatter,
    process_selected_article,
)


def _passing_report(path: str) -> QAReport:
    return QAReport(
        identifier=path,
        qa_score=90,
        passed=True,
        grade="A",
        library_action="高权重入库",
        qa_weight=1.0,
        title="胰腺癌患者化疗期间如何管理副作用",
        display_tags=[
            "胰腺癌", "化疗副作用", "白细胞下降", "恶心呕吐", "血小板低",
            "治疗期间", "患者护理", "家属必看", "问诊准备", "医生沟通",
        ],
        structured_tags={"disease": ["胰腺癌"], "topic": ["化疗副作用"]},
        qa_pairs=[{"question": "Q?", "answer": "A.", "confidence": 0.8}],
        score_detail={"source_quality": 25, "content_clarity": 25, "qa_usability": 25, "safety_boundary": 15},
        summary="适合入库。",
        deduction_reasons=[],
    )


def _failing_report(path: str) -> QAReport:
    return QAReport(
        identifier=path,
        qa_score=70,
        passed=False,
        grade="C",
        library_action="低权重入库/人工复核",
        qa_weight=0.5,
        title="低质量示例",
        display_tags=["a", "b"],
    )


class FakeAgent:
    """记录调用并返回预设报告，不访问 LLM。"""

    def __init__(self, report_factory=_passing_report, threshold=85):
        self._factory = report_factory
        self.threshold = threshold
        self.calls = []

    def evaluate(self, content, identifier="<unknown>"):
        self.calls.append(identifier)
        return self._factory(identifier)

    def should_upload(self, report):
        return report.qa_score >= self.threshold and report.qa_weight > 0


class FakeSyncer:
    """记录 upload_file 调用，返回 'success'。"""

    def __init__(self):
        self.uploads = []

    def upload_file(self, file_path, collection_name=None, metadata=None):
        self.uploads.append({"file_path": file_path, "collection_name": collection_name, "metadata": metadata})
        return "success"


# ---- load_markdown_files ----

def test_load_markdown_files_accepts_single_file(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("hello", encoding="utf-8")
    assert load_markdown_files(p) == [p]


def test_load_markdown_files_sorts_directory(tmp_path):
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "ignore.jpg").write_text("x", encoding="utf-8")
    files = load_markdown_files(tmp_path)
    assert [f.name for f in files] == ["a.md", "b.md"]


def test_load_markdown_files_missing_raises(tmp_path):
    missing = tmp_path / "nope"
    try:
        load_markdown_files(missing)
    except FileNotFoundError:
        return
    raise AssertionError("应抛 FileNotFoundError")


def test_load_markdown_files_no_match_raises(tmp_path):
    (tmp_path / "img.png").write_text("x", encoding="utf-8")
    try:
        load_markdown_files(tmp_path)
    except ValueError:
        return
    raise AssertionError("应抛 ValueError")


# ---- frontmatter / metadata ----

def test_merge_frontmatter_adds_phase1_fields_and_preserves_existing():
    content = "---\ntitle: 旧标题\nauthor: 张三\n---\n\n正文内容\n"
    report = _passing_report("x.md")
    merged = merge_frontmatter(content, report)

    assert "author: 张三" in merged
    assert "正文内容" in merged
    assert "qa_score: 90" in merged
    assert "qa_grade: A" in merged
    assert "qa_weight: 1.0" in merged
    assert "qa_pairs:" in merged
    # tags 被 display_tags 覆盖
    assert "胰腺癌" in merged


def test_merge_frontmatter_maps_report_summary_when_empty():
    """report.summary 应映射到 core summary/description（仅当为空时）。"""
    content = "---\ntitle: x\nsummary: ''\ndescription: ''\n---\n\n正文\n"
    report = _passing_report("x.md")
    report.summary = "QA 报告生成的摘要内容"
    merged = merge_frontmatter(content, report)

    assert "QA 报告生成的摘要内容" in merged


def test_merge_frontmatter_preserves_existing_summary():
    """已有 summary 不应被 report.summary 覆盖。"""
    content = "---\ntitle: x\nsummary: 原摘要\ndescription: 原描述\n---\n\n正文\n"
    report = _passing_report("x.md")
    report.summary = "不应覆盖的摘要"
    merged = merge_frontmatter(content, report)

    # summary/description 保留原值，不被覆盖
    assert "summary: 原摘要" in merged
    assert "description: 原描述" in merged
    # report.summary 只进入 qa_summary（不进 core summary/description）
    assert "qa_summary: 不应覆盖的摘要" in merged


def test_build_qa_frontmatter_is_serializable_and_excludes_raw():
    report = _passing_report("x.md")
    report.raw = {"text": "secret", "parsed": {}}
    fm = build_qa_frontmatter(report)
    s = json.dumps(fm, ensure_ascii=False)
    assert "secret" not in s
    assert fm["qa_score"] == 90
    assert len(fm["display_tags"]) == 10
    assert fm["qa_version"] == "v0.1"


def test_build_fastgpt_metadata_is_compact_and_serializable():
    report = _passing_report("x.md")
    report.raw = {"text": "secret"}
    meta = build_fastgpt_metadata(report)
    s = json.dumps(meta, ensure_ascii=False)
    assert "secret" not in s
    assert meta["qa_score"] == 90
    assert meta["qa_weight"] == 1.0
    # 紧凑元数据不含 qa_pairs/summary 等大字段
    assert "qa_pairs" not in meta
    assert "qa_summary" not in meta


# ---- process_selected_article ----

def test_process_selected_article_writes_report_and_output_without_syncer(tmp_path):
    src = tmp_path / "src" / "art.md"
    src.parent.mkdir(parents=True)
    src.write_text("---\ntitle: 旧\n---\n\n正文\n", encoding="utf-8")

    output_dir = tmp_path / "out"
    report_dir = tmp_path / "rep"
    agent = FakeAgent()
    result = process_selected_article(src, agent, output_dir, report_dir, syncer=None)

    assert (output_dir / "art.md").exists()
    assert (report_dir / "art.qa.json").exists()
    report_payload = json.loads((report_dir / "art.qa.json").read_text(encoding="utf-8"))
    assert report_payload["qa_score"] == 90
    assert report_payload["qa_frontmatter"]["qa_grade"] == "A"

    assert result.uploaded is False
    assert result.upload_result == "not_configured"
    assert result.passed is True


def test_process_selected_article_uploads_only_when_passed(tmp_path):
    src = tmp_path / "pass.md"
    src.write_text("正文\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    report_dir = tmp_path / "rep"

    # 通过 → 触发上传
    syncer = FakeSyncer()
    agent = FakeAgent(report_factory=_passing_report)
    r_ok = process_selected_article(src, agent, output_dir, report_dir, syncer=syncer)
    assert r_ok.uploaded is True
    assert r_ok.upload_result == "success"
    assert len(syncer.uploads) == 1
    assert syncer.uploads[0]["metadata"]["qa_weight"] == 1.0

    # 不通过 → 跳过上传
    syncer_fail = FakeSyncer()
    agent_fail = FakeAgent(report_factory=_failing_report, threshold=85)
    src2 = tmp_path / "fail.md"
    src2.write_text("正文\n", encoding="utf-8")
    r_no = process_selected_article(src2, agent_fail, output_dir, report_dir, syncer=syncer_fail)
    assert r_no.uploaded is False
    assert r_no.upload_result == "skipped_by_qa"
    assert syncer_fail.uploads == []
