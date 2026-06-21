"""微信公众号文章下载器（基于远程 MCP 服务）"""
import json
import os
import time
import urllib.parse
from pathlib import Path
from typing import Optional, List, Callable

import requests


class WeChatMCPDownloader:
    """基于远程 MCP 服务的微信文章下载器
    
    参考 wechat-article-downloader 技能，使用远程 MCP 服务器下载文章。
    MCP 服务器负责 HTML→Markdown 转换，本地只负责接收和保存文件。
    """
    
    # 远程 MCP 服务地址（基于 qiye45/wechatDownload）
    MCP_URL = "https://changfengbox.top/api/mcp"
    TIMEOUT = 120  # 远程服务延迟较高
    
    def __init__(self, output_dir: str = "./wechat-downloads",
                 run_subdir: Optional[str] = None):
        """初始化下载器。

        Args:
            output_dir: 下载根目录。
            run_subdir: 本次下载的子目录名。默认 None 时自动按时间戳生成
                （YYYYMMDD_HHMMSS），使每次下载天然隔离，便于长期回溯。
        """
        base_dir = Path(output_dir)
        base_dir.mkdir(parents=True, exist_ok=True)

        # 默认按时间戳隔离每次下载，避免历史残留污染本次结果
        self.run_subdir = run_subdir or time.strftime("%Y%m%d_%H%M%S")
        self.output_dir = base_dir / self.run_subdir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def download_article(self, url: str, formats: tuple = ("md",)) -> Optional[dict]:
        """下载单篇微信文章
        
        Args:
            url: 微信文章 URL
            formats: 输出格式，可选 "html", "md", "pdf", "word", "txt"
            
        Returns:
            下载结果字典，包含文件路径、标题等信息；失败返回 None
        """
        config = self._build_config(formats)
        
        try:
            result = self._call_mcp("wechat", {"url": url, "config": config})
            
            if not result or "result" not in result:
                print(f"❌ MCP 返回异常: {result}")
                return None
            
            # 解析返回结果
            content_list = result.get("result", {}).get("content", [])
            if not content_list:
                print(f"❌ 未获取到文章内容")
                return None
            
            # 提取文本内容（通常是 JSON 字符串）
            text_content = content_list[0].get("text", "")
            try:
                data = json.loads(text_content)
            except json.JSONDecodeError as e:
                print(f"❌ JSON 解析失败: {e}")
                print(f"   原始内容: {text_content[:200]}")
                return None
            
            if data.get("status") not in ["success", "completed"]:
                error_msg = data.get('message') or data.get('error') or '未知错误'
                print(f"❌ 下载失败: {error_msg}")
                print(f"   状态: {data.get('status')}")
                print(f"   完整响应: {json.dumps(data, ensure_ascii=False)[:300]}")
                return None
            
            # 下载文件
            urls = data.get("urls", [])
            if not urls:
                print(f"❌ 未获取到下载链接")
                return None
            
            downloaded_files = []
            for file_url in urls:
                file_path = self._download_file(file_url)
                if file_path:
                    downloaded_files.append(file_path)
            
            if not downloaded_files:
                print(f"❌ 文件下载失败")
                return None
            
            return {
                "status": "success",
                "title": data.get("title", "未知标题"),
                "files": downloaded_files,
                "url": url
            }
        
        except Exception as e:
            print(f"❌ 下载文章时出错: {e}")
            return None
    
    def download_collection(self, url: str, formats: tuple = ("md",)) -> Optional[dict]:
        """下载微信合集（专辑）
        
        Args:
            url: 合集 URL（appmsgalbum 格式）
            formats: 输出格式
            
        Returns:
            下载结果字典
        """
        config = self._build_config(formats)
        
        try:
            result = self._call_mcp("wechat_collection", {"url": url, "config": config})
            
            if not result or "result" not in result:
                print(f"❌ MCP 返回异常")
                return None
            
            content_list = result.get("result", {}).get("content", [])
            if not content_list:
                print(f"❌ 未获取到合集内容")
                return None
            
            text_content = content_list[0].get("text", "")
            data = json.loads(text_content)
            
            if data.get("status") != "success":
                print(f"❌ 合集下载失败: {data.get('message', '未知错误')}")
                return None
            
            # 遍历合集中的所有文章并下载
            articles = data.get("articles", [])
            downloaded = []
            
            print(f"📚 合集包含 {len(articles)} 篇文章")
            
            for i, article in enumerate(articles, 1):
                article_url = article.get("url")
                if not article_url:
                    continue
                
                print(f"  [{i}/{len(articles)}] 下载: {article.get('title', '未知标题')}")
                result = self.download_article(article_url, formats)
                
                if result and result.get("status") == "success":
                    downloaded.append(result)
                
                # 避免请求过快
                time.sleep(2)
            
            return {
                "status": "success",
                "total": len(articles),
                "downloaded": len(downloaded),
                "articles": downloaded
            }
        
        except Exception as e:
            print(f"❌ 下载合集时出错: {e}")
            return None
    
    def batch_download(self, urls: list, formats: tuple = ("md",), 
                      progress_callback: Optional[Callable] = None) -> dict:
        """批量下载多篇文章
        
        Args:
            urls: URL 列表
            formats: 输出格式
            progress_callback: 进度回调函数 callback(current, total, result)
            
        Returns:
            批量下载结果统计
        """
        self.stats = {
            'total': len(urls),
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        results = []
        
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] 下载: {url}")
            
            result = self.download_article(url, formats)
            
            if result and result.get("status") == "success":
                self.stats['success'] += 1
                print(f"  ✅ 成功: {result.get('title')}")
            else:
                self.stats['failed'] += 1
                print(f"  ❌ 失败")
            
            results.append(result)
            
            if progress_callback:
                progress_callback(i, len(urls), result)
            
            # 避免请求过快
            if i < len(urls):
                time.sleep(2)
        
        # 聚合本次下载的文件清单和 url→file 映射，供下游清洗/评分阶段使用
        all_files = []
        url_file_map = {}
        for url, result in zip(urls, results):
            if result and result.get("status") == "success":
                files = result.get("files", [])
                all_files.extend(str(f) for f in files)
                url_file_map[url] = [str(f) for f in files]

        return {
            "total": self.stats['total'],
            "success": self.stats['success'],
            "failed": self.stats['failed'],
            "skipped": self.stats['skipped'],
            "run_dir": str(self.output_dir),
            "run_subdir": self.run_subdir,
            "files": all_files,
            "url_file_map": url_file_map,
        }
    
    def _build_config(self, formats: tuple) -> dict:
        """构建 MCP config 参数"""
        format_map = {
            "html": "HTML",
            "md": "MD",
            "pdf": "PDF",
            "word": "WORD",
            "docx": "WORD",
            "txt": "TXT",
            "mhtml": "MHTML"
        }
        
        config = {
            "保存离线网页": False,
            "HTML": False,
            "MD": False,
            "PDF": False,
            "WORD": False,
            "TXT": False,
            "MHTML": False,
            "文件开头添加日期": True
        }
        
        for fmt in formats:
            key = format_map.get(fmt.lower())
            if key:
                config[key] = True
        
        return config
    
    def _call_mcp(self, tool_name: str, arguments: dict) -> Optional[dict]:
        """调用 MCP 服务"""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": 1,
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(
                self.MCP_URL,
                json=payload,
                headers=headers,
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.Timeout:
            print(f"❌ MCP 请求超时（{self.TIMEOUT}s）")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ MCP 请求失败: {e}")
            return None
    
    def _download_file(self, url: str) -> Optional[Path]:
        """下载文件并保存到本地"""
        try:
            # 从 URL 提取文件名
            decoded_url = urllib.parse.unquote(url)
            basename = os.path.basename(decoded_url)
            
            if not basename:
                basename = f"article_{int(time.time())}.md"
            
            file_path = self.output_dir / basename
            
            # 下载文件
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            # 尝试多种编码
            content = None
            for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
                try:
                    content = response.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if content is None:
                content = response.content.decode('utf-8', errors='ignore')
            
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return file_path
        
        except Exception as e:
            print(f"❌ 文件下载失败: {e}")
            return None
