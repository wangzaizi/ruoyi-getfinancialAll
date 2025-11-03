"""
基于拼音与缩写规则批量生成城市映射文件（CITY_SITE_OVERRIDES）。

仅使用以下域名模式进行探测：
- 市政府：
  - https://www.{full}.gov.cn
  - https://{full}.gov.cn
  - http://www.{full}.gov.cn
  - http://{full}.gov.cn
  - https://{abbr}.gov.cn   （如 gz.gov.cn / sz.gov.cn）
  - http://{abbr}.gov.cn

- 市财政局：
  - https://czj.{full}.gov.cn
  - http://czj.{full}.gov.cn
  - https://czj.{abbr}.gov.cn （如 czj.sz.gov.cn）
  - http://czj.{abbr}.gov.cn

验证优先级按上列顺序，取首个可用根域。
生成的新文件：generated_site_mappings.py（与 site_mappings.py 相同结构）。
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup  # 仅为一致依赖，不用于解析
from urllib.parse import urlparse
from typing import Dict, Optional

from config import TIMEOUT, MAX_WORKERS
from cities_data import CITIES


logger = logging.getLogger("generate_site_mappings")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


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


def first_alive(session: requests.Session, candidates):
    for u in candidates:
        try:
            r = session.head(u, allow_redirects=True, timeout=TIMEOUT)
            if r.status_code == 200:
                # 归一化根域
                p = urlparse(r.url)
                return f"{p.scheme}://{p.netloc}"
        except Exception:
            continue
    return None


def _build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    })
    try:
        from requests.adapters import HTTPAdapter
        adapter = HTTPAdapter(pool_connections=MAX_WORKERS * 2, pool_maxsize=MAX_WORKERS * 4)
        s.mount('http://', adapter)
        s.mount('https://', adapter)
    except Exception:
        pass
    return s


def _process_city(city: str) -> (str, Dict[str, str]):
    session = _build_session()
    full, abbr = get_pinyin_parts(city)
    if not full and not abbr:
        logger.warning(f"{city}: 无法生成拼音，跳过")
        return city, {"gov": "", "fin": ""}

    gov_candidates = []
    if full:
        gov_candidates += [
            f"https://www.{full}.gov.cn",
            f"https://{full}.gov.cn",
            f"http://www.{full}.gov.cn",
            f"http://{full}.gov.cn",
        ]
    if abbr:
        gov_candidates += [
            f"https://{abbr}.gov.cn",
            f"http://{abbr}.gov.cn",
        ]

    fin_candidates = []
    if full:
        fin_candidates += [
            f"https://czj.{full}.gov.cn",
            f"http://czj.{full}.gov.cn",
        ]
    if abbr:
        fin_candidates += [
            f"https://czj.{abbr}.gov.cn",
            f"http://czj.{abbr}.gov.cn",
        ]

    gov = first_alive(session, gov_candidates)
    fin = first_alive(session, fin_candidates)
    logger.info(f"{city}: gov={gov or '-'} | fin={fin or '-'}")
    return city, {"gov": gov or "", "fin": fin or ""}


def generate_mapping() -> Dict[str, Dict[str, str]]:
    total = len(CITIES)
    logger.info(f"开始基于拼音/缩写规则生成映射，共 {total} 个城市 …")

    mapping: Dict[str, Dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_process_city, city): city for city in CITIES}
        for fut in as_completed(futures):
            city = futures[fut]
            try:
                c, res = fut.result()
                mapping[c] = res
            except Exception as e:
                logger.error(f"{city}: 处理失败 {e}")

    logger.info("映射生成完成。")
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
    mapping = generate_mapping()
    out_file = os.path.join(os.path.dirname(__file__), 'generated_site_mappings.py')
    content = render_mapping_py(mapping)
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"已生成: {out_file}")


if __name__ == '__main__':
    main()


