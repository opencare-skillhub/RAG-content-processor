#!/usr/bin/env python3
"""使用示例脚本"""
from processor import ContentProcessor

def demo_text_processing():
    """演示文本处理"""
    processor = ContentProcessor()
    
    # 处理包含广告和营销内容的文本
    test_content = """
    这是一篇关于人工智能的文章。
    
    编辑：张三
    发布时间：2026-06-16
    
    人工智能正在改变我们的生活方式。
    
    长按识别二维码关注我们
    点击阅读原文查看更多
    
    这是文章的正文内容。
    """
    
    print("=== 文本处理演示 ===")
    processor.process_text(test_content, "AI文章测试")


def demo_markdown_processing():
    """演示 Markdown 处理"""
    processor = ContentProcessor()
    
    # 创建测试 Markdown 文件
    test_md = """---
title: 测试文章
author: 张三
date: 2026-06-16
---

# 测试标题

这是正文内容。

<!-- 这是元数据注释 -->

## 子标题

更多内容...
"""
    
    with open("test_article.md", "w", encoding="utf-8") as f:
        f.write(test_md)
    
    print("=== Markdown 处理演示 ===")
    processor.process_file("test_article.md")


def demo_wechat_article():
    """演示微信文章处理（需要真实 URL）"""
    processor = ContentProcessor()
    
    print("=== 微信文章处理演示 ===")
    print("提示：请提供真实的微信文章 URL")
    # url = input("请输入微信文章 URL: ")
    # processor.process_url(url)


if __name__ == "__main__":
    print("FastGPT 内容处理器 - 使用示例\n")
    
    # 文本处理
    demo_text_processing()
    
    # Markdown 处理
    demo_markdown_processing()
    
    # 微信文章处理（可选）
    # demo_wechat_article()
    
    print("\n✅ 示例运行完成")
