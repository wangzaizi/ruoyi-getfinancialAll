"""
城市网站解析器（不修改 spider.py）。

目标：当 gov/fin 为空时，利用搜索引擎与温和反爬策略，给出建议根域：
 - gov: 市人民政府门户
 - fin: 市财政局门户

策略：
 - 关键词模板：
   * "{城市} 人民政府 官网"、"{城市} 政府网站"
   * "{城市} 财政局 官网"、"{城市} 财政局 网站"
 - 搜索算子：site:.gov.cn {城市} 人民政府 / 财政局
 - 多引擎：百度、必应（cn.bing.com）
 - 过滤：仅接受 *.gov.cn 根域（优先 https），剔除PDF等直链
 - 验证：HEAD=200、可 DNS 解析
 - 反爬：随机延迟(2-6s)、指数退避、失败重试≤3、连接池、限速
 - 缓存：data/cache_city_sites.json，避免重复查询
"""

import os
import re
import json
import time
import random
import socket
import logging
import requests
from urllib.parse import quote, urlparse
from typing import Dict, Optional, Tuple

from config import DATA_DIR, TIMEOUT, MAX_WORKERS


logger = logging.getLogger("city_site_resolver")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


CACHE_FILE = os.path.join(DATA_DIR, 'cache_city_sites.json')


def _build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    })
    try:
        from requests.adapters import HTTPAdapter
        adapter = HTTPAdapter(pool_connections=MAX_WORKERS*2, pool_maxsize=MAX_WORKERS*4)
        s.mount('http://', adapter)
        s.mount('https://', adapter)
    except Exception:
        pass
    return s


def _sleep_backoff(attempt: int):
    base = random.uniform(2.0, 6.0)
    delay = base * (2 ** max(0, attempt-1))
    time.sleep(min(delay, 20.0))


def _is_gov_root(url: str) -> bool:
    try:
        u = urlparse(url)
        if not u.scheme or not u.netloc:
            return False
        if any(url.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
            return False
        return u.netloc.endswith('.gov.cn')
    except Exception:
        return False


def _normalize_root(url: str) -> str:
    u = urlparse(url)
    scheme = 'https' if u.scheme == '' else u.scheme
    return f"{scheme}://{u.netloc}"


def _head_ok(session: requests.Session, url: str) -> bool:
    try:
        r = session.head(url, allow_redirects=True, timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


def _dns_ok(url: str) -> bool:
    try:
        host = urlparse(url).netloc
        socket.gethostbyname(host)
        return True
    except Exception:
        return False


def _search_once(session: requests.Session, engine: str, q: str) -> Optional[str]:
    if engine == 'baidu':
        url = f"https://www.baidu.com/s?wd={quote(q)}"
    elif engine == 'bing':
        url = f"https://cn.bing.com/search?q={quote(q)}"
    else:
        return None

    for attempt in range(1, 4):
        try:
            r = session.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                _sleep_backoff(attempt)
                continue
            # 提取 *.gov.cn 根域
            pattern = re.compile(r"https?://[\w\.-]*gov\.cn")
            found = pattern.findall(r.text)
            # 去重，优先 https
            uniq = []
            seen = set()
            for u in found:
                root = _normalize_root(u)
                if not _is_gov_root(root):
                    continue
                if root not in seen:
                    seen.add(root)
                    uniq.append(root)
            # 依次验证
            for cand in uniq[:10]:
                if _dns_ok(cand) and _head_ok(session, cand):
                    return cand
            return None
        except Exception:
            _sleep_backoff(attempt)
            continue
    return None


def _load_cache() -> Dict[str, Dict[str, str]]:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Dict[str, str]]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def suggest_city_sites(city: str) -> Tuple[Optional[str], Optional[str]]:
    """
    返回 (gov_suggest, fin_suggest)。可能为 None。
    """
    cache = _load_cache()
    if city in cache:
        c = cache[city]
        return (c.get('gov') or None, c.get('fin') or None)

    session = _build_session()
    # gov 关键词
    gov_queries = [
        f"site:.gov.cn {city} 人民政府",
        f"{city} 人民政府 官网",
        f"{city} 政府网站",
    ]
    # fin 关键词
    fin_queries = [
        f"site:.gov.cn {city} 财政局",
        f"{city} 财政局 官网",
        f"{city} 财政局 网站",
    ]

    gov_suggest = None
    fin_suggest = None

    # 多引擎轮询
    engines = ['baidu', 'bing']
    for q in gov_queries:
        for e in engines:
            gov_suggest = _search_once(session, e, q)
            if gov_suggest:
                break
        if gov_suggest:
            break

    for q in fin_queries:
        for e in engines:
            fin_suggest = _search_once(session, e, q)
            if fin_suggest:
                break
        if fin_suggest:
            break

    # 仅缓存建议（不覆盖空）
    cache[city] = {
        'gov': gov_suggest or '',
        'fin': fin_suggest or ''
    }
    _save_cache(cache)
    return gov_suggest, fin_suggest


