"""工具函数模块"""
from .hash import calculate_hash, calculate_file_hash
from .dedup import DedupManager, compute_dedup_key

__all__ = ['calculate_hash', 'calculate_file_hash', 'DedupManager', 'compute_dedup_key']
