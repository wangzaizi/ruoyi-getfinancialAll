"""
工具函数
"""
import os
import json
from typing import List, Dict
from config import DATA_DIR


def load_progress() -> Dict:
    """
    加载爬取进度
    """
    progress_file = os.path.join(DATA_DIR, 'progress.json')
    if os.path.exists(progress_file):
        with open(progress_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def get_statistics() -> Dict:
    """
    获取统计信息
    """
    summary_file = os.path.join(DATA_DIR, 'summary.json')
    if os.path.exists(summary_file):
        with open(summary_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    progress = load_progress()
    results = progress.get('results', [])
    
    if results:
        success_count = sum(1 for r in results if r.get('success'))
        total_files = sum(r.get('files_downloaded', 0) for r in results)
        
        return {
            'total_cities': len(results),
            'success_count': success_count,
            'failed_count': len(results) - success_count,
            'total_files': total_files,
            'progress': len(results)
        }
    
    return {
        'total_cities': 0,
        'success_count': 0,
        'failed_count': 0,
        'total_files': 0,
        'progress': 0
    }


def print_statistics():
    """
    打印统计信息
    """
    stats = get_statistics()
    
    print("\n" + "="*50)
    print("爬取统计信息")
    print("="*50)
    print(f"总城市数: {stats.get('total_cities', 0)}")
    print(f"成功爬取: {stats.get('success_count', 0)}")
    print(f"失败数量: {stats.get('failed_count', 0)}")
    print(f"总下载文件: {stats.get('total_files', 0)}")
    print(f"完成进度: {stats.get('progress', 0)} / 334")
    print("="*50 + "\n")


if __name__ == "__main__":
    print_statistics()

