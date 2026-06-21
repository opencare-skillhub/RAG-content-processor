"""Rubric 配置与一期评分引擎测试。"""

from agents.rubric import RubricConfig


def test_load_default_medical_rubric():
    rubric = RubricConfig.from_yaml()
    assert rubric.version == "v0.1"
    assert rubric.profile == "medical_phase1"
    assert rubric.threshold == 85
    assert rubric.display_tags_count == {"min": 8, "max": 10}


def test_score_schema_total_is_100():
    rubric = RubricConfig.from_yaml()
    assert sum(v["max"] for v in rubric.data["score_detail_schema"].values()) == 100


def test_build_output_schema_contains_phase1_fields():
    rubric = RubricConfig.from_yaml()
    schema = rubric.build_output_schema()
    assert "display_tags" in schema
    assert "structured_tags" in schema
    assert "qa_pairs" in schema
    assert "qa_score" in schema
    assert "qa_weight" in schema


def test_evaluate_result_uses_score_detail_sum_when_qa_score_missing():
    rubric = RubricConfig.from_yaml()
    parsed = {
        "display_tags": ["胰腺癌", "化疗副作用", "白细胞下降", "恶心呕吐", "患者护理", "治疗期间", "家属必看", "医生沟通"],
        "score_detail": {
            "source_quality": 20,
            "content_clarity": 20,
            "qa_usability": 30,
            "safety_boundary": 15,
        },
    }
    result = rubric.evaluate_result(parsed)
    assert result.qa_score == 85
    assert result.grade == "B"
    assert result.library_action == "标准入库"
    assert result.qa_weight == 0.8


def test_evaluate_result_applies_insufficient_tag_penalty():
    rubric = RubricConfig.from_yaml()
    parsed = {
        "qa_score": 90,
        "display_tags": ["胰腺癌"],
        "score_detail": {
            "source_quality": 25,
            "content_clarity": 25,
            "qa_usability": 25,
            "safety_boundary": 15,
        },
    }
    result = rubric.evaluate_result(parsed)
    assert result.qa_score == 87
    assert any("少于" in r for r in result.deduction_reasons)


def test_evaluate_result_applies_marketing_tag_penalty():
    rubric = RubricConfig.from_yaml()
    parsed = {
        "qa_score": 90,
        "display_tags": ["胰腺癌", "抗癌神药", "化疗", "护理", "营养", "问诊", "医生", "副作用"],
        "score_detail": {},
    }
    result = rubric.evaluate_result(parsed)
    assert result.qa_score == 82
    assert any("营销" in r for r in result.deduction_reasons)


def test_evaluate_result_reject_redline_forces_d_grade():
    rubric = RubricConfig.from_yaml()
    parsed = {"qa_score": 95, "display_tags": ["胰腺癌"] * 8, "score_detail": {}}
    redlines = [{"id": "x", "name": "非规范治疗", "action": "reject"}]
    result = rubric.evaluate_result(parsed, redlines)
    assert result.qa_score == 0
    assert result.grade == "D"
    assert result.qa_weight == 0.0


def test_evaluate_result_downgrade_redline_limits_grade():
    rubric = RubricConfig.from_yaml()
    parsed = {"qa_score": 95, "display_tags": ["胰腺癌"] * 8, "score_detail": {}}
    redlines = [{"id": "x", "name": "鼓吹海外就医", "action": "downgrade", "max_grade": "C"}]
    result = rubric.evaluate_result(parsed, redlines)
    assert result.qa_score == 95
    assert result.grade == "C"
    assert result.qa_weight == 0.5
