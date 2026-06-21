"""知识库一期 QA Agent 的离线测试。"""

import json

from agents.qa_agent import KnowledgeBaseQAAgent, QAReport


def _make_agent():
    return KnowledgeBaseQAAgent(api_key="test-key", threshold=85)


def _valid_parsed(score=90):
    return {
        "article_id": "article_001",
        "title": "胰腺癌患者化疗期间如何管理副作用",
        "article_type": "side_effect_management",
        "domain": "medical",
        "display_tags": [
            "胰腺癌", "化疗副作用", "白细胞下降", "恶心呕吐", "血小板低",
            "治疗期间", "患者护理", "家属必看", "问诊准备", "医生沟通"
        ],
        "structured_tags": {
            "disease": ["胰腺癌"],
            "domain": ["医学治疗", "患者教育"],
            "topic": ["化疗副作用", "副作用管理"],
            "scenario": ["治疗期间", "居家护理"],
            "audience": ["患者", "家属"],
            "content_type": ["医学科普", "QA知识"],
            "qa_intent": ["需要注意什么", "什么时候就医"],
        },
        "qa_score": score,
        "summary": "本文适合整理为患者教育类 QA。",
        "qa_pairs": [
            {
                "question": "胰腺癌患者化疗期间常见副作用有哪些？",
                "answer": "常见副作用包括恶心、呕吐、乏力等，应由医生结合检查结果判断。",
                "confidence": 0.82,
                "usage_note": "可作为患者教育回答，不能替代医生判断。",
            }
        ],
        "score_detail": {
            "source_quality": 20,
            "content_clarity": 23,
            "qa_usability": 27,
            "safety_boundary": 15,
        },
        "deduction_reasons": [],
    }


def test_grade_from_score_fallback():
    a = KnowledgeBaseQAAgent
    assert a._grade_from_score(95, None) == "A"
    assert a._grade_from_score(85, None) == "B"
    assert a._grade_from_score(75, None) == "C"
    assert a._grade_from_score(60, None) == "D"
    assert a._grade_from_score(95, "c") == "C"


def test_parse_json_plain():
    agent = _make_agent()
    payload = {"qa_score": 88, "grade": "B", "display_tags": ["KRAS"]}
    parsed = agent._parse_json(json.dumps(payload))
    assert parsed["qa_score"] == 88
    assert parsed["display_tags"] == ["KRAS"]


def test_parse_json_codeblock_wrapped():
    agent = _make_agent()
    text = "```json\n{\"qa_score\": 90, \"grade\": \"A\"}\n```"
    parsed = agent._parse_json(text)
    assert parsed["qa_score"] == 90


def test_parse_json_with_surrounding_text():
    agent = _make_agent()
    text = "好的，结果如下：\n{\"qa_score\": 70, \"grade\": \"C\"}\n以上。"
    parsed = agent._parse_json(text)
    assert parsed["qa_score"] == 70


def test_parse_json_empty_returns_empty_dict():
    agent = _make_agent()
    assert agent._parse_json("") == {}
    assert agent._parse_json("not json at all") == {}


def test_build_report_phase1_fields():
    agent = _make_agent()
    parsed = _valid_parsed(score=90)
    report = agent._build_report("article.md", parsed, raw_text=json.dumps(parsed))

    assert report.identifier == "article.md"
    assert report.article_id == "article_001"
    assert report.title.startswith("胰腺癌")
    assert report.qa_score == 90
    assert report.score == 90  # 兼容属性
    assert report.grade == "A"
    assert report.library_action == "高权重入库"
    assert report.qa_weight == 1.0
    assert report.passed is True
    assert len(report.display_tags) == 10
    assert report.structured_tags["disease"] == ["胰腺癌"]
    assert report.qa_pairs[0]["confidence"] == 0.82


def test_build_report_below_threshold_not_passed():
    agent = _make_agent()
    parsed = _valid_parsed(score=70)
    report = agent._build_report("low.md", parsed, raw_text="")
    assert report.qa_score == 70
    assert report.grade == "C"
    assert report.passed is False
    assert report.library_action == "低权重入库/人工复核"


def test_build_report_score_clamped_to_range():
    agent = _make_agent()
    parsed = _valid_parsed(score=250)
    report = agent._build_report("x.md", parsed, raw_text="")
    assert report.qa_score == 100


def test_should_upload_respects_threshold_and_weight():
    agent = _make_agent()
    passed = QAReport("a.md", qa_score=90, passed=True, grade="A", qa_weight=1.0)
    failed_score = QAReport("b.md", qa_score=70, passed=False, grade="C", qa_weight=0.5)
    failed_weight = QAReport("c.md", qa_score=90, passed=False, grade="D", qa_weight=0.0)
    assert agent.should_upload(passed) is True
    assert agent.should_upload(failed_score) is False
    assert agent.should_upload(failed_weight) is False


def test_redline_reject_forces_d_grade():
    agent = _make_agent()
    parsed = _valid_parsed(score=95)
    redlines = [{"id": "non_standard", "name": "非规范治疗", "action": "reject"}]
    report = agent._build_report("bad.md", parsed, raw_text="", redlines=redlines)
    assert report.qa_score == 0
    assert report.grade == "D"
    assert report.qa_weight == 0.0
    assert report.passed is False
    assert report.redlines == redlines


def test_qareport_serialization():
    report = QAReport(
        identifier="x.md",
        qa_score=88,
        passed=True,
        grade="B",
        library_action="标准入库",
        qa_weight=0.8,
        display_tags=["a", "b"],
        structured_tags={"topic": ["a"]},
        score_detail={"source_quality": 20},
        summary="ok",
        deduction_reasons=["fix"],
    )
    d = report.to_dict()
    assert d["qa_score"] == 88
    assert json.loads(report.to_json())["grade"] == "B"
