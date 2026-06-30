---
name: fastgpt-content-processor
description: >
  开箱即用的 FastGPT 内容处理器：微信文章下载、清洗、LLM 富化标签、QA 评分、入库的一站式工作流。
  本 skill 包含完整项目代码，不依赖任何外部目录。用户只需配置 .env 即可运行。
  当用户提到"下载微信文章"、"清洗文章"、"生成标签"、"QA 评分"、"入库 FastGPT"、
  "处理这篇文章"并附上 mp.weixin.qq.com 链接、或说"rag 入库"、"知识库上传"、"文章打标签"时触发。
---

# FastGPT Content Processor Skill

## 项目路径（固定，不探测）

本 skill 自带完整代码，项目位于：

```
~/.agents/skills/fastgpt-content-processor/
```

所有命令均在此目录下执行。用户无需关心外部目录。

## 开箱即用检查

```bash
cd ~/.agents/skills/fastgpt-content-processor

# 1. 检查 .env（必需）
ls .env 2>/dev/null || echo "请先创建 .env：cp .env.example .env，然后填入 API Key"

# 2. 检查依赖
uv run python3 -c "import openai" 2>/dev/null || uv pip install -r requirements.txt

# 3. 运行测试确认一切正常
uv run python3 -m pytest -q
```

## .env 配置（用户手工填写，绝不泄露）

复制 `.env.example` 为 `.env`，填入以下内容：

```bash
# 必需：通义千问 API Key（用于 QA 评分和默认富化）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

# 可选：FastGPT 上传（不上传可暂时不填）
FASTGPT_BASE_URL=https://your-domain.com/api
FASTGPT_API_KEY=your-fastgpt-key
FASTGPT_DATASET_ID=your-dataset-id

# 可选：智谱/硅基流动 key（富化器会自动选更便宜的模型）
# ZHIPUAI_API_KEY=your-zhipuai-key        # 自动选 glm-4.5-air（免费）
# SILICONFLOW_API_KEY=your-siliconflow-key # 自动选 step-3.5-flash（低成本）
```

> ⚠️ **绝不向用户展示 .env 内容。若用户未配置，提示其填入，不要替用户填写。**

## 核心命令

所有命令前缀均为：
```bash
cd ~/.agents/skills/fastgpt-content-processor
uv run python3 main.py ...
```

### 1. 下载 + 清洗 + LLM 富化（默认行为）

```bash
cd ~/.agents/skills/fastgpt-content-processor
uv run python3 main.py download-and-clean \
  --urls "https://mp.weixin.qq.com/s/xxx" \
  --cleaned-output ./articles
```

**自动执行**：
1. 下载文章
2. 清洗噪音（微信扫一扫、赞/在看、CDN 图片、版权声明等）
3. LLM 自动生成 summary / description / tags（默认选 qwen3.6-flash，有智谱 key 则选 glm-4.5-air）
4. 写入 frontmatter

**输出**：`articles/YYYYMMDD_HHMMSS/[title].md`

### 2. 禁用 LLM 富化（纯规则）

```bash
cd ~/.agents/skills/fastgpt-content-processor
uv run python3 main.py download-and-clean \
  --urls "https://mp.weixin.qq.com/s/xxx" \
  --cleaned-output ./articles \
  --no-enrich
```

### 3. 处理本地文件（process-local，来源无关）

清洗本地已有文件，覆盖 `.md/.txt/.html`：按类型自动路由清洗（Markdown 格式清理 / HTML 正文提取 / 纯文本去噪），默认 LLM 富化 frontmatter，可选去重上传。

```bash
cd ~/.agents/skills/fastgpt-content-processor

# 清洗 + 富化，输出到 ./cleaned
uv run python3 main.py process-local --input ./some-dir --output ./cleaned

# 只清洗不富化
uv run python3 main.py process-local --input ./some-dir --no-enrich

# 清洗 + 富化 + 上传知识库（需配置 FASTGPT_*）
uv run python3 main.py process-local --input ./some-dir --dataset-id your-dataset-id

# dry-run：只列出文件与类型路由
uv run python3 main.py process-local --input ./some-dir --dry-run
```

> `clean-wechat` 现也支持 `--extensions`（默认 `.md`）与默认 LLM 富化（`--no-enrich` 关闭）。

### 4. QA 评分 + 入库（质量门控）

```bash
cd ~/.agents/skills/fastgpt-content-processor

# 仅评分（不上传）
uv run python3 main.py qa-ingest \
  --input ./articles \
  --output ./qa-output \
  --report-dir ./qa-reports

# 评分 + 上传通过的文章（需配置 FASTGPT_*）
uv run python3 main.py qa-ingest \
  --input ./articles \
  --output ./qa-output \
  --report-dir ./qa-reports \
  --dataset-id your-dataset-id
```

- 默认阈值 85，低于阈值或 D 级自动跳过不上传
- 评分模型固定 `qwen3.7-max`

### 5. Dry-run（预览，不花钱）

```bash
cd ~/.agents/skills/fastgpt-content-processor
uv run python3 main.py qa-ingest \
  --input ./articles \
  --dry-run
```

## 文件输出结构

```
~/.agents/skills/fastgpt-content-processor/
├── articles/YYYYMMDD_HHMMSS/
│   └── [title].md              # 带 frontmatter 的清洗后文章
├── qa-reports/
│   └── [title].qa.json         # 评分报告
├── qa-output/
│   └── [title].md              # 增强版（含 qa_* 字段）
└── ...
```

## Frontmatter 示例

```yaml
---
title: 国内唯一！领泰生物口服KRAS G12D PROTAC获中国CDE批准进入临床
author: 药融圈
summary: 领泰生物口服KRAS G12D PROTAC药物LT-010391获中国CDE临床批准...
description: 领泰生物口服KRAS G12D PROTAC药物获批临床，填补国内空白。
tags:
  - PROTAC技术
  - KRAS突变
  - 靶向降解
  - 临床试验
  - 创新药研发
original_url: https://mp.weixin.qq.com/s/xxx
---
```

## 故障排查

| 症状 | 解决 |
|---|---|
| `No module named 'openai'` | `cd ~/.agents/skills/fastgpt-content-processor && uv pip install -r requirements.txt` |
| `缺少 API Key` | 确认 `.env` 中有 `DASHSCOPE_API_KEY` |
| 富化太慢 | `.env` 中加 `ENRICHER_MODEL=qwen3.6-flash` |
| 想换免费模型 | `.env` 中加 `ZHIPUAI_API_KEY`（自动选 glm-4.5-air） |

## 测试

```bash
cd ~/.agents/skills/fastgpt-content-processor
uv run python3 -m pytest -q
```

## 项目结构速览

```
~/.agents/skills/fastgpt-content-processor/
├── main.py                    # CLI 入口
├── .env.example               # 配置模板
├── quick-start.md             # 新手快速入门
├── agents/                    # LLM 富化器、QA 评分器
├── cleaners/                  # 格式清洗、frontmatter 标准化
├── fetchers/                  # 微信文章下载器（MCP）
├── tests/                     # 104 个单元测试
└── docs/dev.log               # 开发记录
```
