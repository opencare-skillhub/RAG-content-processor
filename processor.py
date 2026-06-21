"""内容处理器 - 协调各个模块"""
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import os

from utils import DedupManager, calculate_hash, calculate_file_hash
from cleaners import TextCleaner, MarkdownCleaner, WechatArticleCleaner
from fetchers import FileFetcher, WechatArticleFetcher
from fastgpt_sync import FastGPTSyncer


class ContentProcessor:
    """内容处理器主类"""
    
    def __init__(self, env_file: str = ".env"):
        # 加载环境变量
        load_dotenv(env_file)
        
        # 初始化 FastGPT 同步器
        self.fastgpt = FastGPTSyncer(
            base_url=os.getenv("FASTGPT_BASE_URL"),
            api_key=os.getenv("FASTGPT_API_KEY"),
            dataset_id=os.getenv("FASTGPT_DATASET_ID")
        )
        
        # 初始化去重管理器
        self.dedup = DedupManager()
        
        # 初始化抓取器
        self.file_fetcher = FileFetcher(
            scan_dir=os.getenv("SCAN_DIR", "./input")
        )
        self.wechat_fetcher = WechatArticleFetcher()
        
        # 初始化清理器
        self.text_cleaner = TextCleaner()
        self.markdown_cleaner = MarkdownCleaner()
        self.wechat_cleaner = WechatArticleCleaner()
        
        # 输出目录
        self.output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def process_text(self, content: str, title: str = "文本内容") -> bool:
        """处理纯文本内容
        
        Args:
            content: 文本内容
            title: 内容标题
            
        Returns:
            处理是否成功
        """
        print(f"\n📝 处理文本: {title}")
        
        # 清理内容
        cleaned = self.text_cleaner.clean(content)
        
        # 计算 Hash
        content_hash = calculate_hash(cleaned)
        identifier = f"text:{title}"
        
        # 去重检查
        if self.dedup.is_duplicate(identifier, content_hash):
            print(f"⏭️  内容已存在，跳过: {title}")
            return True
        
        # 上传到 FastGPT
        success = self.fastgpt.upload_text(cleaned, title)
        
        if success:
            # 记录状态
            self.dedup.update_record(identifier, content_hash, {
                "type": "text",
                "title": title,
                "original_length": len(content),
                "cleaned_length": len(cleaned)
            })
        
        return success
    
    def process_file(self, file_path: str) -> bool:
        """处理本地文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            处理是否成功
        """
        print(f"\n📄 处理文件: {file_path}")
        
        # 抓取文件
        try:
            file_info = self.file_fetcher.fetch_file(file_path)
        except FileNotFoundError as e:
            print(f"❌ {e}")
            return False
        
        # 根据类型选择清理器
        content_type = file_info["type"]
        if content_type == "markdown":
            cleaned = self.markdown_cleaner.clean(file_info["content"])
        elif content_type == "html":
            cleaned = self.wechat_cleaner.clean(file_info["content"])
        else:
            cleaned = self.text_cleaner.clean(file_info["content"])
        
        # 计算 Hash
        content_hash = calculate_hash(cleaned)
        identifier = file_info["identifier"]
        
        # 去重检查
        if self.dedup.is_duplicate(identifier, content_hash):
            print(f"⏭️  文件已处理，跳过: {file_info['filename']}")
            return True
        
        # 上传到 FastGPT
        title = file_info["filename"]
        success = self.fastgpt.upload_text(cleaned, title)
        
        if success:
            # 记录状态
            self.dedup.update_record(identifier, content_hash, {
                "type": "file",
                "filename": file_info["filename"],
                "content_type": content_type,
                "original_length": len(file_info["content"]),
                "cleaned_length": len(cleaned)
            })
        
        return success
    
    def process_url(self, url: str) -> bool:
        """处理 URL 内容（目前支持微信文章）
        
        Args:
            url: 内容 URL
            
        Returns:
            处理是否成功
        """
        print(f"\n🔗 处理 URL: {url}")
        
        # 判断 URL 类型
        if self.wechat_fetcher.is_wechat_url(url):
            return self._process_wechat_article(url)
        else:
            print(f"⚠️  暂不支持的 URL 类型: {url}")
            return False
    
    def _process_wechat_article(self, url: str) -> bool:
        """处理微信文章"""
        # 抓取文章
        article_info = self.wechat_fetcher.fetch(url)
        if not article_info:
            return False
        
        # 清理内容
        cleaned = self.wechat_cleaner.clean(article_info["content"])
        
        # 计算 Hash
        content_hash = calculate_hash(cleaned)
        identifier = article_info["identifier"]
        
        # 去重检查
        if self.dedup.is_duplicate(identifier, content_hash):
            print(f"⏭️  文章已处理，跳过: {article_info['title']}")
            return True
        
        # 上传到 FastGPT
        title = article_info["title"]
        success = self.fastgpt.upload_text(cleaned, title)
        
        if success:
            # 记录状态
            self.dedup.update_record(identifier, content_hash, {
                "type": "wechat_article",
                "title": title,
                "url": url,
                "original_length": len(article_info["content"]),
                "cleaned_length": len(cleaned)
            })
        
        return success
    
    def scan_directory(self, directory: str = None) -> dict:
        """扫描目录并处理所有文件
        
        Args:
            directory: 目录路径，默认为配置的 SCAN_DIR
            
        Returns:
            处理统计信息
        """
        print(f"\n🔍 扫描目录: {directory or self.file_fetcher.scan_dir}")
        
        # 扫描文件
        files = self.file_fetcher.scan_directory(directory)
        
        if not files:
            print("⚠️  未找到可处理的文件")
            return {"total": 0, "success": 0, "skipped": 0, "failed": 0}
        
        print(f"📦 找到 {len(files)} 个文件")
        
        # 处理每个文件
        stats = {"total": len(files), "success": 0, "skipped": 0, "failed": 0}
        
        for file_info in files:
            identifier = file_info["identifier"]
            content_hash = calculate_hash(file_info["content"])
            
            # 去重检查
            if self.dedup.is_duplicate(identifier, content_hash):
                print(f"⏭️  跳过: {file_info['filename']}")
                stats["skipped"] += 1
                continue
            
            # 处理文件
            success = self.process_file(identifier)
            
            if success:
                stats["success"] += 1
            else:
                stats["failed"] += 1
        
        return stats
    
    def clear_state(self):
        """清除所有处理状态"""
        print("\n🗑️  清除所有处理状态...")
        self.dedup.clear_all()
        print("✅ 状态已清除")
    
    def show_stats(self):
        """显示处理统计信息"""
        print("\n📊 处理统计:")
        records = self.dedup.get_all_records()
        
        if not records:
            print("  暂无处理记录")
            return
        
        # 按类型统计
        type_stats = {}
        for identifier, record in records.items():
            content_type = record.get("metadata", {}).get("type", "unknown")
            type_stats[content_type] = type_stats.get(content_type, 0) + 1
        
        print(f"  总记录数: {len(records)}")
        for content_type, count in type_stats.items():
            print(f"  - {content_type}: {count}")
