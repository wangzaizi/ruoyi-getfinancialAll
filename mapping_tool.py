"""
城市站点映射测试与迭代工具（不修改 spider.py）。

功能：
- 基于 site_mappings.py 的 CITY_SITE_OVERRIDES 测试各城市的市政府(gov)与财政局(fin)根域是否可访问
- 对缺失或不可用项，使用百度搜索给出建议，不落地CSV/JSON
- 可选的自动更新：将建议写回 site_mappings.py（默认关闭）
"""

import os
import re
import json
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from typing import Dict, List, Optional

from config import DATA_DIR, TIMEOUT
from cities_data import CITIES
from site_mappings import CITY_SITE_OVERRIDES
from city_site_resolver import suggest_city_sites


logger = logging.getLogger("mapping_tool")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def verify_site_alive(session: requests.Session, url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        r = session.head(url, allow_redirects=True, timeout=7)
        return r.status_code == 200
    except Exception:
        return False


def baidu_guess(session: requests.Session, city: str, query: str) -> Optional[str]:
    try:
        q = f"{city} {query}"
        url = f"https://www.baidu.com/s?wd={quote(q)}"
        r = session.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        pattern = re.compile(r"https?://[\w\.-]*gov\.cn")
        candidates = []
        for a in soup.find_all('a', href=True):
            for text in (a.get('href', ''), a.get_text() or ''):
                m = pattern.search(text)
                if m:
                    c = m.group(0)
                    if c not in candidates:
                        candidates.append(c)
        for c in candidates[:10]:
            try:
                if verify_site_alive(session, c):
                    return c
            except Exception:
                continue
        return None
    except Exception:
        return None


def render_mapping_py(mapping: Dict[str, Dict[str, str]]) -> str:
    """根据映射字典渲染 site_mappings.py 文件内容。"""
    header = (
        '"""\n城市站点映射（优先使用），可按需补充与修正。\n\n'
        '结构：\nCITY_SITE_OVERRIDES = {\n    "城市名": {\n        "gov": "市政府网站根域",\n        "fin": "市财政局网站根域（若有）"\n    },\n    ...\n}\n"""\n\n'
    )
    lines = [header, "CITY_SITE_OVERRIDES = {\n"]
    for city in sorted(mapping.keys()):
        gov = mapping[city].get('gov', '')
        fin = mapping[city].get('fin', '')
        lines.append(f'    "{city}": {{"gov": "{gov}", "fin": "{fin}"}},\n')
    lines.append("}\n")
    return ''.join(lines)


def test_and_iterate_mappings(cities: Optional[List[str]] = None, auto_update: bool = False) -> Dict[str, Dict[str, str]]:
    """
    仅依赖 site_mappings.py 进行测试；对缺失/不可用项通过百度搜索给建议。
    - auto_update=False：只打印建议；
    - auto_update=True：把建议直接写回 site_mappings.py（谨慎使用）。
    返回：city -> {gov_mapped, gov_ok, gov_suggest, fin_mapped, fin_ok, fin_suggest}
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    })

    cities_to_check = cities or CITIES
    total = len(cities_to_check)
    results: Dict[str, Dict[str, str]] = {}

    logger.info(f"[映射测试] 共 {total} 个城市，基于 site_mappings.py 进行验证与建议 …")

    # 工作副本，便于 auto_update
    mapping_copy = {k: dict(v) for k, v in CITY_SITE_OVERRIDES.items()}

    for city in cities_to_check:
        m = mapping_copy.get(city, {})
        gov_m = m.get('gov')
        fin_m = m.get('fin')

        gov_ok = verify_site_alive(session, gov_m)
        fin_ok = verify_site_alive(session, fin_m)

        gov_suggest = None
        fin_suggest = None

        if not gov_ok or not fin_ok:
            # 使用独立解析器（含多引擎、缓存、反爬缓解）
            sg, sf = suggest_city_sites(city)
            if not gov_ok:
                gov_suggest = sg
            if not fin_ok:
                fin_suggest = sf

        if gov_suggest and not verify_site_alive(session, gov_suggest):
            gov_suggest = None
        if fin_suggest and not verify_site_alive(session, fin_suggest):
            fin_suggest = None

        results[city] = {
            'gov_mapped': gov_m or '',
            'gov_ok': str(gov_ok),
            'gov_suggest': gov_suggest or '',
            'fin_mapped': fin_m or '',
            'fin_ok': str(fin_ok),
            'fin_suggest': fin_suggest or ''
        }

        if (not gov_ok and gov_suggest) or (not fin_ok and fin_suggest):
            logger.info(
                f"[建议补全] {city}: 建议 -> {{'gov': '{gov_suggest or gov_m or ''}', 'fin': '{fin_suggest or fin_m or ''}'}}"
            )
            if auto_update:
                mapping_copy.setdefault(city, {})
                if gov_suggest:
                    mapping_copy[city]['gov'] = gov_suggest
                if fin_suggest:
                    mapping_copy[city]['fin'] = fin_suggest
        elif not gov_ok and not fin_ok:
            logger.warning(f"[缺失] {city}: gov/fin 映射均不可用且未找到可靠建议")
        else:
            logger.info(f"[通过] {city}: gov_ok={gov_ok}, fin_ok={fin_ok}")

    if auto_update:
        # 写回 site_mappings.py
        new_content = render_mapping_py(mapping_copy)
        with open(os.path.join(os.path.dirname(__file__), 'site_mappings.py'), 'w', encoding='utf-8') as f:
            f.write(new_content)
        logger.info("已根据建议自动更新 site_mappings.py。")

    logger.info("[映射测试] 完成。如需更新，请将 [建议补全] 行手动写入 site_mappings.py，或开启 auto_update。")
    return results


def run_city_mapping_mode(auto_update: bool = True):
    """命令式入口：映射测试（可选自动更新）"""
    test_and_iterate_mappings(auto_update=auto_update)


