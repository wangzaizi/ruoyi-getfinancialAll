"""
生成每个城市包含 urls 的数据文件。

来源：generated_site_mappings_result.CITY_SITE_SOURCES_WITH_URLS
输出：data/city_urls/[城市名].json（UTF-8，含 gov/fin/urls/filters/violent_fallback_enabled）
并生成索引：data/city_urls/index.json（统计与城市列表）
"""

import os
import json
from datetime import datetime
from typing import Dict

from config import DATA_DIR
from generated_site_mappings_result import CITY_SITE_SOURCES_WITH_URLS


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def serialize(obj):
    try:
        json.dumps(obj)
        return obj
    except Exception:
        # 兜底：无法序列化的对象以字符串输出
        return str(obj)


def main():
    out_dir = os.path.join(DATA_DIR, "city_urls")
    ensure_dir(out_dir)

    total = len(CITY_SITE_SOURCES_WITH_URLS)
    written = 0
    index: Dict[str, str] = {
        "generated_at": datetime.now().isoformat(),
        "total_cities": total,
        "files": []
    }

    for city, payload in CITY_SITE_SOURCES_WITH_URLS.items():
        try:
            file_name = f"{city}.json"
            # 处理Windows文件名非法字符
            safe_name = file_name.replace("\\", "_").replace("/", "_").replace(":", "_") \
                .replace("*", "_").replace("?", "_").replace("\"", "'") \
                .replace("<", "_").replace(">", "_").replace("|", "_")
            out_path = os.path.join(out_dir, safe_name)

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(serialize(payload), f, ensure_ascii=False, indent=2)

            index["files"].append({
                "city": city,
                "file": os.path.basename(out_path),
                "urls_count": len(payload.get("urls", []))
            })
            written += 1
        except Exception as e:
            # 出错也尽量继续其他城市
            index.setdefault("errors", []).append({"city": city, "error": str(e)})

    # 写入索引
    index_path = os.path.join(out_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"已生成 {written}/{total} 个城市的 urls 文件 -> {out_dir}")
    print(f"索引: {index_path}")


if __name__ == "__main__":
    main()


