"""FastGPT 同步模块（增强版）

增强功能：
- 知识库查询（list_datasets）
- 文章/集合查询（list_collections）
- 知识库搜索（search）
- 文件/文件夹上传（upload_file, upload_folder）- 支持去重
- 文本推送（upload_text）
"""
import json
import os
import re
import requests
from pathlib import Path
from typing import Optional, List, Dict

from utils.dedup import DedupManager
from utils.hash import calculate_file_hash


class FastGPTSyncer:
    """FastGPT 知识库同步器（增强版）"""
    
    def __init__(self, base_url: str, api_key: str, dataset_id: str = None,
                 state_file: str = None):
        # 强制使用 /api 根路径（参考 fastgpt_sync.py 的实现）
        self.base_url = self._get_api_base(base_url)
        self.api_key = api_key
        self.dataset_id = dataset_id
        
        self.session = requests.Session()
        # 三重认证 header（私有化环境兼容）
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'apikey': api_key,
            'Content-Type': 'application/json'
        })
        
        # 初始化去重管理器（参考 clinicaltrials推送和订阅 的 fastgpt_sync.py）
        state_file = state_file or os.getenv(
            "FASTGPT_SYNC_STATE_DB", 
            "./data/fastgpt_sync_state.json"
        )
        self.dedup = DedupManager(state_file)
    
    def _get_api_base(self, url: str) -> str:
        """强制构建 /api 根路径"""
        url = url.rstrip('/')
        # 如果已经有 /api，直接使用
        if url.endswith('/api'):
            return url
        # 否则添加 /api
        return f"{url}/api"
    
    def upload_text(self, content: str, title: str = "上传内容", 
                   collection_name: Optional[str] = None) -> bool:
        """上传文本内容到 FastGPT
        
        Args:
            content: 文本内容
            title: 内容标题
            collection_name: 集合名称（可选）
            
        Returns:
            上传是否成功
        """
        try:
            # 创建或获取集合
            collection_id = self._get_or_create_collection(
                collection_name or title
            )
            
            if not collection_id:
                print("❌ 无法创建集合")
                return False
            
            # 上传数据
            url = f"{self.base_url}/core/dataset/data/pushData"
            payload = {
                "collectionId": collection_id,
                "data": [
                    {
                        "q": content,
                        "a": ""
                    }
                ]
            }
            
            response = self.session.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                print(f"✅ 上传成功: {title}")
                return True
            else:
                print(f"❌ 上传失败: {response.status_code} - {response.text}")
                return False
        
        except Exception as e:
            print(f"❌ 上传时出错: {e}")
            return False
    
    def upload_file(self, file_path: str, 
                   collection_name: Optional[str] = None,
                   metadata: Optional[dict] = None) -> str:
        """上传文件到 FastGPT（支持去重）
        
        Args:
            file_path: 文件路径
            collection_name: 集合名称（可选）
            metadata: 可选的 QA 元数据
            
        Returns:
            "success" - 上传成功
            "skipped" - 文件已上传且内容未变化（跳过）
            "failed"  - 上传失败
        """
        try:
            path = Path(file_path)
            if not path.exists():
                print(f"❌ 文件不存在: {file_path}")
                return "failed"
            
            # ===== 去重检查（参考 clinicaltrails推送和订阅 的 sync_once 逻辑）=====
            file_hash = calculate_file_hash(str(path))
            file_identity = str(path.resolve())  # 使用绝对路径作为唯一标识
            
            if self.dedup.is_duplicate(file_identity, file_hash):
                print(f"⏭️  跳过（内容未变化）: {path.name}")
                return "skipped"
            
            # 创建或获取集合
            collection_id = self._get_or_create_collection(
                collection_name or path.stem
            )
            
            if not collection_id:
                print("❌ 无法创建集合")
                return "failed"
            
            # 使用官方 create/localFile 接口
            url = f"{self.base_url}/core/dataset/collection/create/localFile"
            metadata = metadata or {}
            
            with open(file_path, 'rb') as f:
                files = {'file': (path.name, f)}
                
                # 严格按照官方参数格式
                data_payload = {
                    "datasetId": self.dataset_id,
                    "parentId": collection_id,
                    "trainingType": "chunk",
                    "chunkSize": 512,
                    "chunkSplitter": "",
                    "qaPrompt": "",
                    "metadata": metadata
                }
                
                form_data = {
                    "data": json.dumps(data_payload)
                }
                
                # 临时移除 Content-Type 让 requests 自动设置
                headers = self.session.headers.copy()
                headers.pop('Content-Type', None)
                
                response = requests.post(
                    url, 
                    headers=headers,
                    files=files, 
                    data=form_data,
                    timeout=60
                )
            
            if response.status_code == 200:
                res_json = response.json()
                if res_json.get("code") == 200:
                    print(f"✅ 文件上传成功: {path.name}")
                    # ===== 记录上传状态（用于下次去重）=====
                    self.dedup.update_record(
                        file_identity, 
                        file_hash,
                        metadata={
                            "filename": path.name,
                            "collection_name": collection_name or path.stem,
                            "collection_id": collection_id,
                            "qa_metadata": metadata,
                        }
                    )
                    return "success"
                else:
                    print(f"❌ 文件上传失败: {res_json.get('message')}")
                    return "failed"
            else:
                print(f"❌ 文件上传失败: {response.status_code} - {response.text[:200]}")
                return "failed"
        
        except Exception as e:
            print(f"❌ 文件上传时出错: {e}")
            return "failed"
    
    def _get_or_create_collection(self, name: str) -> Optional[str]:
        """获取或创建集合
        
        Args:
            name: 集合名称
            
        Returns:
            集合 ID，失败返回 None
        """
        try:
            # 先尝试查找已有集合
            url = f"{self.base_url}/core/dataset/collection/list"
            params = {
                'datasetId': self.dataset_id,
                'name': name
            }
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                collections = data.get('data', [])
                
                # 查找匹配的集合
                for coll in collections:
                    if coll.get('name') == name:
                        return coll.get('_id')
            
            # 不存在则创建新集合
            url = f"{self.base_url}/core/dataset/collection/create"
            payload = {
                "datasetId": self.dataset_id,
                "name": name,
                "type": "file"
            }
            
            response = self.session.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                result = data.get('data', {})
                # data 可能是字典或字符串
                if isinstance(result, dict):
                    return result.get('_id')
                else:
                    # 直接返回字符串 ID
                    return result
            else:
                print(f"❌ 创建集合失败: {response.status_code} - {response.text}")
                return None
        
        except Exception as e:
            print(f"❌ 获取/创建集合时出错: {e}")
            return None
    
    def test_connection(self) -> bool:
        """测试与 FastGPT 的连接"""
        try:
            url = f"{self.base_url}/core/dataset/detail"
            params = {'id': self.dataset_id}
            
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                print("✅ FastGPT 连接成功")
                return True
            else:
                print(f"❌ FastGPT 连接失败: {response.status_code}")
                return False
        
        except Exception as e:
            print(f"❌ 连接测试失败: {e}")
            return False
    
    # ========== 新增查询功能 ==========
    
    def list_datasets(self) -> List[Dict]:
        """列出所有知识库
        
        Returns:
            知识库列表，每个包含 _id, name 等字段
        """
        try:
            url = f"{self.base_url}/core/dataset/list"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                datasets = data.get('data', [])
                return datasets
            else:
                print(f"❌ 查询知识库失败: {response.status_code}")
                return []
        
        except Exception as e:
            print(f"❌ 查询知识库时出错: {e}")
            return []
    
    def list_collections(self, dataset_id: str = None, 
                        search_text: str = "",
                        page_size: int = 50,
                        offset: int = 0) -> List[Dict]:
        """列出知识库中的文章/集合
        
        Args:
            dataset_id: 知识库 ID（默认使用 self.dataset_id）
            search_text: 搜索文本（可选）
            page_size: 每页数量
            offset: 偏移量
            
        Returns:
            文章/集合列表
        """
        dataset_id = dataset_id or self.dataset_id
        if not dataset_id:
            print("❌ 未指定知识库 ID")
            return []
        
        try:
            url = f"{self.base_url}/core/dataset/collection/listV2"
            payload = {
                "datasetId": dataset_id,
                "parentId": None,
                "searchText": search_text,
                "pageSize": page_size,
                "offset": offset
            }
            
            response = self.session.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # 处理三种可能的返回格式
                result = data.get('data', data)
                if isinstance(result, list):
                    return result
                elif isinstance(result, dict):
                    return result.get('list', result.get('data', []))
                else:
                    return []
            else:
                print(f"❌ 查询文章失败: {response.status_code}")
                return []
        
        except Exception as e:
            print(f"❌ 查询文章时出错: {e}")
            return []
    
    def search(self, query: str, dataset_id: str = None, 
              limit: int = 5, similarity: float = 0.2) -> List[Dict]:
        """在知识库中搜索
        
        Args:
            query: 搜索查询
            dataset_id: 知识库 ID（默认使用 self.dataset_id）
            limit: 返回结果数量
            similarity: 相似度阈值
            
        Returns:
            搜索结果列表
        """
        dataset_id = dataset_id or self.dataset_id
        if not dataset_id:
            print("❌ 未指定知识库 ID")
            return []
        
        try:
            url = f"{self.base_url}/core/dataset/searchTest"
            payload = {
                "datasetId": dataset_id,
                "text": query,
                "limit": limit,
                "similarity": similarity
            }
            
            response = self.session.post(url, json=payload, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('data', [])
                return results
            else:
                print(f"❌ 搜索失败: {response.status_code}")
                return []
        
        except Exception as e:
            print(f"❌ 搜索时出错: {e}")
            return []
    
    def upload_folder(self, folder_path: str, collection_name: str = None,
                     file_extensions: tuple = ('.md', '.txt'),
                     progress_callback=None) -> Dict:
        """上传整个文件夹（支持去重）
        
        Args:
            folder_path: 文件夹路径
            collection_name: 集合名称（默认使用文件夹名）
            file_extensions: 支持的文件扩展名
            progress_callback: 进度回调 callback(current, total, filename, result)
            
        Returns:
            上传结果统计（含 skipped 计数）
        """
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            print(f"❌ 文件夹不存在: {folder_path}")
            return {"total": 0, "success": 0, "skipped": 0, "failed": 0}
        
        # 收集所有文件
        files = []
        for ext in file_extensions:
            files.extend(folder.rglob(f'*{ext}'))
        
        if not files:
            print(f"⚠️  文件夹中没有找到支持的文件")
            return {"total": 0, "success": 0, "skipped": 0, "failed": 0}
        
        # 创建或获取集合
        collection_name = collection_name or folder.name
        collection_id = self._get_or_create_collection(collection_name)
        
        if not collection_id:
            print("❌ 无法创建集合")
            return {"total": len(files), "success": 0, "skipped": 0, "failed": len(files)}
        
        # 批量上传（带去重）
        total = len(files)
        success = 0
        skipped = 0
        failed = 0
        
        print(f"📁 开始上传文件夹: {folder.name} ({total} 个文件)")
        
        for i, file_path in enumerate(files, 1):
            print(f"  [{i}/{total}] 上传: {file_path.name}")
            
            result = self.upload_file(str(file_path), collection_name)
            
            if result == "success":
                success += 1
                print(f"    ✅ 成功")
            elif result == "skipped":
                skipped += 1
                print(f"    ⏭️  跳过（内容未变化）")
            else:
                failed += 1
                print(f"    ❌ 失败")
            
            if progress_callback:
                progress_callback(i, total, file_path.name, result)
        
        print(f"\n📊 上传完成: 成功 {success}/{total}, 跳过 {skipped}, 失败 {failed}")
        
        return {
            "total": total,
            "success": success,
            "skipped": skipped,
            "failed": failed,
            "collection_id": collection_id
        }
