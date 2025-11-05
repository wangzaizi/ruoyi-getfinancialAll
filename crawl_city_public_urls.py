"""
按城市使用公开栏目检索，基于 gov/fin 根域查找符合条件的公开链接：
- 数据源：从 generated_site_mappings_result.py 的 CITY_SITE_SOURCES_WITH_URLS 获取所有城市的 gov/fin 网站地址
- 读取现有的 results.json，只对 success: false 的城市重新爬取
- 使用公开栏目检索方法（violent_fallback=False，不使用暴力遍历）
- 更新原文件，保留 success: true 的城市不变
"""

import os
import json
import multiprocessing
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import DATA_DIR
from spider import FinanceReportSpider
# 数据源：从 generated_site_mappings_result.py 获取所有城市的 gov/fin 网站地址
from generated_site_mappings_result import CITY_SITE_SOURCES_WITH_URLS


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def crawl_city(city: str, gov: str, fin: str, use_violent_fallback: bool = True) -> Dict:
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
            reports = spider.search_finance_reports(root, city, violent_fallback=use_violent_fallback)
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
        "downloaded_files": "",
        "success": len(urls_collected) > 0,
    }


def load_existing_results(results_path: str) -> Optional[Dict]:
    """加载现有的 results.json 文件"""
    if not os.path.exists(results_path):
        return None
    try:
        with open(results_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"加载现有结果文件失败: {e}")
        return None


def main():
    out_dir = os.path.join(DATA_DIR, "city_urls_crawled")
    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, "results.json")

    # 加载现有结果
    existing_data = load_existing_results(out_path)
    existing_items_by_city = {}
    if existing_data and "items" in existing_data:
        for item in existing_data["items"]:
            city = item.get("city")
            if city:
                existing_items_by_city[city] = item

    # 确定需要重新爬取的城市（只处理 success: false 的）
    # 数据源：CITY_SITE_SOURCES_WITH_URLS 包含所有城市的 gov/fin 网站地址
    cities_to_retry = []
    if existing_items_by_city:
        for city, payload in CITY_SITE_SOURCES_WITH_URLS.items():
            existing_item = existing_items_by_city.get(city)
            if existing_item and existing_item.get("success") is True:
                # 成功的城市跳过，保留原结果
                continue
            # 失败的城市或新城市需要处理，从 CITY_SITE_SOURCES_WITH_URLS 获取 gov/fin
            cities_to_retry.append(city)
    else:
        # 如果没有现有结果，处理所有城市（从 CITY_SITE_SOURCES_WITH_URLS 获取）
        cities_to_retry = list(CITY_SITE_SOURCES_WITH_URLS.keys())

    if not cities_to_retry:
        print("所有城市都已成功，无需重新爬取")
        return

    # 统计已成功的城市数量
    existing_success_count = sum(1 for item in existing_items_by_city.values() if item.get("success") is True)
    
    print(f"需要重新爬取的城市数量: {len(cities_to_retry)}")
    print(f"已成功的城市数量: {existing_success_count}（将保留不变）")

    # 重新爬取失败的城市（使用暴力遍历）
    new_results: List[Dict[str, object]] = []
    cpu_count = multiprocessing.cpu_count()
    max_workers = min(cpu_count * 4, 64)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for city in cities_to_retry:
            # 从 CITY_SITE_SOURCES_WITH_URLS 获取该城市的 gov/fin 网站地址
            payload = CITY_SITE_SOURCES_WITH_URLS.get(city, {})
            gov = (payload.get("gov") or "").strip()
            fin = (payload.get("fin") or "").strip()
            if not gov and not fin:
                # 如果 gov 和 fin 都为空（如和田地区），跳过
                print(f"警告: {city}: gov 和 fin 均为空，跳过")
                continue
            fut = executor.submit(crawl_city, city, gov, fin, use_violent_fallback=False)
            futures[fut] = city

        for fut in as_completed(futures):
            try:
                result = fut.result()
                new_results.append(result)
            except Exception as e:
                # 异常城市也记录失败项
                city = futures[fut]
                new_results.append({
                    "city": city,
                    "gov": CITY_SITE_SOURCES_WITH_URLS.get(city, {}).get("gov", ""),
                    "fin": CITY_SITE_SOURCES_WITH_URLS.get(city, {}).get("fin", ""),
                    "urls": [],
                    "success": False,
                    "error": str(e),
                })

    # 合并结果：保留成功的城市，更新失败的城市
    final_items = []
    new_results_by_city = {r["city"]: r for r in new_results}
    
    # 遍历所有城市，决定使用哪个结果
    for city in CITY_SITE_SOURCES_WITH_URLS.keys():
        existing_item = existing_items_by_city.get(city)
        new_item = new_results_by_city.get(city)
        
        if existing_item and existing_item.get("success") is True:
            # 已成功的城市，保留原结果
            final_items.append(existing_item)
        elif new_item:
            # 新爬取的结果（覆盖失败的城市）
            final_items.append(new_item)
        elif existing_item:
            # 原有失败项且本次未重新爬取，保留原结果
            final_items.append(existing_item)
        else:
            # 新城市且未爬取成功，添加失败项
            payload = CITY_SITE_SOURCES_WITH_URLS.get(city, {})
            final_items.append({
                "city": city,
                "gov": payload.get("gov", ""),
                "fin": payload.get("fin", ""),
                "urls": [],
                "success": False,
            })
    
    # 统计成功数量
    success_count = sum(1 for item in final_items if item.get("success") is True)

    # 更新统计信息并写入文件
    total = len(CITY_SITE_SOURCES_WITH_URLS)
    failed_count = total - success_count

    payload = {
        "generated_at": datetime.now().isoformat(),
        "total_cities": total,
        "success_count": success_count,
        "failed_count": failed_count,
        "items": final_items,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"完成：成功 {success_count}/{total}，失败 {failed_count}，结果文件：{out_path}")


if __name__ == "__main__":
    main()


