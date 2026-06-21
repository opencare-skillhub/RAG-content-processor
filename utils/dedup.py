"""去重管理器 - 基于 Hash 的去重机制"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class DedupManager:
    """去重管理器，基于内容 Hash 进行去重"""
    
    def __init__(self, state_file: str = "state/sync_state.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()
    
    def _load_state(self) -> dict:
        """加载状态文件"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"files": {}, "updated_at": ""}
        return {"files": {}, "updated_at": ""}
    
    def _save_state(self):
        """保存状态文件"""
        self.state["updated_at"] = datetime.now().isoformat()
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
    
    def is_duplicate(self, identifier: str, content_hash: str) -> bool:
        """检查是否为重复内容
        
        Args:
            identifier: 内容标识符（如文件路径、URL等）
            content_hash: 内容的 Hash 值
            
        Returns:
            True 表示重复，False 表示新内容
        """
        files = self.state.get("files", {})
        if identifier in files:
            return files[identifier].get("hash") == content_hash
        return False
    
    def get_record(self, identifier: str) -> Optional[dict]:
        """获取指定标识符的记录"""
        return self.state.get("files", {}).get(identifier)
    
    def update_record(self, identifier: str, content_hash: str, 
                     metadata: Optional[dict] = None):
        """更新或添加记录
        
        Args:
            identifier: 内容标识符
            content_hash: 内容 Hash
            metadata: 额外元数据
        """
        if "files" not in self.state:
            self.state["files"] = {}
        
        record = {
            "hash": content_hash,
            "updated_at": datetime.now().isoformat()
        }
        
        if metadata:
            record["metadata"] = metadata
        
        self.state["files"][identifier] = record
        self._save_state()
    
    def delete_record(self, identifier: str):
        """删除记录"""
        if "files" in self.state and identifier in self.state["files"]:
            del self.state["files"][identifier]
            self._save_state()
    
    def clear_all(self):
        """清空所有记录"""
        self.state = {"files": {}, "updated_at": datetime.now().isoformat()}
        self._save_state()
    
    def get_all_records(self) -> dict:
        """获取所有记录"""
        return self.state.get("files", {})
