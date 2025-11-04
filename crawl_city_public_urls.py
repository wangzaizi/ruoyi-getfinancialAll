"""
按城市使用公开栏目检索，基于 gov/fin 根域查找符合条件的公开链接：
- 对每个城市：用 FinanceReportSpider.search_finance_reports(root, city, violent_fallback=False)
- 汇总 urls（仅取链接字符串），urls 非空视为成功
- 输出到 data/city_urls_crawled/[城市名].json 与索引 data/city_urls_crawled/index.json
"""

import os
import json
import multiprocessing
from datetime import datetime
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import DATA_DIR
from spider import FinanceReportSpider
from generated_site_mappings_result import CITY_SITE_SOURCES_WITH_URLS


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def crawl_city(city: str, gov: str, fin: str) -> Dict:
    roots: List[str] = []
    if gov:
        roots.append(gov)
    if fin and fin not in roots:
        roots.append(fin)

    urls_collected: List[str] = []
    seen = set()
    # 为保证线程安全，每次调用创建独立的爬虫实例
    spider = FinanceReportSpider()
    for root in roots:
        try:
            reports = spider.search_finance_reports(root, city, violent_fallback=False)
            for r in reports:
                u = r.get('url') or ''
                if u and (u not in seen):
                    seen.add(u)
                    urls_collected.append(u)
        except Exception:
            continue

    return {
        "city": city,
        "gov": gov,
        "fin": fin,
        "urls": urls_collected,
        "success": len(urls_collected) > 0,
    }


def main():
    out_dir = os.path.join(DATA_DIR, "city_urls_crawled")
    ensure_dir(out_dir)

    total = len(CITY_SITE_SOURCES_WITH_URLS)
    success_count = 0
    results: List[Dict[str, object]] = []
    cpu_count = multiprocessing.cpu_count()
    max_workers = min(cpu_count * 4, 64)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for city, payload in CITY_SITE_SOURCES_WITH_URLS.items():
            gov = (payload.get("gov") or "").strip()
            fin = (payload.get("fin") or "").strip()
            fut = executor.submit(crawl_city, city, gov, fin)
            futures[fut] = city

        for fut in as_completed(futures):
            try:
                result = fut.result()
                results.append(result)
                if result.get("success"):
                    success_count += 1
            except Exception as e:
                # 异常城市也记录失败项
                results.append({
                    "city": futures[fut],
                    "gov": "",
                    "fin": "",
                    "urls": [],
                    "success": False,
                    "error": str(e),
                })

    # 写入总结果文件
    out_path = os.path.join(out_dir, "results.json")
    payload = {
        "generated_at": datetime.now().isoformat(),
        "total_cities": total,
        "success_count": success_count,
        "failed_count": total - success_count,
        "items": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"完成：成功 {success_count}/{total}，结果文件：{out_path}")


if __name__ == "__main__":
    main()


