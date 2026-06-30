# 快速入门

本文档面向新手，通过 3 个真实场景，直接给出可执行的 CLI 命令。

---

## 前置准备

```bash
# 1. 克隆仓库并安装依赖
git clone <repo-url>
cd fastgpt-content-processor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 复制环境变量模板
cp .env.example .env
```

编辑 `.env`，**至少填以下 4 项**（其余保持默认即可）：

```bash
# FastGPT 知识库（不上传可暂时不填）
FASTGPT_BASE_URL=https://your-domain.com/api
FASTGPT_API_KEY=your-fastgpt-key
FASTGPT_DATASET_ID=your-dataset-id

# LLM API Key（通义千问，用于 QA 评分和富化）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
```

> 💡 如果你有**智谱**或**硅基流动**的 key，可以一并填入 `.env` 的 `ZHIPUAI_API_KEY` / `SILICONFLOW_API_KEY`，富化器会自动选择更快/更便宜的模型。

---

## 场景一：下载并清洗一篇微信文章（默认含 LLM 富化）

**目标**：把一篇微信文章下载下来，清洗掉广告、UI 按钮、图片等噪音，并用 LLM 自动生成 `summary`/`description`/`tags`，最后写入 frontmatter。

```bash
python3 main.py download-and-clean \
  --urls "https://mp.weixin.qq.com/s/quXh4J5f0_lX2PM-cFMhlA"
```

**发生了什么**：
1. 下载文章到 `wechat-downloads/YYYYMMDD_HHMMSS/`
2. 清洗正文（删除微信扫一扫、赞/在看按钮、CDN 图片、版权声明等）
3. **自动调用 LLM** 生成摘要、描述、标签（默认选 `qwen3.6-flash`，有智谱 key 则选 `glm-4.5-air`）
4. 提取 frontmatter：`title`、`author`（公众号名）、`summary`、`description`、`tags`、`original_url`
5. 上传到 FastGPT 时，tags/summary 会作为 metadata 传入，方便 RAG 检索

**查看结果**：

```bash
cat wechat-downloads_cleaned/2026*/国内唯一*.md | head -20
```

预期 frontmatter：
```yaml
---
title: 国内唯一！领泰生物口服KRAS G12D PROTAC获中国CDE批准进入临床
author: 药融圈
summary: 领泰生物自主研发的全球首创口服KRAS G12D靶向蛋白降解剂LT-010391正式获得中国CDE临床试验批准，是国内唯一进入临床阶段的口服KRAS降解剂。
description: 领泰生物口服KRAS G12D PROTAC获CDE临床批准
tags:
  - KRAS
  - PROTAC
  - 靶向治疗
  - 临床试验
  - 领泰生物
  - 肿瘤
  - 创新药
original_url: https://mp.weixin.qq.com/s/quXh4J5f0_lX2PM-cFMhlA
---
```

> 💡 如果 LLM 调用失败（比如 key 用完），会降级为空，不阻断流程，只打印 warning。

**禁用 LLM 富化**（纯规则清洗，tags 为空）：

```bash
python3 main.py download-and-clean \
  --urls "https://mp.weixin.qq.com/s/quXh4J5f0_lX2PM-cFMhlA" \
  --no-enrich
```

---

## 场景二：处理本地已有文件（process-local，覆盖 .md/.txt/.html）

**目标**：清洗本地已有的文件（不限来源），自动按类型路由——Markdown 走格式清理、HTML 提取正文、TXT 去噪，默认 LLM 富化 frontmatter，可选直接上传知识库。

```bash
# 清洗 + 富化，输出到 ./cleaned
python3 main.py process-local --input ./some-dir --output ./cleaned

# 只清洗不富化
python3 main.py process-local --input ./some-dir --no-enrich

# 清洗 + 富化 + 上传知识库
python3 main.py process-local --input ./some-dir --dataset-id your-dataset-id

# dry-run：只列出文件与类型路由，不清洗/富化/上传
python3 main.py process-local --input ./some-dir --dry-run
```

**发生了什么**：
1. 收集 `.md/.txt/.html`（用 `--extensions` 可调）
2. 按类型清洗：`markdown→FormatCleaner`、`html→正文提取`、`text→去噪`
3. 默认 LLM 富化 `summary/description/tags`（`--no-enrich` 关闭）
4. 统一写出为带 frontmatter 的 `.md`；给定 `--dataset-id` 则去重上传

> 与「场景一」的区别：`download-and-clean` 从微信 URL 开始；`process-local` 处理**本地已有文件**，来源无关。

---

## 场景三：QA 评分 + 入库（质量门控）

**目标**：对清洗后的文章做专业 QA 评分（内容质量、标签准确度、安全边界），只有高分文章才上传到 FastGPT 知识库。

```bash
# 步骤 1：评分（生成本地报告，不上传）
python3 main.py qa-ingest \
  --input ./wechat-downloads_cleaned \
  --output ./qa-output \
  --report-dir ./qa-reports

# 步骤 2（可选）：评分 + 上传到知识库
python3 main.py qa-ingest \
  --input ./wechat-downloads_cleaned \
  --output ./qa-output \
  --report-dir ./qa-reports \
  --dataset-id 697b19a113081cf58b45cac3
```

**发生了什么**：
1. 读取每篇清洗后的文章
2. 调用 `qwen3.7-max`（评分专用模型）做专业 QA
3. 产出：
   - `qa-reports/*.qa.json`：分数、等级、标签、QA 问答对、扣分理由
   - `qa-output/*.md`：增强版 Markdown（frontmatter 注入 QA 字段）
4. 分数 ≥ 85 且等级 ≥ B 的文章才会上传（低分文章标记为 `skipped_by_qa`）

**查看评分报告**：

```bash
cat qa-reports/国内唯一*.qa.json | python3 -m json.tool
```

预期输出（节选）：
```json
{
  "qa_score": 90,
  "grade": "A",
  "library_action": "高权重入库",
  "qa_weight": 1.0,
  "display_tags": ["胰腺癌", "化疗副作用", "KRAS", "PROTAC"],
  "score_detail": {
    "source_quality": 25,
    "content_clarity": 25,
    "qa_usability": 25,
    "safety_boundary": 15
  },
  "passed": true
}
```

**dry-run（先预览，不调 LLM、不上传）**：

```bash
python3 main.py qa-ingest \
  --input ./wechat-downloads_cleaned \
  --output ./qa-output \
  --report-dir ./qa-reports \
  --dry-run
```

---

## 完整流程（一键串联）

如果你已经确认文章质量，可以直接走完整 pipeline：

```bash
# 1. 下载 + 清洗 + LLM 富化（默认自动执行）
python3 main.py download-and-clean \
  --urls "https://mp.weixin.qq.com/s/quXh4J5f0_lX2PM-cFMhlA" \
  --cleaned-output ./articles

# 2. QA 评分 + 入库
python3 main.py qa-ingest \
  --input ./articles \
  --output ./qa-output \
  --report-dir ./qa-reports \
  --dataset-id 697b19a113081cf58b45cac3
```

---

## 常见问题

### Q1: 报错 "缺少 API Key"
确认 `.env` 中至少填了 `DASHSCOPE_API_KEY`（通义千问）或 `ZHIPUAI_API_KEY`（智谱）或 `SILICONFLOW_API_KEY`（硅基流动）。系统会自动选择最快/最便宜的模型。

### Q2: 想换更便宜的模型做富化
在 `.env` 中显式覆盖：
```bash
ENRICHER_MODEL=glm-4.5-air
ENRICHER_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ENRICHER_API_KEY=你的智谱key
```

### Q3: 不想用 LLM，只要纯规则清洗
加 `--no-enrich`：
```bash
python3 main.py download-and-clean --urls urls.txt --no-enrich
```

### Q4: qa-ingest 上传了我不想入库的文章
QA 评分有门控：低于阈值（默认 85）或 D 级的文章会自动跳过，不会上传。你可以在 `qa-reports/*.qa.json` 里查看每篇的评分和 `library_action`。

### Q5: 批量处理多篇文章
`--urls` 支持文件路径（每行一个 URL）：
```bash
echo "https://mp.weixin.qq.com/s/xxx" > urls.txt
echo "https://mp.weixin.qq.com/s/yyy" >> urls.txt
python3 main.py download-and-clean --urls urls.txt
```

---

## 下一步

- 想了解评分规则？看 `agents/rubrics/medical.yaml`
- 想改评分阈值？`.env` 中调 `QA_AGENT_SCORE_THRESHOLD`
- 想看全部 CLI 参数？`python3 main.py --help`
