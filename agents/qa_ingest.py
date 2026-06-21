"""一期 QA 精选文章入库工作流。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import json

import yaml

from agents.qa_agent import KnowledgeBaseQAAgent, QAReport


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


class _SimpleFrontmatter:
    @staticmethod
    def split(content: str) -> tuple[dict, str]:
        if not content.startswith('---\n'):
            return {}, content

        end = content.find('\n---\n', 4)
        if end == -1:
            return {}, content

        fm_text = content[4:end]
        body = content[end + 5:]
        try:
            data = yaml.safe_load(fm_text) or {}
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        return data, body

    @staticmethod
    def dump(frontmatter: dict, body: str) -> str:
        fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)
        body = body.lstrip('\n')
        return f"---\n{fm_yaml}---\n\n{body}"


def load_markdown_files(input_path: str | Path, extensions: tuple[str, ...] = ('.md', '.txt')) -> list[Path]:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"输入路径不存在: {input_path}")

    if path.is_file():
        if path.suffix.lower() not in extensions:
            raise ValueError(f"文件类型不支持: {path.suffix}")
        return [path]

    files = sorted(
        p for p in path.rglob('*')
        if p.is_file() and p.suffix.lower() in extensions
    )
    if not files:
        raise ValueError(f"未找到匹配的 Markdown 文件: {input_path}")
    return files


def build_qa_frontmatter(report: QAReport) -> dict:
    return {
        "qa_score": report.qa_score,
        "qa_grade": report.grade,
        "qa_library_action": report.library_action,
        "qa_weight": report.qa_weight,
        "qa_version": report.version,
        "display_tags": list(report.display_tags),
        "structured_tags": report.structured_tags,
        "qa_summary": report.summary,
        "qa_pairs": report.qa_pairs,
        "qa_deduction_reasons": list(report.deduction_reasons),
    }


def build_fastgpt_metadata(report: QAReport) -> dict:
    return {
        "qa_score": report.qa_score,
        "qa_grade": report.grade,
        "qa_library_action": report.library_action,
        "qa_weight": report.qa_weight,
        "display_tags": list(report.display_tags),
        "structured_tags": report.structured_tags,
        "qa_version": report.version,
    }


def merge_frontmatter(content: str, report: QAReport) -> str:
    frontmatter, body = _SimpleFrontmatter.split(content)
    frontmatter = dict(frontmatter)
    if report.title:
        frontmatter.setdefault("title", report.title)
    # 把 QA 报告的摘要映射到 core summary/description（仅当为空时，不覆盖）
    if report.summary:
        frontmatter.setdefault("summary", report.summary)
        frontmatter.setdefault("description", report.summary)
    frontmatter["tags"] = list(report.display_tags)
    frontmatter.update(build_qa_frontmatter(report))
    return _SimpleFrontmatter.dump(frontmatter, body)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def process_selected_article(
    path: Path,
    agent: KnowledgeBaseQAAgent,
    output_dir: Path,
    report_dir: Path,
    syncer: Optional[object] = None,
) -> QAIngestResult:
    content = path.read_text(encoding='utf-8')
    report = agent.evaluate(content, identifier=str(path))

    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / path.name
    report_path = report_dir / f"{path.stem}.qa.json"
    enriched = merge_frontmatter(content, report)
    output_path.write_text(enriched, encoding='utf-8')

    report_payload = report.to_dict()
    report_payload["qa_frontmatter"] = build_qa_frontmatter(report)
    _write_json(report_path, report_payload)

    uploaded = False
    upload_result = "not_configured"
    if syncer is not None:
        if agent.should_upload(report):
            metadata = build_fastgpt_metadata(report)
            upload_result = syncer.upload_file(
                str(output_path),
                collection_name=report.title or path.stem,
                metadata=metadata,
            )
            uploaded = upload_result == "success"
        else:
            upload_result = "skipped_by_qa"

    return QAIngestResult(
        source_path=str(path),
        report_path=str(report_path),
        output_path=str(output_path),
        uploaded=uploaded,
        upload_result=upload_result,
        passed=agent.should_upload(report),
        qa_score=report.qa_score,
        grade=report.grade,
        library_action=report.library_action,
        qa_weight=report.qa_weight,
        display_tags=list(report.display_tags),
    )


def process_selected_articles(
    input_path: str | Path,
    agent: KnowledgeBaseQAAgent,
    output_dir: str | Path,
    report_dir: str | Path,
    syncer: Optional[object] = None,
    extensions: tuple[str, ...] = ('.md', '.txt'),
) -> list[QAIngestResult]:
    files = load_markdown_files(input_path, extensions=extensions)
    output_path = Path(output_dir)
    report_path = Path(report_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path.mkdir(parents=True, exist_ok=True)

    results = []
    for file_path in files:
        results.append(process_selected_article(file_path, agent, output_path, report_path, syncer=syncer))
    return results
