"""Hash 计算工具"""
import hashlib
from pathlib import Path


def calculate_hash(content: str) -> str:
    """计算字符串内容的 MD5 Hash"""
    if not content:
        return ""
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def calculate_file_hash(file_path: str) -> str:
    """计算文件的 MD5 Hash"""
    path = Path(file_path)
    if not path.exists():
        return ""
    
    hash_md5 = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()
