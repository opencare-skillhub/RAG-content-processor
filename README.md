# FastGPT 内容处理器

一个用于管理和处理 FastGPT 知识库内容的命令行工具，支持知识库查询、内容搜索、文件上传，以及微信公众号文章的下载、清理和上传。

## 功能特性

- **list-datasets**: 列出所有 FastGPT 知识库
- **list-collections**: 列出指定知识库下的文章/集合
- **search**: 在知识库中搜索内容（语义搜索）
- **upload-file**: 上传单个 Markdown 文件到知识库
- **upload-folder**: 批量上传整个文件夹的 Markdown 文件
- **download-wechat**: 批量下载微信公众号文章（通过 MCP 服务）
- **clean-wechat**: 两阶段清理微信公众号文章
- **download-and-clean**: 一站式处理（下载 → 清理 → 上传）

## 安装与运行

### 推荐方式：uv

```bash
cd fastgpt-content-processor
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

### 标准方式：venv

```bash
cd fastgpt-content-processor
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

### 运行方式

```bash
python3 main.py --help
python3 main.py list-datasets
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS 突变"
```

> 提示：如果你直接在系统环境中运行，可能会出现 `python: command not found`。本项目统一建议使用 `python3`，并优先在独立虚拟环境中执行。

## 环境变量配置

在 `.env` 文件中配置：

```env
# FastGPT 配置
FASTGPT_BASE_URL=https://your-fastgpt-domain.com
FASTGPT_API_KEY=your-api-key-here

# 知识库质检 Agent（规划中，见下方路线图）
# QA_AGENT_PROVIDER=qwen          # 质检使用的 LLM 提供方
# QA_AGENT_API_KEY=your-key       # 对应的 API Key
# QA_AGENT_BASE_URL=https://...   # 对应的 API 地址
# QA_AGENT_SCORE_THRESHOLD=85     # 上传准入分数（默认 85）
```

## 使用示例

### 列出所有知识库

```bash
python3 main.py list-datasets
```

### 列出知识库下的文章

```bash
python3 main.py list-collections --dataset-id 697b19a113081cf58b45cac3
```

### 在知识库中搜索

```bash
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS 突变"
```

### 上传单个文件

```bash
python3 main.py upload-file --file article.md --dataset-id 697b19a113081cf58b45cac3
```

### 批量上传文件夹

```bash
python3 main.py upload-folder --folder ./articles --dataset-id 697b19a113081cf58b45cac3
```

### 下载微信公众号文章

创建 `urls.txt`，每行一个微信文章 URL，然后：

```bash
python3 main.py download-wechat --urls urls.txt --output ./wechat-downloads
```

### 清理微信公众号文章

```bash
python3 main.py clean-wechat --input ./wechat-downloads --output ./cleaned-articles
```

### 一站式处理（下载 → 清理 → 上传）

```bash
python3 main.py download-and-clean \
  --urls urls.txt \
  --output ./wechat-downloads \
  --cleaned-output ./cleaned-articles \
  --dataset-id 697b19a113081cf58b45cac3
```

#### 用 LLM 富化 frontmatter（可选）

默认清洗后的 frontmatter 中 `summary`/`description`/`tags` 为空（规则提取不到）。
加 `--enrich` 会用一次低成本 LLM 生成这些字段，写入 frontmatter。

```bash
# 复用 QA_AGENT_* 配置（开箱即用）
python3 main.py download-and-clean \
  --urls "https://mp.weixin.qq.com/s/xxx" \
  --enrich

# 推荐：配免费/低成本模型，速度快
# .env 中加：ENRICHER_MODEL=glm-4.5-air + ENRICHER_BASE_URL + ENRICHER_API_KEY
```

### 人工精选文章 QA 入库（一期流程）

一期核心流程：**人工精选文章 → 自动整理 QA → 生成文章标签 → 打 QA 分数 → 分级入库**。
`qa-ingest` 会对人工精选的本地文章做 QA 评分，产出结构化报告与增强 Markdown，
并按分数/等级决定是否上传。低于阈值或 D 级的内容会被跳过，**不会自动上传**。

```bash
# 仅评分、生成本地报告与增强 Markdown（不调 FastGPT）
python3 main.py qa-ingest \
  --input ./cleaned-articles \
  --output ./qa-output \
  --report-dir ./qa-reports

# 评分 + 按权重上传到知识库（省略 --dataset-id 则只本地，不上传）
python3 main.py qa-ingest \
  --input ./cleaned-articles \
  --output ./qa-output \
  --report-dir ./qa-reports \
  --dataset-id 697b19a113081cf58b45cac3

# dry-run：只列出将处理的文件与配置，不调 LLM、不上传
python3 main.py qa-ingest --input ./cleaned-articles --dry-run
```

- `./qa-reports/*.qa.json` 含 `display_tags`、`structured_tags`、`qa_pairs`、
  `qa_score`、`grade`、`library_action`、`qa_weight`、`score_detail`。
- `./qa-output/` 产出注入了 QA frontmatter 的增强 Markdown。
- 评分规则在 `agents/rubrics/medical.yaml`，可按需迭代；阈值默认 85。

## 项目结构

```
fastgpt-content-processor/
├── main.py                      # 主程序入口
├── fastgpt_sync.py              # FastGPT API 封装
├── fetchers/                    # 内容抓取模块
│   ├── wechat_mcp.py           # 微信文章下载（MCP 服务）
│   └── file.py                 # 本地文件读取
├── cleaners/                    # 内容清理模块
│   ├── format_cleaner.py       # 阶段 1：格式清理
│   ├── frontmatter_doctor.py   # 阶段 2：Frontmatter 标准化
│   ├── wechat_markdown.py      # 微信文章清理（整合两阶段）
│   └── markdown.py             # Markdown 通用清理
├── utils/                       # 工具函数
│   ├── hash.py                 # Hash 计算
│   └── dedup.py                # 去重逻辑
├── tests/                       # 测试目录
├── .env.example                 # 环境变量模板
├── requirements.txt             # Python 依赖
└── README.md                    # 本文档
```

## 测试

请查看 [`tests/README.md`](tests/README.md)，其中列出了核心逻辑测试范围与后续测试主题建议。

### 运行测试

```bash
python3 -m pytest
```

只跑核心逻辑测试：

```bash
python3 -m pytest tests/test_core_logic.py
```

## 二开路线图

本项目建议优先走"稳健交付"路线：先完善环境、测试和文档，再逐步扩展能力。

### 短期：可复现与可验证
- 统一 `python3` 与虚拟环境说明
- 补齐核心逻辑测试
- 明确 FastGPT、MCP 与示例脚本的运行边界
- 提升文档一致性

### 中期：知识库质检 Agent（核心方向）
引入"上传前质检"机制，把原来未实现的翻译能力重新定位为**内容质量准入 Agent**，目标是保证只有合格内容才进入知识库。

设计要点：
- **内容分级**：根据专业度、完整性、来源可信度，给出等级（如 A/B/C 或 1-5 级）
- **标签化**：自动抽取主题标签、疾病/药物/临床领域标签
- **多维度评分**：从若干维度对内容打分，例如
  - 结构完整性（标题/正文/摘要是否齐全）
  - 信息密度（有效内容占比）
  - 来源可信度（公众号权威性、是否含营销噪音）
  - 时效性与可引用性
- **分数准入门槛**：综合分 ≥ 阈值（默认 85）才允许自动上传；低于阈值则暂停并询问用户，**不自动上传**
- **可配置**：阈值、维度权重、是否启用通过 `QA_AGENT_*` 环境变量控制
- **可观测**：每次质检输出结构化报告（分数、维度明细、建议），便于追溯

交互方式：
- 自动模式：分数达标 → 直接上传；不达标 → 跳过并记录到报告
- 交互模式：分数不达标 → 提示用户「跳过 / 强制上传 / 重新清理」

### 长期：可扩展与可平台化
- 插件化抓取器 / 清理器 / 质检器 / 上传适配器
- 支持更多内容源
- 支持更多知识库目标与导出格式
- 引入工作流化处理链路（下载 → 清理 → 质检 → 上传）
- 支持规则配置化与批量任务编排

## 如何贡献

欢迎贡献代码、文档、测试和使用经验。

### 推荐贡献方式
- 先提 issue 说明需求或问题
- 优先补测试，再改逻辑
- 保持文档与代码同步
- 新增清理规则时提供样例输入/输出
- 新增抓取器或上传适配时说明适用场景

### 适合贡献的方向
- 新的内容清理规则
- 新的数据源抓取器
- FastGPT 接口适配增强
- CLI 交互体验优化
- 测试覆盖率提升
- 示例与教程补充

## 致谢

感谢以下项目与资料为本项目提供了思路和参考：

- [wechat-article-downloader](https://github.com/qiye45/wechatDownload)
- [baoyu-format-markdown](https://github.com/baoyu-tech/markdown-formatter)
- [markdown-frontmatter-doctor](https://github.com/example/frontmatter-doctor)
- [FastGPT API 文档](https://doc.fastgpt.in/docs/development/api/)

## 许可证

MIT License

---

**其他语言版本**: [English](README.en.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [한국어](README.ko.md)
