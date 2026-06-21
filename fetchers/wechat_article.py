"""微信公众号文章抓取器"""
import re
import requests
from typing import Optional


class WechatArticleFetcher:
    """微信公众号文章抓取器"""
    
    # 微信文章 URL 模式
    WECHAT_URL_PATTERN = r'https?://mp\.weixin\.qq\.com/s/[a-zA-Z0-9_-]+'
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
    
    def is_wechat_url(self, url: str) -> bool:
        """检查是否为微信文章 URL"""
        return bool(re.match(self.WECHAT_URL_PATTERN, url))
    
    def fetch(self, url: str) -> Optional[dict]:
        """抓取微信文章
        
        Args:
            url: 微信文章 URL
            
        Returns:
            包含文章内容和元数据的字典，失败返回 None
        """
        if not self.is_wechat_url(url):
            print(f"⚠️  不是有效的微信文章 URL: {url}")
            return None
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # 提取标题
            title = self._extract_title(response.text)
            
            return {
                "content": response.text,
                "identifier": url,
                "title": title or "微信文章",
                "type": "wechat_article",
                "url": url
            }
        
        except requests.RequestException as e:
            print(f"❌ 抓取微信文章失败: {e}")
            return None
        except Exception as e:
            print(f"❌ 处理微信文章时出错: {e}")
            return None
    
    def _extract_title(self, html: str) -> Optional[str]:
        """从 HTML 中提取文章标题"""
        # 尝试从 meta 标签提取
        title_match = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', html)
        if title_match:
            return title_match.group(1)
        
        # 尝试从 title 标签提取
        title_match = re.search(r'<title>([^<]+)</title>', html)
        if title_match:
            return title_match.group(1)
        
        # 尝试从 h1 标签提取
        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if title_match:
            return title_match.group(1)
        
        return None
