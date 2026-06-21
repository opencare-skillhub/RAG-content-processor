# FastGPT 工作流配置目录

此目录用于存放 FastGPT 工作流的 JSON 配置文件。

## 使用说明

1. 将 FastGPT 导出的工作流 JSON 文件放置在此目录
2. 后续版本将支持自动加载和执行工作流

## 示例工作流结构

```json
{
  "name": "内容处理工作流",
  "nodes": [
    {
      "type": "input",
      "name": "接收内容"
    },
    {
      "type": "process",
      "name": "清理内容"
    },
    {
      "type": "output",
      "name": "写入知识库"
    }
  ],
  "edges": [
    {"from": "接收内容", "to": "清理内容"},
    {"from": "清理内容", "to": "写入知识库"}
  ]
}
```

## 后续计划

- [ ] 支持从 FastGPT 导入工作流 JSON
- [ ] 工作流可视化编辑
- [ ] 工作流执行日志
- [ ] 工作流版本管理
