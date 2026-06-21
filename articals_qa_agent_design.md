# 医疗信息质量评分 Agent 开发说明

## 一、项目目标

开发一个「医疗信息质量评分 Agent」，用于评估公众号、视频号、小红书、网页文章、医生科普、会议摘要、海外就医宣传、中医/营养品宣传等内容的信息质量和潜在误导风险。

本 Agent 主要面向肿瘤科普场景，优先覆盖胰腺癌、胆道癌、消化道肿瘤等方向。系统需要支持后续扩展到其他癌种和疾病领域。

核心原则：

1. 不只判断“谁发布的”，更要判断“内容说了什么、证据在哪里、推论是否过度、患者照做是否有风险”。
2. 评分规则必须配置化，不能写死在代码里。
3. 输出必须可解释，不能只给一个分数。
4. 对高风险内容要有红旗闸门机制，即使来源看似专业，也要强制降级。
5. Agent 第一版以规则 + LLM 辅助为主，后续可接入 RAG、数据库、人工标注校准。

---

## 二、核心输出

对每篇输入内容，系统输出以下结果：

```json
{
  "overall_score": 72,
  "grade": "B",
  "risk_level": "R2",
  "harm_risk_score": 25,
  "evidence_tag": "doctor_education_with_references",
  "recommended_action": "可作为科普参考，但不应作为治疗决策依据",
  "summary": "该内容来源较可信，部分引用指南和研究，但对适用人群和毒副作用说明不足。",
  "dimension_scores": {
    "source_credibility": 18,
    "evidence_data_quality": 24,
    "clinical_content_quality": 20,
    "conclusion_risk_orientation": 10
  },
  "red_flags": [],
  "claims": [],
  "evidence_checks": [],
  "explanation": ""
}
```

---

## 三、评分体系

总分 100 分，分为四个维度：

| 维度         |  权重 | 满分 |
| ---------- | --: | -: |
| A. 信源可信度   | 25% | 25 |
| B. 证据与数据质量 | 35% | 35 |
| C. 内容医学质量  | 25% | 25 |
| D. 结论导向与风险 | 15% | 15 |

总分计算：

```text
IQS = A + B + C + D - RedFlagPenalty
```

但需要注意：
红旗风险闸门优先于总分。如果触发严重红旗，应设置分数上限，例如最高不得超过 25、30、40 或 45 分。

---

## 四、等级划分

```yaml
grade_thresholds:
  A:
    min_score: 85
    meaning: "高可信，可进入知识库核心层"
  B:
    min_score: 70
    meaning: "整体可信，可作为科普参考"
  C:
    min_score: 55
    meaning: "谨慎使用，需要补充证据"
  D:
    min_score: 40
    meaning: "低质量，不建议作为知识源"
  E:
    min_score: 0
    meaning: "高风险或疑似误导，不建议传播"
```

风险等级：

```yaml
risk_levels:
  R0: "低风险，常规科普"
  R1: "轻微信息不完整"
  R2: "证据较弱，需要提示限制"
  R3: "可能误导患者，需要人工复核"
  R4: "可能导致错误治疗选择"
  R5: "高风险医疗误导或疑似欺诈"
```

---

## 五、推荐技术栈

优先使用：

```text
Python 3.11+
FastAPI
Pydantic v2
PyYAML
pytest
SQLite / PostgreSQL 可选
```

LLM 调用部分需要抽象成独立接口，不能绑定某一个模型供应商。

建议目录结构：

```text
medical_info_quality_agent/
  app/
    main.py
    api/
      routes.py
    core/
      scoring_engine.py
      risk_gate.py
      claim_extractor.py
      source_classifier.py
      evidence_classifier.py
      report_generator.py
    models/
      input_schema.py
      output_schema.py
      claim_schema.py
      score_schema.py
    services/
      llm_client.py
      evidence_search.py
      config_loader.py
    configs/
      scoring_weights.yml
      source_tiers.yml
      evidence_hierarchy.yml
      red_flags.yml
      disease_profiles/
        pancreatic_cancer.yml
        biliary_cancer.yml
        gastric_cancer.yml
    prompts/
      claim_extraction.md
      evidence_check.md
      scoring_rubric.md
      risk_assessment.md
    tests/
      test_scoring_engine.py
      test_risk_gate.py
      test_source_classifier.py
      test_claim_extractor.py
    examples/
      sample_inputs.jsonl
      sample_outputs.jsonl
  README.md
  pyproject.toml
```

---

## 六、输入格式

系统需要支持最小输入：

```json
{
  "title": "某某神药让晚期胰腺癌患者重获新生",
  "content": "文章正文或视频转写内容",
  "url": "https://example.com/article",
  "platform": "wechat",
  "author": "某医生",
  "published_at": "2026-06-16",
  "disease": "pancreatic_cancer",
  "metadata": {
    "account_name": "xxx",
    "account_type": "doctor_account",
    "has_commercial_contact": true
  }
}
```

字段说明：

```text
title: 标题
content: 正文或视频转写文本
url: 原文链接，可为空
platform: wechat / video_account / xhs / web / hospital_site / guideline / journal / unknown
author: 作者，可为空
published_at: 发布时间，可为空
disease: 疾病领域，可为空
metadata: 扩展字段
```

---

## 七、输出格式

输出必须包含：

```json
{
  "input_id": "可选",
  "overall_score": 0,
  "grade": "A/B/C/D/E",
  "risk_level": "R0/R1/R2/R3/R4/R5",
  "harm_risk_score": 0,
  "evidence_tag": "guideline / consensus / peer_reviewed_study / doctor_education / media_report / anecdote / marketing / high_risk_misinformation",
  "recommended_action": "",
  "summary": "",
  "dimension_scores": {
    "source_credibility": 0,
    "evidence_data_quality": 0,
    "clinical_content_quality": 0,
    "conclusion_risk_orientation": 0
  },
  "claims": [
    {
      "claim_id": "C1",
      "claim": "",
      "claim_type": "treatment_effect / diagnosis / prognosis / side_effect / guideline_recommendation / commercial_claim / other",
      "disease": "",
      "intervention": "",
      "population": "",
      "line_of_therapy": "",
      "claimed_outcome": "",
      "support_status": "supported / partially_supported / unsupported / contradicted / insufficient",
      "evidence_level": "",
      "notes": ""
    }
  ],
  "red_flags": [
    {
      "id": "",
      "name": "",
      "matched_text": "",
      "risk_level": "",
      "score_cap": 0,
      "reason": ""
    }
  ],
  "explanation": "",
  "version": "0.1.0"
}
```

---

## 八、配置文件设计

### 1. scoring_weights.yml

```yaml
version: "0.1.0"

dimensions:
  source_credibility:
    max_points: 25
    weight: 0.25
  evidence_data_quality:
    max_points: 35
    weight: 0.35
  clinical_content_quality:
    max_points: 25
    weight: 0.25
  conclusion_risk_orientation:
    max_points: 15
    weight: 0.15

grade_thresholds:
  A: 85
  B: 70
  C: 55
  D: 40
  E: 0
```

---

### 2. source_tiers.yml

```yaml
source_tiers:
  S0_guideline_regulatory:
    prior_score: 95
    examples:
      - NCCN
      - CSCO
      - ASCO
      - ESMO
      - CACA
      - FDA
      - EMA
      - NMPA
      - 国家卫健委
    description: "正式指南、共识、监管文件、药品说明书"

  S1_peer_reviewed_evidence:
    prior_score: 88
    examples:
      - PubMed
      - JCO
      - NEJM
      - Lancet Oncology
      - Annals of Oncology
      - ClinicalTrials.gov
    description: "同行评议论文、临床试验注册、会议正式摘要"

  S2_hospital_professional:
    prior_score: 78
    examples:
      - 三甲医院官网
      - 癌症中心官网
      - 学会官网
      - 实名专科医生科普
    description: "专业医疗机构或实名医生内容，需要检查引用和商业导流"

  S3_medical_media_doctor_account:
    prior_score: 65
    examples:
      - 医学媒体
      - 医生个人号
      - 会议解读
    description: "有一定参考价值，但需要证据核查"

  S4_social_media_general:
    prior_score: 45
    examples:
      - 普通公众号
      - 视频号
      - 小红书
      - 抖音
      - 快手
    description: "社交媒体内容，默认需要强校验"

  S5_marketing_high_risk:
    prior_score: 20
    examples:
      - 海外代诊营销
      - 神药广告
      - 秘方偏方
      - 非规范治疗
    description: "高风险营销信息，默认低分"
```

---

### 3. evidence_hierarchy.yml

```yaml
evidence_levels:
  guideline:
    score: 100
    label: "指南/共识"
  systematic_review_meta_analysis:
    score: 95
    label: "系统综述/Meta分析"
  phase3_rct:
    score: 90
    label: "III期随机对照研究"
  phase2_trial:
    score: 78
    label: "II期临床研究"
  phase1_trial:
    score: 65
    label: "I期临床研究"
  real_world_study:
    score: 65
    label: "真实世界研究"
  case_series:
    score: 50
    label: "病例系列"
  case_report:
    score: 35
    label: "单病例"
  expert_opinion:
    score: 45
    label: "专家观点"
  media_report:
    score: 30
    label: "媒体报道"
  marketing_claim:
    score: 15
    label: "营销话术"
  no_evidence:
    score: 0
    label: "无证据"
```

---

### 4. red_flags.yml

```yaml
hard_gates:
  - id: stop_standard_treatment
    name: "建议停止或替代规范治疗"
    patterns:
      - "不用化疗"
      - "停止化疗"
      - "不需要手术"
      - "替代放疗"
      - "替代标准治疗"
      - "不用去医院"
    risk_level: R5
    score_cap: 25
    harm_risk_score_min: 90

  - id: cancer_cure_claim
    name: "宣称治愈癌症或包有效"
    patterns:
      - "治愈癌症"
      - "根治晚期"
      - "癌症克星"
      - "100%有效"
      - "包治"
      - "无副作用"
    risk_level: R5
    score_cap: 30
    harm_risk_score_min: 90

  - id: miracle_drug_or_secret_formula
    name: "神药、秘方或夸大宣传"
    patterns:
      - "神药"
      - "秘方"
      - "祖传"
      - "医生不会告诉你"
      - "国外才有"
      - "唯一希望"
    risk_level: R4
    score_cap: 40
    harm_risk_score_min: 75

  - id: anecdote_overclaim
    name: "单病例外推"
    patterns:
      - "一个患者用了以后肿瘤消失"
      - "亲身经历证明"
      - "真实案例说明有效"
      - "用了之后完全缓解"
    risk_level: R4
    score_cap: 45
    harm_risk_score_min: 70

  - id: commercial_referral
    name: "商业导流或海外代诊诱导"
    patterns:
      - "私信咨询"
      - "名额有限"
      - "海外会诊通道"
      - "包入组"
      - "内部渠道"
      - "加微信"
    risk_level: R4
    score_cap: 45
    harm_risk_score_min: 70
```

---

### 5. disease_profiles/pancreatic_cancer.yml

```yaml
disease: pancreatic_cancer
name: "胰腺癌"

required_fields_for_treatment_claim:
  - cancer_type
  - stage
  - line_of_therapy
  - molecular_marker
  - intervention
  - comparator
  - sample_size
  - study_phase
  - endpoint
  - toxicity
  - approval_status
  - guideline_position

important_outcomes:
  - OS
  - PFS
  - ORR
  - DCR
  - DoR
  - grade_3_or_higher_AE
  - treatment_discontinuation

standard_warning_rules:
  - "只讲ORR不讲PFS/OS，需要扣分"
  - "只讲单病例，不得推导普遍疗效"
  - "I/II期研究不得包装为标准治疗"
  - "临床试验药物不得包装为已上市可及治疗"
  - "营养品、中医、补充疗法不得宣称替代抗肿瘤治疗"
  - "海外就医信息必须说明获批状态、适应症、入组条件、风险、费用和不确定性"
```

---

## 九、核心模块说明

### 1. ConfigLoader

职责：

1. 加载所有 YAML 配置。
2. 支持热更新或重启后更新。
3. 对配置进行 schema 校验。
4. 允许后续增加 disease profile。

接口示例：

```python
config = ConfigLoader.load("configs/")
```

---

### 2. SourceClassifier

职责：

1. 根据 platform、author、url、metadata 判断 source tier。
2. 输出 source_tier、prior_score、reason。
3. 不做最终评分，只提供信源先验。

输出示例：

```json
{
  "source_tier": "S3_medical_media_doctor_account",
  "prior_score": 65,
  "reason": "来源为医生个人科普账号，但未检测到明确指南引用。"
}
```

---

### 3. ClaimExtractor

职责：

1. 将文章拆成多个医学主张。
2. 每个 claim 需要识别疾病、治疗、适应症、人群、线数、终点、证据类型。
3. 可以用 LLM，也可以先用规则辅助。

需要识别的 claim_type：

```text
treatment_effect
diagnosis
prognosis
side_effect
guideline_recommendation
drug_approval
clinical_trial
nutrition
traditional_medicine
overseas_medical_service
commercial_claim
other
```

输出示例：

```json
{
  "claim_id": "C1",
  "claim": "某药可以显著延长晚期胰腺癌患者生存",
  "claim_type": "treatment_effect",
  "disease": "pancreatic_cancer",
  "intervention": "某药",
  "population": "晚期胰腺癌",
  "line_of_therapy": "unknown",
  "claimed_outcome": "OS"
}
```

---

### 4. RiskGate

职责：

1. 根据 red_flags.yml 匹配高风险表达。
2. 支持关键词匹配、正则匹配、LLM 语义判断。
3. 输出 red_flags。
4. 应用 score_cap。
5. 计算 harm_risk_score。

规则：

```text
如果命中多个 red flag，采用最高风险等级。
如果存在 score_cap，则最终 overall_score 不得超过所有命中规则中的最低 score_cap。
```

---

### 5. EvidenceClassifier

职责：

1. 判断每个 claim 的证据层级。
2. 第一版可以不做联网检索，只根据文本中引用信息判断。
3. 后续扩展 evidence_search.py，接入 PubMed、ClinicalTrials.gov、指南数据库、内部 RAG。

支持状态：

```text
supported
partially_supported
unsupported
contradicted
insufficient
```

证据层级：

```text
guideline
consensus
systematic_review_meta_analysis
phase3_rct
phase2_trial
phase1_trial
real_world_study
case_series
case_report
expert_opinion
media_report
marketing_claim
no_evidence
```

---

### 6. ScoringEngine

职责：

根据四个维度计算分数。

#### A. 信源可信度 25 分

子项：

```yaml
source_credibility_items:
  institution_level:
    max_points: 8
  author_identity:
    max_points: 5
  citation_traceability:
    max_points: 5
  update_time:
    max_points: 3
  conflict_of_interest_disclosure:
    max_points: 4
```

#### B. 证据与数据质量 35 分

子项：

```yaml
evidence_data_quality_items:
  evidence_level:
    max_points: 10
  guideline_consistency:
    max_points: 7
  data_completeness:
    max_points: 6
  population_match:
    max_points: 5
  outcome_interpretation:
    max_points: 4
  multi_source_consistency:
    max_points: 3
```

#### C. 内容医学质量 25 分

子项：

```yaml
clinical_content_quality_items:
  indication_boundary:
    max_points: 5
  treatment_position:
    max_points: 5
  risk_side_effects:
    max_points: 5
  alternative_options:
    max_points: 4
  uncertainty_expression:
    max_points: 3
  patient_action_advice:
    max_points: 3
```

#### D. 结论导向与风险 15 分

子项：

```yaml
conclusion_risk_orientation_items:
  restrained_conclusion:
    max_points: 5
  avoid_fear_marketing:
    max_points: 3
  avoid_commercial_induction:
    max_points: 4
  respect_standard_care:
    max_points: 3
```

---

### 7. ReportGenerator

职责：

生成自然语言评分报告。

报告格式：

```markdown
## 信息质量评分报告

标题：
来源：
作者：
平台：
发布时间：

### 总评
IQS：
等级：
风险：
建议：

### 主要医学主张
1. ...
2. ...

### 证据核查
| 主张 | 支持状态 | 证据层级 | 问题 |
|---|---|---|---|

### 四维评分
| 维度 | 得分 | 说明 |
|---|---:|---|
| 信源可信度 | ... | ... |
| 证据与数据质量 | ... | ... |
| 内容医学质量 | ... | ... |
| 结论导向与风险 | ... | ... |

### 红旗信号
- ...

### 结论
...
```

---

## 十、API 设计

### POST /score

输入一篇内容，返回评分结果。

Request:

```json
{
  "title": "文章标题",
  "content": "文章正文",
  "url": "",
  "platform": "wechat",
  "author": "",
  "published_at": "",
  "disease": "pancreatic_cancer",
  "metadata": {}
}
```

Response:

```json
{
  "overall_score": 72,
  "grade": "B",
  "risk_level": "R2",
  "harm_risk_score": 25,
  "recommended_action": "可作为科普参考，但不应作为治疗决策依据",
  "dimension_scores": {},
  "claims": [],
  "red_flags": [],
  "explanation": ""
}
```

---

### POST /score/batch

支持批量评分。

Request:

```json
{
  "items": [
    {
      "title": "",
      "content": "",
      "platform": "",
      "author": ""
    }
  ]
}
```

---

### GET /config/version

返回当前规则版本。

Response:

```json
{
  "version": "0.1.0",
  "loaded_configs": [
    "scoring_weights.yml",
    "source_tiers.yml",
    "evidence_hierarchy.yml",
    "red_flags.yml",
    "disease_profiles/pancreatic_cancer.yml"
  ]
}
```

---

## 十一、测试样例

### 样例 1：指南内容

输入：

```json
{
  "title": "NCCN 胰腺癌治疗指南更新",
  "content": "本文介绍 NCCN 对转移性胰腺癌一线治疗的推荐，包括 FOLFIRINOX 和吉西他滨联合白蛋白紫杉醇等方案。",
  "platform": "guideline",
  "author": "NCCN",
  "disease": "pancreatic_cancer"
}
```

期望：

```text
score >= 85
grade = A
risk_level = R0 or R1
```

---

### 样例 2：医生科普

输入：

```json
{
  "title": "胰腺癌患者如何理解 ORR、PFS 和 OS",
  "content": "本文解释 ORR、PFS、OS 的区别，并提醒患者不要只看有效率，需要结合生存获益和副作用，由主治医生判断。",
  "platform": "wechat",
  "author": "实名肿瘤科医生",
  "disease": "pancreatic_cancer"
}
```

期望：

```text
score 70-85
grade = B or A
risk_level = R0 or R1
```

---

### 样例 3：单病例夸大

输入：

```json
{
  "title": "一个晚期胰腺癌患者用了某疗法后肿瘤消失",
  "content": "真实案例证明该疗法有效，晚期患者不要放弃，详情私信咨询。",
  "platform": "video_account",
  "author": "未知",
  "disease": "pancreatic_cancer"
}
```

期望：

```text
score <= 45
grade = D or E
risk_level = R4
red_flags 包含 anecdote_overclaim 和 commercial_referral
```

---

### 样例 4：神药宣传

输入：

```json
{
  "title": "癌症克星来了，不用化疗也能治愈晚期癌症",
  "content": "该神药无副作用，100%有效，医生不会告诉你，想了解加微信。",
  "platform": "xhs",
  "author": "未知",
  "disease": "pancreatic_cancer"
}
```

期望：

```text
score <= 30
grade = E
risk_level = R5
harm_risk_score >= 90
```

---

### 样例 5：中医支持治疗

输入：

```json
{
  "title": "胰腺癌治疗期间如何用中医改善食欲和睡眠",
  "content": "本文强调中医只能作为支持治疗，不能替代手术、化疗、放疗或靶向治疗。患者应在医生指导下使用。",
  "platform": "wechat",
  "author": "中西医结合医生",
  "disease": "pancreatic_cancer"
}
```

期望：

```text
score 55-75
grade = C or B
risk_level = R1 or R2
不能因为出现中医二字直接判 E
```

---

### 样例 6：中医替代抗癌

输入：

```json
{
  "title": "不用化疗，中医秘方让胰腺癌缩瘤",
  "content": "很多患者用了这个秘方后肿瘤明显缩小，化疗太伤身体，建议尽早改用中医。",
  "platform": "video_account",
  "author": "未知",
  "disease": "pancreatic_cancer"
}
```

期望：

```text
score <= 35
grade = E
risk_level = R5
red_flags 包含 stop_standard_treatment 和 miracle_drug_or_secret_formula
```

---

## 十二、开发要求

1. 所有评分权重、信源分层、红旗词、疾病规则必须从 YAML 读取。
2. 不允许在 Python 代码中写死具体医学规则。
3. 每个评分结果必须可解释。
4. 命中红旗规则时必须输出 matched_text、risk_level、score_cap、reason。
5. claim_extractor 可以先用 mock 或规则实现，但接口要保留 LLM 扩展能力。
6. evidence_search 第一版可以为空实现，但需要预留接口。
7. 所有模块必须有单元测试。
8. README 需要说明如何启动、如何修改配置、如何新增疾病 profile。
9. 输出 JSON 必须稳定，便于前端和后续数据库存储。
10. 后续要支持人工标注样本校准，所以请保留 calibration_cases.jsonl 格式。

---

## 十三、第一版 MVP 交付目标

第一版完成以下功能即可：

1. FastAPI 服务可启动。
2. POST /score 可输入文章并返回评分。
3. 支持读取 YAML 配置。
4. 支持信源分类。
5. 支持红旗规则匹配。
6. 支持简单 claim 抽取。
7. 支持四维评分。
8. 支持分数上限 score_cap。
9. 支持 Markdown 评分报告生成。
10. 提供 6 个测试样例，全部通过 pytest。

---

## 十四、后续迭代方向

第二阶段：

1. 接入 PubMed / ClinicalTrials.gov / 指南知识库检索。
2. 对每个 claim 做证据匹配。
3. 增加 RAG。
4. 增加人工复核后台。
5. 增加医生账号白名单、灰名单、风险账号库。
6. 增加视频转写输入。
7. 增加批量文章评分。
8. 增加数据库存储和历史评分版本追踪。

第三阶段：

1. 基于人工标注样本训练校准器。
2. 对不同癌种建立 disease profile。
3. 支持多 Agent 流程：

   * Claim Extraction Agent
   * Evidence Verification Agent
   * Risk Detection Agent
   * Scoring Agent
   * Report Writing Agent
4. 支持信息流监控和自动预警。
5. 接入小胰宝 OSINT / War Room 系统。

---

## 十五、开发时请优先实现的类

请优先实现以下类：

```text
ConfigLoader
MedicalInfoInput
MedicalInfoScoreOutput
SourceClassifier
ClaimExtractor
RiskGate
EvidenceClassifier
ScoringEngine
ReportGenerator
```

建议调用流程：

```text
input
  -> ConfigLoader
  -> SourceClassifier
  -> ClaimExtractor
  -> RiskGate
  -> EvidenceClassifier
  -> ScoringEngine
  -> ReportGenerator
  -> output
```

---

## 十六、重要边界

1. Agent 不做诊断。
2. Agent 不给患者具体治疗建议。
3. Agent 只评价信息质量和传播风险。
4. 输出中必须提示：医疗决策应由医生结合患者具体情况判断。
5. 对中医、营养品、海外就医不能简单关键词封杀，要根据是否替代规范治疗、是否夸大疗效、是否商业诱导来判断。
6. 对指南、医生、医院来源也不能无条件高分，如果存在断章取义、商业导流或危险建议，需要降级。

---

## 十七、最终目标

构建一个可配置、可解释、可迭代的医疗信息质量评分 Agent。

第一版重点不是追求医学知识库完美，而是先建立稳定的评分骨架、红旗闸门、配置体系和输出结构，为后续接入指南、论文、临床试验、医生审核和 OSINT 系统打基础。

