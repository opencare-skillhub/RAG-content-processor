"""FastGPT 同步模块（增强版）

增强功能：
- 知识库查询（list_datasets）
- 文章/集合查询（list_collections）
- 知识库搜索（search）
- 文件/文件夹上传（upload_file, upload_folder）- 支持去重
- 文本推送（upload_text）
"""
import json
import logging
import os
import re
import requests
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import quote

from utils.dedup import DedupManager, compute_dedup_key
from utils.hash import calculate_file_hash, calculate_hash

logger = logging.getLogger(__name__)


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
                   metadata: Optional[dict] = None,
                   parent_id: Optional[str] = None) -> str:
        """上传文件到 FastGPT（支持去重）

        采用官方 create/localFile 接口：该接口会**自动创建集合并触发训练/embedding**，
        因此 parentId 默认传 None（与官方 curl 一致），不再预建一个空集合当父级
        （预建 file 类型集合当 parentId 会导致训练不触发）。集合名由上传的文件名决定。

        Args:
            file_path: 文件路径
            collection_name: 集合名称（可选；默认用文件名，仅用于覆盖集合显示名）
            metadata: 可选的 QA 元数据
            parent_id: 可选的父级**文件夹**集合 ID（用于目录归类，默认 None=根）

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

            metadata = metadata or {}

            # ===== 去重检查（key: original_url → 内容 hash → 文件 hash）=====
            # 读取内容用于内容 hash 与去重 key 计算
            try:
                content_text = path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                content_text = None

            dedup_key = compute_dedup_key(metadata, content_text, path)
            # value_hash 表示"内容是否变化"，统一用内容 hash（无法读文本时回退文件字节 hash）
            value_hash = calculate_hash(content_text) if content_text else calculate_file_hash(str(path))

            existing = self.dedup.get_record(dedup_key)
            is_update = False
            if existing:
                if existing.get("hash") == value_hash:
                    print(f"⏭️  跳过（内容未变化）: {path.name}")
                    return "skipped"
                # 同一文档身份但内容变化 → 更新：不覆盖旧 collection，改名另存
                is_update = True

            # ===== 决定上传文件名（localFile 接口以文件名作为集合名）=====
            base_name = collection_name or path.stem
            if is_update:
                base_name = f"{base_name}-{value_hash[:8]}"
                logger.warning(
                    "检测到内容更新，已另存为新集合: %s（原: %s, key=%s）",
                    base_name, collection_name or path.stem, dedup_key,
                )
            upload_filename = f"{base_name}{path.suffix}"

            # 中文文件名需 encode：multipart 的 Content-Disposition 在部分服务端会按
            # latin-1 解析导致乱码；这里做 RFC3986 百分号编码，FastGPT 端会 decode 还原。
            safe_filename = quote(upload_filename)

            # 使用官方 create/localFile 接口（自动建集合 + 触发训练/embedding）
            url = f"{self.base_url}/core/dataset/collection/create/localFile"

            with open(file_path, 'rb') as f:
                files = {'file': (safe_filename, f)}

                # 严格按照官方参数格式（parentId 默认 None，与官方 curl 一致）
                data_payload = {
                    "datasetId": self.dataset_id,
                    "parentId": parent_id,
                    "trainingType": "chunk",
                    "chunkSize": 512,
                    "chunkSplitter": "",
                    "qaPrompt": "",
                    "metadata": metadata
                }

                form_data = {
                    "data": json.dumps(data_payload)
                }

                # 临时移除 Content-Type 让 requests 自动设置 multipart 边界
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
                        dedup_key,
                        value_hash,
                        metadata={
                            "filename": path.name,
                            "collection_name": upload_filename,
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
    
    def create_dataset(
        self,
        name: str,
        intro: str = "介绍",
        avatar: str = "",
        parent_id: Optional[str] = None,
        vector_model: str = "text-embedding-v4",
        agent_model: str = "step-1v-8k",
        vlm_model: Optional[str] = None,
    ) -> Optional[dict]:
        """创建 FastGPT 知识库。"""
        try:
            vlm_model = vlm_model or os.getenv("FASTGPT_VLM_MODEL", "step-1o-turbo-vision")
            url = f"{self.base_url}/core/dataset/create"
            payload = {
                "parentId": parent_id,
                "type": "dataset",
                "name": name,
                "intro": intro,
                "avatar": avatar,
                "vectorModel": vector_model,
                "agentModel": agent_model,
                "vlmModel": vlm_model,
            }
            response = self.session.post(url, json=payload, timeout=30)
            if response.status_code != 200:
                print(f"❌ 创建知识库失败: {response.status_code} - {response.text}")
                return None
            data = response.json()
            if data.get("code") != 200:
                print(f"❌ 创建知识库失败: {data.get('message', '')}")
                return None
            print(f"✅ 创建知识库成功: {name}")
            result = data.get("data", {})
            if isinstance(result, str):
                return {"_id": result}
            return result
        except Exception as e:
            print(f"❌ 创建知识库时出错: {e}")
            return None

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
