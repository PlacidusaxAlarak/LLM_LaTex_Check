import json
import hashlib
from pathlib import Path
from typing import Optional, Any

CACHE_DIR = Path(".cache")

def ensure_cache_dir_exists():
    """确保缓存目录存在。"""
    CACHE_DIR.mkdir(exist_ok=True)

def get_cache_key(data: str) -> str:
    """根据输入数据的UTF-8编码计算SHA256哈希值作为缓存键。"""
    return hashlib.sha256(data.encode('utf-8')).hexdigest()

def get_from_cache(key: str) -> Optional[Any]:
    """根据键从缓存中获取数据。如果缓存不存在或读取失败，则返回None。"""
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                print(f"   └── 命中缓存: {key[:10]}...")
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"   └── 缓存读取错误: {e}，将忽略缓存。")
            return None
    return None

def set_to_cache(key: str, data: Any):
    """将数据存入缓存。"""
    cache_file = CACHE_DIR / f"{key}.json"
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"   └── 已写入缓存: {key[:10]}...")
    except IOError as e:
        print(f"   └── 缓存写入错误: {e}")