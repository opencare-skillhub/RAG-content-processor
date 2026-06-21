"""风险红线检测器测试。"""

from agents.redline import RedlineChecker
from agents.rubric import RubricConfig


def test_redline_keyword_match_overseas_treatment():
    checker = RedlineChecker(RubricConfig.from_yaml())
    hits = checker.check("这篇文章鼓吹赴美就医和海外医疗。")
    assert hits
    assert hits[0]["id"] == "overseas_treatment"
    assert "赴美就医" in hits[0]["matched_keywords"]


def test_redline_keyword_match_miracle_drug():
    checker = RedlineChecker(RubricConfig.from_yaml())
    hits = checker.check("某抗癌神药可以逆转癌症。")
    ids = {h["id"] for h in hits}
    assert "miracle_drug" in ids


def test_redline_regex_match_single_case_hype():
    checker = RedlineChecker(RubricConfig.from_yaml())
    hits = checker.check("一个案例就创造奇迹，亲身经历三个月根治。")
    ids = {h["id"] for h in hits}
    assert "single_case_hype" in ids


def test_redline_no_match_for_neutral_content():
    checker = RedlineChecker(RubricConfig.from_yaml())
    hits = checker.check("本文介绍胰腺癌化疗期间常见副作用管理。")
    assert hits == []


def test_redline_handles_empty_content():
    checker = RedlineChecker(RubricConfig.from_yaml())
    assert checker.check("") == []
