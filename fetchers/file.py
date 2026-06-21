"""本地文件抓取器"""
from pathlib import Path
from typing import List


class FileFetcher:
    """本地文件抓取器"""
    
    SUPPORTED_EXTENSIONS = {'.md', '.txt', '.html', '.htm'}
    
    def __init__(self, scan_dir: str = "./input"):
        self.scan_dir = Path(scan_dir)
    
    def fetch_file(self, file_path: str) -> dict:
        """抓取单个文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            包含文件内容和元数据的字典
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        content = path.read_text(encoding='utf-8')
        
        return {
            "content": content,
            "identifier": str(path.absolute()),
            "filename": path.name,
            "extension": path.suffix.lower(),
            "type": self._get_content_type(path.suffix)
        }
    
    def scan_directory(self, directory: str = None) -> List[dict]:
        """扫描目录下的所有支持文件
        
        Args:
            directory: 目录路径，默认为 scan_dir
            
        Returns:
            文件信息列表
        """
        scan_path = Path(directory) if directory else self.scan_dir
        
        if not scan_path.exists():
            print(f"⚠️  目录不存在: {scan_path}")
            return []
        
        files = []
        for ext in self.SUPPORTED_EXTENSIONS:
            for file_path in scan_path.rglob(f"*{ext}"):
                try:
                    file_info = self.fetch_file(str(file_path))
                    files.append(file_info)
                except Exception as e:
                    print(f"⚠️  读取文件失败 {file_path}: {e}")
        
        return files
    
    def _get_content_type(self, extension: str) -> str:
        """根据扩展名判断内容类型"""
        ext = extension.lower()
        if ext == '.md':
            return 'markdown'
        elif ext in {'.html', '.htm'}:
            return 'html'
        else:
            return 'text'
