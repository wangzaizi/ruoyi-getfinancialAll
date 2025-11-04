"""
基于拼音与缩写规则批量生成城市映射文件（CITY_SITE_OVERRIDES）。

探测策略（优先级顺序）：
1. 拼音规则探测（优先）：
   - 市政府：
     * https://www.{full}.gov.cn
     * https://{full}.gov.cn
     * http://www.{full}.gov.cn
     * http://{full}.gov.cn
     * https://www.{abbr}.gov.cn   （如 https://www.sm.gov.cn，三明市人民政府）
     * https://{abbr}.gov.cn   （如 gz.gov.cn / sz.gov.cn）
     * http://www.{abbr}.gov.cn
     * http://{abbr}.gov.cn
     * https://www.{abbr}s.gov.cn   （如 https://www.jcs.gov.cn，金昌市人民政府，缩写+市的首字母）
     * https://{abbr}s.gov.cn
     * http://www.{abbr}s.gov.cn
     * http://{abbr}s.gov.cn
   
   - 市财政局：
     * https://czj.{full}.gov.cn
     * http://czj.{full}.gov.cn
     * https://czj.{abbr}.gov.cn （如 czj.sz.gov.cn）
     * http://czj.{abbr}.gov.cn
     * https://cz.{full}.gov.cn （如 cz.sanming.gov.cn）
     * http://cz.{full}.gov.cn
     * https://cz.{abbr}.gov.cn （如 cz.sm.gov.cn，三明市财政局）
     * http://cz.{abbr}.gov.cn
     * https://mof.{full}.gov.cn （如 https://mof.sanya.gov.cn，三亚市财政局，mof=Ministry of Finance）
     * http://mof.{full}.gov.cn
     * https://mof.{abbr}.gov.cn
     * http://mof.{abbr}.gov.cn

2. 搜索引擎查找（当拼音规则未找到时）：
   - 支持多个搜索引擎：百度、必应、360、搜狗
   - 使用多种查询关键词组合
   - 自动验证DNS和HTTP可访问性

反爬虫技术：
- 随机User-Agent轮换（6种不同浏览器）
- 随机延迟（1-3秒）
- 随机化Referer请求头
- 搜索引擎顺序随机打乱
- 连接池复用和会话管理

优化说明：
- 自动检测CPU核心数，使用更多线程并发（CPU核心数 × 4，最多64线程）
- 优化连接池配置，提升网络IO效率
- 添加进度条显示，实时反馈处理状态
- 批量处理优化，减少资源开销
- 线程本地Session复用，减少连接开销

生成的新文件：generated_site_mappings.py（与 site_mappings.py 相同结构）。
"""

import os
import sys
import re
import socket
import random
import time
import logging
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, quote
from typing import Dict, Optional, Tuple, List
from threading import local

from config import TIMEOUT, DATA_DIR, LOG_DIR
from cities_data import CITIES
from datetime import datetime

# 优化配置：根据CPU核心数动态调整并发数
CPU_COUNT = multiprocessing.cpu_count()
# 使用更多线程：CPU核心数 * 4（IO密集型任务）
OPTIMIZED_MAX_WORKERS = min(CPU_COUNT * 4, 64)  # 最多64个线程，避免过多
# 连接池配置：每个线程需要更多连接
CONNECTION_POOL_SIZE = OPTIMIZED_MAX_WORKERS * 8
CONNECTION_POOL_MAXSIZE = OPTIMIZED_MAX_WORKERS * 16

logger = logging.getLogger("generate_site_mappings")
if not logger.handlers:
    # 创建日志文件路径（带时间戳）
    log_filename = os.path.join(LOG_DIR, f'generate_mappings_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    # 配置日志格式
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 创建文件handler和控制台handler
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别（包括DEBUG）
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # 控制台只显示INFO及以上
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # 配置logger
    logger.setLevel(logging.DEBUG)  # logger本身设置为DEBUG级别
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"日志文件: {log_filename}")
    logger.info(f"开始生成城市站点映射，日志将同时输出到文件和控制台")

# 线程本地存储，用于复用Session
_thread_local = local()

# 搜索引擎配置
SEARCH_ENGINES = ['baidu', 'bing', '360', 'sogou']

# 省份缩写前缀（用于 {prov}{city}.gov.cn 模式，如 hnloudi.gov.cn）
# 注：包含常见两字母/三字母形式，可能存在冲突但会通过存活检测过滤
PROVINCE_PREFIXES = [
    'bj','tj','sh','cq',
    'he','hb','sx','nm','nmg',
    'ln','jl','hlj',
    'js','zj','ah','fj','jx','sd',
    'ha','hen','hn','hb','hn','gd','gx','hi',
    'sc','gz','yn','xz','sn','gs','qh','nx','xj'
]

# User-Agent池（反爬虫）
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
]


def get_pinyin_parts(city: str):
    try:
        from pypinyin import pinyin, Style
        base = city.replace("市", "")
        full_list = pinyin(base, style=Style.NORMAL)
        full = "".join([x[0] for x in full_list])
        fl_list = pinyin(base, style=Style.FIRST_LETTER)
        abbr = "".join([x[0] for x in fl_list])
        return full.lower(), abbr.lower()
    except Exception:
        # 兜底：返回空，生成器会跳过
        return "", ""


def first_alive(session: requests.Session, candidates, timeout: float = None):
    """
    快速检测候选URL，使用更短的超时时间以提升效率
    先尝试HEAD请求（更快），如果失败再尝试GET请求（某些网站HEAD不支持）
    """
    if timeout is None:
        timeout = min(TIMEOUT, 8.0)  # 缩短超时时间，加快失败响应
    
    if not candidates:
        return None
    
    for i, u in enumerate(candidates):
        try:
            # 先尝试HEAD请求（更快）
            r = session.head(u, allow_redirects=True, timeout=timeout)
            if r.status_code == 200:
                # 归一化根域
                p = urlparse(r.url)
                result = f"{p.scheme}://{p.netloc}"
                logger.debug(f"成功访问(HEAD): {u} -> {result}")
                return result
            # 如果HEAD返回非200，尝试GET（某些网站HEAD不支持）
            elif r.status_code in [405, 403]:
                r2 = session.get(u, allow_redirects=True, timeout=timeout, stream=True)
                if r2.status_code == 200:
                    p = urlparse(r2.url)
                    result = f"{p.scheme}://{p.netloc}"
                    logger.debug(f"成功访问(GET): {u} -> {result}")
                    return result
        except requests.exceptions.Timeout:
            # 超时不记录（太多日志）
            continue
        except requests.exceptions.ConnectionError:
            # 连接错误不记录（太多日志）
            continue
        except Exception as e:
            # 如果HEAD失败，尝试GET
            try:
                r = session.get(u, allow_redirects=True, timeout=timeout, stream=True)
                if r.status_code == 200:
                    p = urlparse(r.url)
                    result = f"{p.scheme}://{p.netloc}"
                    logger.debug(f"成功访问(GET-fallback): {u} -> {result}")
                    return result
            except Exception:
                logger.debug(f"访问 {u} 失败: {type(e).__name__}")
                continue
    return None


def _get_session() -> requests.Session:
    """
    获取线程本地Session，复用连接以提升性能
    每个线程使用随机的User-Agent（反爬虫）
    """
    if not hasattr(_thread_local, 'session'):
        s = requests.Session()
        # 随机选择User-Agent
        ua = random.choice(USER_AGENTS)
        s.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        })
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            # 优化连接池配置：更大的连接池和重试策略
            retry_strategy = Retry(
                total=2,
                backoff_factor=0.3,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(
                pool_connections=CONNECTION_POOL_SIZE,
                pool_maxsize=CONNECTION_POOL_MAXSIZE,
                max_retries=retry_strategy,
                pool_block=False  # 非阻塞，提升并发
            )
            s.mount('http://', adapter)
            s.mount('https://', adapter)
        except Exception as e:
            logger.debug(f"连接池配置失败: {e}")
        _thread_local.session = s
    return _thread_local.session


def _random_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """随机延迟（反爬虫）"""
    time.sleep(random.uniform(min_sec, max_sec))


def _is_gov_root(url: str) -> bool:
    """检查是否为gov.cn根域"""
    try:
        u = urlparse(url)
        if not u.scheme or not u.netloc:
            return False
        # 排除文件扩展名
        if any(url.lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip']):
            return False
        return u.netloc.endswith('.gov.cn')
    except Exception:
        return False


def _normalize_root(url: str) -> str:
    """归一化URL为根域"""
    try:
        u = urlparse(url)
        scheme = 'https' if u.scheme == '' else u.scheme
        return f"{scheme}://{u.netloc}"
    except Exception:
        return url


def _dns_ok(url: str) -> bool:
    """DNS解析检查"""
    try:
        host = urlparse(url).netloc
        socket.gethostbyname(host)
        return True
    except Exception:
        return False


def _head_ok(session: requests.Session, url: str, timeout: float = 8.0) -> bool:
    """HEAD请求验证URL可访问"""
    try:
        r = session.head(url, allow_redirects=True, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _search_engine(session: requests.Session, engine: str, query: str) -> Optional[str]:
    """
    使用指定搜索引擎搜索，返回第一个有效的gov.cn根域
    """
    search_urls = {
        'baidu': f"https://www.baidu.com/s?wd={quote(query)}",
        'bing': f"https://cn.bing.com/search?q={quote(query)}",
        '360': f"https://www.so.com/s?q={quote(query)}",
        'sogou': f"https://www.sogou.com/web?query={quote(query)}",
    }
    
    if engine not in search_urls:
        return None
    
    url = search_urls[engine]
    
    # 反爬虫：随机延迟
    _random_delay(1.0, 2.5)
    
    try:
        # 随机化请求头（每次请求）
        headers = session.headers.copy()
        headers['Referer'] = random.choice([
            'https://www.baidu.com/',
            'https://cn.bing.com/',
        ])
        
        r = session.get(url, headers=headers, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        
        # 提取所有gov.cn域名
        pattern = re.compile(r"https?://[\w\.-]*gov\.cn[^\"'<>)\s]*", re.IGNORECASE)
        found = pattern.findall(r.text)
        
        # 去重并归一化
        seen = set()
        candidates = []
        for u in found:
            root = _normalize_root(u)
            if not _is_gov_root(root):
                continue
            if root not in seen:
                seen.add(root)
                candidates.append(root)
        
        # 验证前10个候选（DNS + HEAD）
        for cand in candidates[:10]:
            if _dns_ok(cand) and _head_ok(session, cand, timeout=6.0):
                return cand
        
        return None
    except Exception as e:
        logger.debug(f"搜索引擎 {engine} 搜索失败: {e}")
        return None


def _search_by_engines(city: str, site_type: str) -> Optional[str]:
    """
    使用多个搜索引擎查找市政府或财政局网站
    site_type: 'gov' 或 'fin'
    """
    session = _get_session()
    
    if site_type == 'gov':
        queries = [
            f"site:.gov.cn {city} 人民政府",
            f"{city} 人民政府 官网",
            f"{city} 政府网站",
            f"{city} 市政府",
        ]
    elif site_type == 'fin':
        queries = [
            f"site:.gov.cn {city} 财政局",
            f"{city} 财政局 官网",
            f"{city} 财政局 网站",
            f"{city} 财政局 门户",
        ]
    else:
        return None
    
    # 随机打乱搜索引擎顺序
    engines = SEARCH_ENGINES.copy()
    random.shuffle(engines)
    
    # 尝试每个查询和每个引擎
    for query in queries:
        for engine in engines:
            result = _search_engine(session, engine, query)
            if result:
                logger.info(f"[搜索引擎] {city} {site_type}: {engine} 找到 {result}")
                return result
            # 引擎间延迟
            _random_delay(0.5, 1.5)
        # 查询间延迟
        _random_delay(1.0, 2.0)
    
    return None


def _process_city(city: str) -> tuple:
    """
    处理单个城市，使用线程本地Session复用连接
    1. 先尝试拼音规则
    2. 如果失败，使用搜索引擎（反爬虫）
    """
    session = _get_session()
    full, abbr = get_pinyin_parts(city)
    
    # 生成候选URL列表
    gov_candidates = []
    if full:
        gov_candidates.extend([
            f"https://www.{full}.gov.cn",
            f"https://{full}.gov.cn",
            f"http://www.{full}.gov.cn",
            f"http://{full}.gov.cn",
        ])
    if abbr:
        gov_candidates.extend([
            f"https://www.{abbr}.gov.cn",  # 如 https://www.sm.gov.cn（三明市人民政府）
            f"https://{abbr}.gov.cn",
            f"http://www.{abbr}.gov.cn",
            f"http://{abbr}.gov.cn",
            f"https://www.{abbr}s.gov.cn",  # 如 https://www.jcs.gov.cn（金昌市人民政府，缩写+市的首字母）
            f"https://{abbr}s.gov.cn",
            f"http://www.{abbr}s.gov.cn",
            f"http://{abbr}s.gov.cn",
        ])

    # 省缩写前缀 + 城市全拼/缩写（如 hnloudi.gov.cn / hnsz.gov.cn）
    for prov in PROVINCE_PREFIXES:
        if full:
            gov_candidates.extend([
                f"https://{prov}{full}.gov.cn",
                f"http://{prov}{full}.gov.cn",
                f"https://www.{prov}{full}.gov.cn",
                f"http://www.{prov}{full}.gov.cn",
            ])
        if abbr:
            gov_candidates.extend([
                f"https://{prov}{abbr}.gov.cn",
                f"http://{prov}{abbr}.gov.cn",
                f"https://www.{prov}{abbr}.gov.cn",
                f"http://www.{prov}{abbr}.gov.cn",
            ])

    fin_candidates = []
    if full:
        fin_candidates.extend([
            f"https://czj.{full}.gov.cn",
            f"http://czj.{full}.gov.cn",
            f"https://cz.{full}.gov.cn",  # 如 cz.sanming.gov.cn
            f"http://cz.{full}.gov.cn",
            f"https://mof.{full}.gov.cn",  # 如 https://mof.sanya.gov.cn（三亚市财政局，mof=Ministry of Finance）
            f"http://mof.{full}.gov.cn",
        ])
    if abbr:
        fin_candidates.extend([
            f"https://czj.{abbr}.gov.cn",
            f"http://czj.{abbr}.gov.cn",
            f"https://cz.{abbr}.gov.cn",  # 如 cz.sm.gov.cn（三明市财政局）
            f"http://cz.{abbr}.gov.cn",
            f"https://mof.{abbr}.gov.cn",  # 如 mof.sy.gov.cn（如果使用缩写）
            f"http://mof.{abbr}.gov.cn",
        ])

    # 省缩写前缀 + 财政局（如 czj.hnloudi.gov.cn / czj.hnsz.gov.cn）
    for prov in PROVINCE_PREFIXES:
        if full:
            fin_candidates.extend([
                f"https://czj.{prov}{full}.gov.cn",
                f"http://czj.{prov}{full}.gov.cn",
                f"https://mof.{prov}{full}.gov.cn",
                f"http://mof.{prov}{full}.gov.cn",
            ])
        if abbr:
            fin_candidates.extend([
                f"https://czj.{prov}{abbr}.gov.cn",
                f"http://czj.{prov}{abbr}.gov.cn",
                f"https://mof.{prov}{abbr}.gov.cn",
                f"http://mof.{prov}{abbr}.gov.cn",
            ])

    # 先尝试拼音规则检测
    logger.debug(f"[{city}] 尝试 {len(gov_candidates)} 个gov候选URL，{len(fin_candidates)} 个fin候选URL")
    if gov_candidates:
        logger.debug(f"[{city}] gov候选: {gov_candidates[:3]}...")  # 只显示前3个
    if fin_candidates:
        logger.debug(f"[{city}] fin候选: {fin_candidates[:3]}...")  # 只显示前3个
    
    gov = first_alive(session, gov_candidates, timeout=6.0)
    fin = first_alive(session, fin_candidates, timeout=6.0)
    
    if gov:
        logger.info(f"[{city}] 拼音规则找到gov: {gov}")
    if fin:
        logger.info(f"[{city}] 拼音规则找到fin: {fin}")
    
    # 如果拼音规则未找到，使用搜索引擎
    if not gov:
        logger.info(f"[{city}] 拼音规则未找到gov（尝试了 {len(gov_candidates)} 个URL），尝试搜索引擎...")
        gov = _search_by_engines(city, 'gov')
    
    if not fin:
        logger.info(f"[{city}] 拼音规则未找到fin（尝试了 {len(fin_candidates)} 个URL），尝试搜索引擎...")
        fin = _search_by_engines(city, 'fin')
    
    result = {"gov": gov or "", "fin": fin or ""}
    if not result["gov"] and not result["fin"]:
        logger.warning(f"[{city}] 未能找到任何网站（gov/fin均为空）")
    return city, result


def generate_mapping() -> Dict[str, Dict[str, str]]:
    """
    生成映射，使用优化的并发配置
    """
    total = len(CITIES)
    logger.info(f"开始基于拼音/缩写规则生成映射，共 {total} 个城市 …")
    logger.info(f"并发配置: {OPTIMIZED_MAX_WORKERS} 个工作线程 (CPU核心数: {CPU_COUNT})")
    logger.info(f"连接池配置: pool_connections={CONNECTION_POOL_SIZE}, pool_maxsize={CONNECTION_POOL_MAXSIZE}")

    mapping: Dict[str, Dict[str, str]] = {}
    completed = 0
    
    # 使用优化的线程池
    with ThreadPoolExecutor(max_workers=OPTIMIZED_MAX_WORKERS) as executor:
        # 批量提交任务
        futures = {executor.submit(_process_city, city): city for city in CITIES}
        
        # 处理完成的任务，带进度显示
        for fut in as_completed(futures):
            city = futures[fut]
            try:
                c, res = fut.result()
                mapping[c] = res
                completed += 1
                # 每10个城市打印一次进度
                if completed % 10 == 0 or completed == total:
                    logger.info(f"进度: {completed}/{total} ({completed*100//total}%) | 最新: {c} - gov={res.get('gov', '-')[:30] or '-'} | fin={res.get('fin', '-')[:30] or '-'}")
            except Exception as e:
                logger.error(f"{city}: 处理失败 {e}")
                completed += 1

    logger.info(f"映射生成完成。共处理 {completed} 个城市，成功 {len(mapping)} 个。")
    return mapping


def render_mapping_py(mapping: Dict[str, Dict[str, str]]) -> str:
    header = (
        '"""\n城市站点映射（自动生成）。若有错误请手动修正。\n\n'
        'CITY_SITE_OVERRIDES = {\n    "城市名": {"gov": "市政府根域", "fin": "财政局根域"}\n}\n"""\n\n'
    )
    lines = [header, "CITY_SITE_OVERRIDES = {\n"]
    for city in sorted(mapping.keys()):
        gov = mapping[city].get('gov', '')
        fin = mapping[city].get('fin', '')
        lines.append(f'    "{city}": {{"gov": "{gov}", "fin": "{fin}"}},\n')
    lines.append("}\n")
    return ''.join(lines)


def main():
    """
    主函数：生成映射并保存到文件
    """
    import time
    start_time = time.time()
    
    try:
        mapping = generate_mapping()
        out_file = os.path.join(os.path.dirname(__file__), 'generated_site_mappings.py')
        content = render_mapping_py(mapping)
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        elapsed = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"映射生成完成！")
        print(f"输出文件: {out_file}")
        print(f"总城市数: {len(mapping)}")
        print(f"耗时: {elapsed:.2f} 秒")
        print(f"平均速度: {len(mapping)/elapsed:.2f} 城市/秒")
        print(f"{'='*60}\n")
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
        sys.exit(1)
    except Exception as e:
        logger.error(f"生成失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()


