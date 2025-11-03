"""
财政报告爬虫主程序
"""
import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote, parse_qsl, urlunparse
from pathlib import Path
import re
from typing import List, Dict, Optional
from tqdm import tqdm
import json
from datetime import datetime

from config import *
from cities_data import CITIES


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, f'spider_{datetime.now().strftime("%Y%m%d")}.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FinanceReportSpider:
    """财政报告爬虫"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.downloaded = {}  # 记录已下载的文件
        self.failed_cities = []  # 记录失败的城市
        
        # 已知政府网站URL映射（常用城市）
        self.known_websites = {
            "北京市": "https://www.beijing.gov.cn",
            "上海市": "https://www.shanghai.gov.cn",
            "天津市": "https://www.tianjin.gov.cn",
            "重庆市": "https://www.cq.gov.cn",
            "赣州市": "https://www.ganzhou.gov.cn",
            "杭州市": "https://www.hangzhou.gov.cn",
            "深圳市": "https://www.sz.gov.cn",
        }
        # 为requests配置连接池，提升并发能力
        try:
            from requests.adapters import HTTPAdapter
            adapter = HTTPAdapter(pool_connections=MAX_WORKERS * 2, pool_maxsize=MAX_WORKERS * 4)
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)
        except Exception:
            pass
        
    def search_government_website(self, city: str) -> Optional[str]:
        """
        通过构造URL（基于拼音和首字母缩写）来查找并验证给定城市的财政局官方网站。
        """
        from pypinyin import pinyin, Style

        logger.info(f"[{city}] 开始通过构造URL查找财政局网站...")
        
        # 移除城市名称中的“市”字以便生成拼音
        city_name_for_pinyin = city.replace("市", "")
        
        # 1. 获取全拼
        pinyin_full_list = pinyin(city_name_for_pinyin, style=Style.NORMAL)
        city_pinyin_full = "".join([item[0] for item in pinyin_full_list])
        
        # 2. 获取首字母
        pinyin_first_letter_list = pinyin(city_name_for_pinyin, style=Style.FIRST_LETTER)
        city_pinyin_first = "".join([item[0] for item in pinyin_first_letter_list])

        # 构造可能的域名列表
        possible_domains = [
            # 财政局常见二级域
            f"czj.{city_pinyin_full}.gov.cn",
            f"czj.{city_pinyin_first}.gov.cn",
            # 财政厅/财政变体
            f"czt.{city_pinyin_full}.gov.cn",
            f"czt.{city_pinyin_first}.gov.cn",
            f"{city_pinyin_full}cz.gov.cn",
            # 财政局英文/缩写（如深圳：szfb.sz.gov.cn）
            f"{city_pinyin_first}fb.{city_pinyin_first}.gov.cn",
            f"{city_pinyin_first}fb.{city_pinyin_full}.gov.cn",
            f"{city_pinyin_full}fb.{city_pinyin_first}.gov.cn",
            f"{city_pinyin_full}fb.{city_pinyin_full}.gov.cn",
        ]

        for domain in possible_domains:
            for scheme in ["https://", "http://"]: # 优先使用HTTPS
                url = f"{scheme}{domain}"
                try:
                    # 使用HEAD请求快速检查
                    response = self.session.head(url, allow_redirects=True, timeout=7)
                    if response.status_code == 200:
                        final_url = urlparse(response.url)
                        base_url = f"{final_url.scheme}://{final_url.netloc}"
                        
                        # 进一步验证页面标题
                        page_res = self.session.get(base_url, timeout=10)
                        page_soup = BeautifulSoup(page_res.content, 'lxml')
                        page_title = page_soup.title.string if page_soup.title else ""

                        if "财政" in page_title:
                            logger.info(f"[{city}] 通过构造URL找到并验证了财政局网站: {base_url}")
                            return base_url
                        else:
                            logger.warning(f"[{city}] 网站 {base_url} 标题不含'财政'，继续尝试。")
                            
                except requests.RequestException:
                    continue # 连接失败，继续尝试下一个

        logger.error(f"[{city}] 未能通过构造URL找到有效的财政局网站。")
        return None
    
    def matches_keywords(self, text: str, city_name: str) -> bool:
        """
        检查文本是否匹配财政决算报告的关键词。
        - 必须包含年份
        - 必须包含城市名或“本级”/“市级”
        - 必须包含“决算”
        - 必须排除“部门”、“单位”等关键词
        """
        if not text:
            return False

        year = str(TARGET_YEAR)
        
        # 检查是否包含年份
        if year not in text:
            return False
        
        # 检查是否包含城市名或“本级”
        city_name_no_shi = city_name.replace('市', '')
        if not (city_name_no_shi in text or '本级' in text or '市级' in text):
            return False
            
        # 必须包含“决算”
        if '决算' not in text:
            return False

        # 排除部门决算
        excluded_keywords = ['部门', '单位', '街道', '镇', '乡']
        if any(kw in text for kw in excluded_keywords):
            return False

        return True
    
    def find_next_page_url(self, page_url: str, soup: BeautifulSoup) -> Optional[str]:
        """
        查找搜索结果页面的下一页链接
        返回下一页URL，如果没有则返回None
        """
        try:
            # 查找包含"下一页"、"下页"、"next"等关键词的链接
            # 方法1: 通过文本内容查找
            text_pattern = re.compile(r'(下一页|下页|next|more)', re.I)
            text_links = soup.find_all('a', href=True, string=text_pattern)
            for link in text_links:
                href = link.get('href', '')
                if href:
                    full_url = urljoin(page_url, href)
                    if full_url != page_url:
                        return full_url
            
            # 方法2: 通过class属性查找
            class_links = soup.find_all('a', class_=re.compile(r'(next|page-next)', re.I), href=True)
            for link in class_links:
                href = link.get('href', '')
                if href:
                    full_url = urljoin(page_url, href)
                    if full_url != page_url:
                        return full_url
            
            # 方法3: 通过id属性查找
            id_links = soup.find_all('a', id=re.compile(r'(next|page-next)', re.I), href=True)
            for link in id_links:
                href = link.get('href', '')
                if href:
                    full_url = urljoin(page_url, href)
                    if full_url != page_url:
                        return full_url
            
            # 查找页码链接（查找比当前页更大的页码）
            page_links = soup.find_all('a', href=True, string=re.compile(r'^\d+$'))
            current_page_num = None
            
            # 尝试从URL中提取当前页码
            url_match = re.search(r'[?&]page[=_]?(\d+)', page_url)
            if url_match:
                current_page_num = int(url_match.group(1))
            
            if current_page_num is not None:
                for link in page_links:
                    page_text = link.get_text().strip()
                    try:
                        page_num = int(page_text)
                        if page_num > current_page_num:
                            href = link.get('href', '')
                            if href:
                                return urljoin(page_url, href)
                    except:
                        continue
            
            # 查找常见的页码参数模式
            # 尝试增加pageNum、page、p等参数
            url_parts = list(urlparse(page_url))
            query_params = dict(parse_qsl(url_parts[4]))
            
            # 尝试各种页码参数名
            page_param_names = ['pageNum', 'page', 'p', 'pn', 'currentPage', 'pageIndex']
            for param_name in page_param_names:
                if param_name in query_params:
                    try:
                        current_page = int(query_params[param_name])
                        query_params[param_name] = str(current_page + 1)
                        new_query = '&'.join([f"{k}={v}" for k, v in query_params.items()])
                        url_parts[4] = new_query
                        next_url = urlunparse(url_parts)
                        return next_url
                    except:
                        continue
            
            return None
            
        except Exception as e:
            logger.debug(f"查找下一页链接失败: {e}")
            return None
    
    def parse_search_results(self, start_url: str, city_name: str) -> List[Dict]:
        """
        从给定的起始页面解析并提取财政决算报告的链接。
        支持分页，会遍历所有页面直到结尾。
        """
        all_reports = []
        processed_pages = set()  # 用于避免重复处理同一页面
        current_page_url = start_url
        max_pages = 100  # 防止无限循环，最多遍历100页
        
        try:
            page_count = 0
            while current_page_url and page_count < max_pages:
                if current_page_url in processed_pages:
                    logger.info(f"页面已处理过，跳过: {current_page_url}")
                    break
                processed_pages.add(current_page_url)
                
                page_count += 1
                logger.info(f"解析页面 {page_count}: {current_page_url}")
                
                response = self.session.get(current_page_url, timeout=TIMEOUT)
                if response.status_code != 200:
                    logger.warning(f"无法访问页面 {current_page_url}，状态码: {response.status_code}")
                    break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                all_links = soup.find_all('a', href=True)
                logger.info(f"页面 {page_count} 找到 {len(all_links)} 个链接，开始过滤...")
                
                processed_urls = set()  # 用于去重
                page_reports = []
                
                for link in all_links:
                    href = link.get('href', '')
                    title = link.get_text().strip()
                    
                    if not href or href.startswith('javascript:') or href.startswith('#'):
                        continue
                    
                    try:
                        full_url = urljoin(current_page_url, href)
                    except:
                        continue
                    
                    if full_url in processed_urls:
                        continue
                    processed_urls.add(full_url)
                    
                    # 获取链接周围的文本以获得更多上下文
                    parent_text = link.parent.get_text().strip() if link.parent else ''
                    combined_text = f"{title} {parent_text}"
                    
                    if self.matches_keywords(combined_text, city_name):
                        page_reports.append({
                            'title': title or href.split('/')[-1],
                            'url': full_url
                        })
                
                logger.info(f"页面 {page_count} 提取到 {len(page_reports)} 个相关链接")
                all_reports.extend(page_reports)
                
                next_page_url = self.find_next_page_url(current_page_url, soup)
                if next_page_url:
                    logger.info(f"找到下一页: {next_page_url}")
                    current_page_url = next_page_url
                    time.sleep(REQUEST_DELAY)
                else:
                    logger.info(f"已到达最后一页（第 {page_count} 页）")
                    break
            
            logger.info(f"总共遍历了 {page_count} 页，提取到 {len(all_reports)} 个相关链接")
            
        except Exception as e:
            logger.error(f"解析页面失败 {start_url}: {e}")
        
        return all_reports
    
    def use_site_search(self, base_url: str, city: str) -> List[Dict]:
        """
        简单站内检索：尝试识别常见搜索表单与参数名，提交“决算 + 年份 + 层级/城市名”关键词，
        回收结果页并复用分页解析逻辑。
        """
        reports: List[Dict] = []
        try:
            response = self.session.get(base_url, timeout=TIMEOUT)
            if response.status_code != 200:
                return reports
            soup = BeautifulSoup(response.text, 'html.parser')

            # 候选搜索参数名；关键词统一使用“决算”，时间范围尽量设置为目标年份
            param_candidates = ['q', 'wd', 'keyword', 'searchWord', 'title', 'k', 'key']
            keywords = ["决算"]

            tried_urls = set()

            # 1) 解析首页表单
            forms = soup.find_all('form')
            for form in forms:
                action = form.get('action') or ''
                method = (form.get('method') or 'get').lower()
                form_url = urljoin(base_url, action) if action else base_url

                # 收集已有隐藏/文本字段
                form_fields = {}
                for inp in form.find_all('input'):
                    name = inp.get('name')
                    if not name:
                        continue
                    val = inp.get('value') or ''
                    form_fields[name] = val

                # 确定搜索参数名
                search_param = None
                for cand in param_candidates:
                    if cand in form_fields:
                        search_param = cand
                        break
                if not search_param:
                    # 尝试从input[text]里挑一个常见name
                    for inp in form.find_all('input'):
                        if inp.get('type', 'text').lower() in ['text', 'search']:
                            n = inp.get('name')
                            if n:
                                search_param = n
                                break

                if not search_param:
                    continue

                for kw in keywords:
                    params = dict(form_fields)
                    params[search_param] = kw

                    # 如表单包含时间或年份字段，则尽量约束到目标年份
                    try:
                        # 常见时间字段名
                        start_keys = ['startTime', 'start_time', 'stime', 'startDate', 'start_date', 'from', 'fromDate']
                        end_keys = ['endTime', 'end_time', 'etime', 'endDate', 'end_date', 'to', 'toDate']
                        year_keys = ['year', 'yearStr', 'time', 'sj']

                        start_val = f"{TARGET_YEAR}-01-01 00:00:00"
                        end_val = f"{TARGET_YEAR}-12-31 23:59:59"

                        for k in start_keys:
                            if k in params:
                                params[k] = start_val
                        for k in end_keys:
                            if k in params:
                                params[k] = end_val
                        for k in year_keys:
                            if k in params:
                                params[k] = str(TARGET_YEAR)

                        # 某些站点需要时间戳
                        if 'timeStamp' in params and not params['timeStamp']:
                            params['timeStamp'] = '1'

                        if method == 'post':
                            logger.info(f"[站内检索][FORM][POST] url={form_url} params={params}")
                            res = self.session.post(form_url, data=params, timeout=TIMEOUT, allow_redirects=True)
                        else:
                            logger.info(f"[站内检索][FORM][GET] url={form_url} params={params}")
                            res = self.session.get(form_url, params=params, timeout=TIMEOUT, allow_redirects=True)
                        if res.status_code == 200:
                            start_url = res.url
                            if start_url not in tried_urls:
                                tried_urls.add(start_url)
                                found = self.parse_search_results(start_url, city_name=city)
                                logger.info(f"[站内检索][FORM] 命中结果 {len(found)} 条 -> {start_url}")
                                reports.extend(found)
                    except Exception:
                        continue

            # 2) 常见搜索路径（GET参数）
            common_search_paths = [
                '/search', '/search.html', '/s', '/so', '/so.html', '/ss', '/site/search'
            ]
            for path in common_search_paths:
                search_url = urljoin(base_url, path)
                for param in param_candidates:
                    for kw in keywords:
                        try:
                            req_params = {param: kw}
                            # 同样尝试加入常见的时间窗口参数（如果该端点支持）
                            for k in ['startTime', 'start_time', 'stime', 'startDate', 'start_date', 'from', 'fromDate']:
                                req_params.setdefault(k, f"{TARGET_YEAR}-01-01 00:00:00")
                            for k in ['endTime', 'end_time', 'etime', 'endDate', 'end_date', 'to', 'toDate']:
                                req_params.setdefault(k, f"{TARGET_YEAR}-12-31 23:59:59")
                            for k in ['year', 'yearStr', 'time', 'sj']:
                                req_params.setdefault(k, str(TARGET_YEAR))

                            logger.info(f"[站内检索][COMMON][GET] url={search_url} params={req_params}")
                            res = self.session.get(search_url, params=req_params, timeout=TIMEOUT, allow_redirects=True)
                            if res.status_code == 200:
                                start_url = res.url
                                if start_url not in tried_urls:
                                    tried_urls.add(start_url)
                                    found = self.parse_search_results(start_url, city_name=city)
                                    logger.info(f"[站内检索][COMMON] 命中结果 {len(found)} 条 -> {start_url}")
                                    reports.extend(found)
                        except Exception:
                            continue

        except Exception as e:
            logger.debug(f"站内搜索失败: {e}")

        return reports

    def search_finance_reports(self, base_url: str, city: str) -> List[Dict]:
        """
        搜索财政报告链接：不依赖固定路径，先在站点内检索“公开/政务公开/财政公开”等栏目，
        再在这些栏目页内按 决算+目标年份+层级（本级/本市/城市名）过滤，完整遍历列表分页。
        """
        reports = []

        try:
            # 公开类栏目关键词
            public_keywords = ["公开", "信息公开", "政务公开", "政府信息公开", "财政信息公开", "财政公开"]

            def same_domain(url_a: str, url_b: str) -> bool:
                try:
                    pa = urlparse(url_a)
                    pb = urlparse(url_b)
                    return pa.netloc == pb.netloc
                except Exception:
                    return False

            # Step1: 在首页收集“公开”相关栏目链接（含一层扩展）
            candidate_section_urls = set()
            visited_for_sections = set()

            def collect_sections(from_url: str):
                try:
                    if from_url in visited_for_sections:
                        return
                    visited_for_sections.add(from_url)
                    resp = self.session.get(from_url, timeout=TIMEOUT)
                    if resp.status_code != 200:
                        return
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for a in soup.find_all('a', href=True):
                        href = a.get('href', '')
                        title = a.get_text().strip()
                        if not href:
                            continue
                        full_url = urljoin(from_url, href)
                        text_all = f"{title} {href}"
                        if any(pk in text_all for pk in public_keywords) and same_domain(base_url, full_url):
                            candidate_section_urls.add(full_url)
                except Exception as ex:
                    logger.debug(f"收集公开栏目失败 {from_url}: {ex}")

            # 从首页开始
            collect_sections(base_url)

            # 对已收集栏目做一层扩展收集（避免漏掉次级栏目）
            for url in list(candidate_section_urls)[:50]:  # 限制扩展数量，避免全站爬爆
                collect_sections(url)

            # 至少包含首页作为起始检索点
            candidate_section_urls.add(base_url)

            logger.info(f"{city}: 收集到 {len(candidate_section_urls)} 个公开相关栏目起点，开始检索决算链接…")

            # Step2: 在每个栏目页内，使用现有分页解析逻辑提取满足条件的链接
            added = set()
            for start_url in candidate_section_urls:
                try:
                    page_reports = self.parse_search_results(start_url, city_name=city)
                    for r in page_reports:
                        key = r.get('url')
                        if key and key not in added:
                            # 标记该链接来源于公开栏目，用于附件下载放宽策略
                            r['from_public_section'] = True
                            reports.append(r)
                            added.add(key)
                except Exception as ex:
                    logger.debug(f"解析栏目失败 {start_url}: {ex}")

            # 若仍未找到则对公开类栏目做有限深度的暴力遍历
            if not reports and candidate_section_urls:
                logger.info(f"{city}: 站内检索仍未命中，开始对公开栏目暴力遍历（有限深度）…")
                from collections import deque
                queue = deque()
                visited = set()
                max_pages = 120  # 上限，防止爬爆
                depth_limit = 2  # 栏目内两层深度

                for u in candidate_section_urls:
                    queue.append((u, 0))

                while queue and len(visited) < max_pages:
                    current_url, depth = queue.popleft()
                    if current_url in visited:
                        continue
                    visited.add(current_url)

                    try:
                        resp = self.session.get(current_url, timeout=TIMEOUT)
                        if resp.status_code != 200:
                            continue
                        soup = BeautifulSoup(resp.text, 'html.parser')

                        # 1) 在当前页尝试直接匹配决算链接
                        links = soup.find_all('a', href=True)
                        page_added = 0
                        for a in links:
                            href = a.get('href', '')
                            title = a.get_text().strip()
                            if not href:
                                continue
                            full = urljoin(current_url, href)
                            text_all = f"{title} {href}"
                            if self.matches_keywords(text_all, city_name=city):
                                if full not in added:
                                    reports.append({'title': title or href.split('/')[-1], 'url': full, 'from_public_section': True})
                                    added.add(full)
                                    page_added += 1

                            # 2) 文件直链也必须满足关键字规则
                            if any(full.lower().endswith(ext) for ext in TARGET_FILE_TYPES):
                                if self.matches_keywords(text_all, city_name=city):
                                    if full not in added:
                                        reports.append({'title': title or href.split('/')[-1], 'url': full, 'from_public_section': True})
                                        added.add(full)
                                        page_added += 1

                        # 3) 控制拓展到下一层
                        if depth < depth_limit:
                            for a in links:
                                href = a.get('href', '')
                                if not href:
                                    continue
                                nxt = urljoin(current_url, href)
                                if same_domain(base_url, nxt) and (nxt not in visited):
                                    queue.append((nxt, depth + 1))

                        if page_added > 0:
                            logger.info(f"{city}: 暴力遍历在 {current_url} 捕获 {page_added} 个候选")

                    except Exception as ex:
                        logger.debug(f"暴力遍历失败 {current_url}: {ex}")

        except Exception as e:
            logger.error(f"搜索 {city} 财政报告失败: {e}")

        return reports
    
    def extract_pdf_links(self, page_url: str, city_name: str, download_all: bool = False) -> List[Dict]:
        """
        从页面中提取符合条件的文件链接（按目标年份与层级过滤）
        """
        pdf_links = []
        
        try:
            response = self.session.get(page_url, timeout=TIMEOUT)
            if response.status_code != 200:
                logger.warning(f"无法访问页面 {page_url}，状态码: {response.status_code}")
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找所有链接
            links = soup.find_all('a', href=True)
            
            # 也查找iframe中的内容
            iframes = soup.find_all('iframe', src=True)
            for iframe in iframes:
                iframe_src = iframe.get('src')
                if not iframe_src: continue
                
                try:
                    iframe_url = urljoin(page_url, iframe_src)
                    # 检查iframe src本身是否是文件
                    if any(iframe_url.lower().endswith(ext) for ext in TARGET_FILE_TYPES):
                        text_all = f"iframe_content {iframe_src}"
                        if download_all or self.matches_keywords(text_all, city_name=city_name):
                            pdf_links.append({
                                'title': 'iframe_content',
                                'url': iframe_url
                            })
                            continue

                    # 解析iframe内部
                    iframe_response = self.session.get(iframe_url, timeout=TIMEOUT)
                    if iframe_response.status_code == 200:
                        iframe_soup = BeautifulSoup(iframe_response.content, 'html.parser')
                        links.extend(iframe_soup.find_all('a', href=True))
                except requests.RequestException as e:
                    logger.warning(f"无法访问或解析iframe内容: {iframe_src}, Error: {e}")

            # 统一处理收集到的链接
            processed_urls = {p['url'] for p in pdf_links}
            for link in links:
                href = link.get('href', '')
                if not any(href.lower().endswith(ext) for ext in TARGET_FILE_TYPES):
                    continue
                
                try:
                    full_url = urljoin(page_url, href)
                    if full_url in processed_urls:
                        continue
                    
                    title = link.get_text(strip=True)
                    if not title:
                        from urllib.parse import unquote
                        title = unquote(href.split('/')[-1])

                    text_all = f"{title} {href}"
                    if download_all or self.matches_keywords(text_all, city_name=city_name):
                        pdf_links.append({'url': full_url, 'title': title})
                        processed_urls.add(full_url)
                except Exception:
                    logger.warning(f"解析链接失败: {href}")

        except Exception as e:
            logger.error(f"提取PDF链接失败 {page_url}: {e}")
        
        return pdf_links
    
    def download_file(self, url: str, save_path: str) -> bool:
        """
        下载文件（带重试机制和智能文件名处理）
        """
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, timeout=TIMEOUT, stream=True)
                if response.status_code == 200:
                    # 检查URL是否包含文件扩展名
                    url_lower = url.lower()
                    has_file_extension = any(url_lower.endswith(ext) for ext in TARGET_FILE_TYPES)
                    
                    # 检查内容类型
                    content_type = response.headers.get('Content-Type', '').lower()
                    is_html = 'text/html' in content_type
                    
                    # 如果URL包含文件扩展名，即使Content-Type是HTML也要尝试下载
                    if is_html and not url_lower.endswith('.html'):
                        if has_file_extension:
                            logger.info(f"URL包含文件扩展名，尽管Content-Type是HTML，仍尝试下载: {url}")
                        else:
                            logger.warning(f"URL返回的是HTML而非文件，且URL不包含文件扩展名: {url}")
                            return False

                    # 智能获取文件名，如果Content-Disposition存在，则优先使用
                    final_save_path = save_path
                    content_disposition = response.headers.get('Content-Disposition')
                    if content_disposition:
                        # 保留我们传入的 save_path 命名，不再用响应头覆盖
                        # 如需后续扩展，可仅用于推断扩展名而非重命名
                        pass

                    os.makedirs(os.path.dirname(final_save_path), exist_ok=True)
                    
                    # 检查文件大小
                    total_size = int(response.headers.get('Content-Length', 0))
                    
                    with open(final_save_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    # 验证文件大小
                    if total_size > 0 and os.path.getsize(final_save_path) != total_size:
                        logger.warning(f"文件大小不匹配: {url}")
                        if attempt < MAX_RETRIES - 1:
                            continue
                        return False
                    
                    # 验证文件不为空
                    if os.path.getsize(final_save_path) == 0:
                        logger.warning(f"下载的文件为空: {url}")
                        os.remove(final_save_path)
                        if attempt < MAX_RETRIES - 1:
                            continue
                        return False
                    
                    return True
                elif response.status_code == 404:
                    logger.warning(f"文件不存在(404): {url}")
                    return False
                else:
                    logger.warning(f"下载失败，状态码: {response.status_code}, URL: {url}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(2 * (attempt + 1))  # 递增延迟
                        continue
                    return False
                    
            except requests.exceptions.Timeout:
                logger.warning(f"下载超时 (尝试 {attempt + 1}/{MAX_RETRIES}): {url}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return False
            except Exception as e:
                logger.error(f"下载文件失败 (尝试 {attempt + 1}/{MAX_RETRIES}) {url}: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                return False
        
        return False

    def write_source_info(self, file_path: str, source_page_url: str, file_url: str, title: str, city: str):
        """
        在下载目录写入同名的来源说明txt，记录来源页面与直链，便于追溯。
        """
        try:
            base = os.path.splitext(file_path)[0]
            txt_path = base + ".source.txt"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(f"城市: {city}\n")
                f.write(f"标题: {title}\n")
                f.write(f"来源页面: {source_page_url}\n")
                f.write(f"文件直链: {file_url}\n")
                f.write(f"保存文件: {os.path.basename(file_path)}\n")
                f.write(f"时间: {datetime.now().isoformat()}\n")
        except Exception as e:
            logger.debug(f"写入来源说明失败 {file_path}: {e}")
    
    def crawl_city(self, city: str) -> Dict:
        """
        爬取单个城市的财政报告
        """
        logger.info(f"开始爬取 {city} 的财政报告...")
        
        result = {
            'city': city,
            'success': False,
            'website': None,
            'reports_found': 0,
            'files_downloaded': 0,
            'errors': []
        }
        
        try:
            # 1. 搜索政府网站
            website_url = self.search_government_website(city)
            if not website_url:
                result['errors'].append("未找到政府网站")
                logger.warning(f"{city}: 未找到政府网站")
                return result
            
            result['website'] = website_url
            logger.info(f"{city}: 找到政府网站 {website_url}")
            
            # 2. 搜索财政报告（直接返回符合条件的链接列表）
            reports = self.search_finance_reports(website_url, city)
            if not reports:
                logger.warning(f"{city}: 未能找到符合条件的决算公开链接。")

            result['reports_found'] = len(reports)
            
            if not reports:
                result['errors'].append("未找到财政报告")
                logger.warning(f"{city}: 未找到财政报告")
                return result
            
            logger.info(f"{city}: 找到 {len(reports)} 个报告链接")
            
            # 3. 提取并下载文件
            city_dir = os.path.join(DOWNLOAD_DIR, city)
            downloaded_count = 0
            
            for report in reports:
                try:
                    # 提取页面中的文件链接
                    # 如果该链接来自公开栏目，则下载页面中的所有附件（不再按关键词过滤）
                    download_all = bool(report.get('from_public_section'))
                    pdf_links = self.extract_pdf_links(report['url'], city_name=city, download_all=download_all)
                    
                    # 如果没有直接找到PDF，尝试下载页面本身
                    if not pdf_links:
                        # 检查报告URL本身是否是文件
                        if any(report['url'].lower().endswith(ext) for ext in TARGET_FILE_TYPES):
                            # 直链也必须通过关键词过滤
                            if download_all:
                                pdf_links = [{'title': report.get('title', '') or report['url'].split('/')[-1], 'url': report['url']}]
                            else:
                                text_all = f"{report.get('title', '')} {report['url']}"
                                if self.matches_keywords(text_all, city_name=city):
                                    pdf_links = [{'title': report['title'], 'url': report['url']}]
                    
                    # 下载文件
                    for pdf_link in pdf_links:
                        from urllib.parse import unquote
                        file_ext = Path(pdf_link['url']).suffix or '.pdf'
                        # 避免乱码：尝试unquote再清理非法字符
                        base_title = unquote(pdf_link.get('title', '') or '')
                        safe_title = re.sub(r'[<>:"/\\|?*]', '_', base_title).strip() or '附件'
                        # 命名规则：2024年{xx市}+附件名
                        city_label = city if city.endswith('市') else f"{city}市"
                        filename = f"{TARGET_YEAR}年{city_label}{safe_title}{file_ext}"
                        save_path = os.path.join(city_dir, filename)
                        
                        # 检查是否已下载（检查文件大小，避免下载空文件）
                        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                            # 仍写入/更新来源说明
                            self.write_source_info(save_path, report['url'], pdf_link['url'], pdf_link.get('title', filename), city)
                            logger.info(f"{city}: 文件已存在，跳过 {filename}")
                            downloaded_count += 1
                            continue
                        
                        if self.download_file(pdf_link['url'], save_path):
                            # 写入来源说明txt
                            self.write_source_info(save_path, report['url'], pdf_link['url'], pdf_link.get('title', filename), city)
                            downloaded_count += 1
                            logger.info(f"{city}: 下载成功 {filename}")
                            time.sleep(REQUEST_DELAY)
                        else:
                            result['errors'].append(f"下载失败: {filename}")
                            
                except Exception as e:
                    error_msg = f"处理报告失败 {report['title']}: {e}"
                    result['errors'].append(error_msg)
                    logger.error(f"{city}: {error_msg}")
            
            result['files_downloaded'] = downloaded_count
            result['success'] = downloaded_count > 0
            
            if result['success']:
                logger.info(f"{city}: 成功下载 {downloaded_count} 个文件")
            else:
                logger.warning(f"{city}: 未下载任何文件")
                
        except Exception as e:
            error_msg = f"爬取失败: {e}"
            result['errors'].append(error_msg)
            logger.error(f"{city}: {error_msg}")
        
        return result
    
    def save_progress(self, results: List[Dict]):
        """
        保存爬取进度
        """
        progress_file = os.path.join(DATA_DIR, 'progress.json')
        
        progress_data = {
            'last_update': datetime.now().isoformat(),
            'total_cities': len(CITIES),
            'results': results
        }
        
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    def run(self, test_mode: bool = False, test_cities: List[str] = None):
        """
        运行爬虫
        
        Args:
            test_mode: 是否为测试模式
            test_cities: 测试模式下的城市列表，如果为None则使用默认测试城市
        """
        if test_mode:
            if test_cities is None:
                # 默认测试几个城市
                test_cities = ["赣州市", "北京市", "上海市", "杭州市", "深圳市"]
            cities_to_crawl = test_cities
            logger.info(f"测试模式：爬取 {len(cities_to_crawl)} 个城市的财政报告")
            logger.info(f"测试城市: {', '.join(cities_to_crawl)}")
        else:
            cities_to_crawl = CITIES
            logger.info(f"开始爬取 {len(cities_to_crawl)} 个地级行政区划的财政报告（目标年份: {TARGET_YEAR}）")
        
        results = []
        
        # 加载已有进度
        progress_file = os.path.join(DATA_DIR, 'progress.json')
        existing_results = {}
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
                    # 只在非测试模式下使用已有进度
                    if not test_mode:
                        existing_results = {r['city']: r for r in progress_data.get('results', [])}
                        completed_cities = {city for city, r in existing_results.items() if r.get('success')}
                        logger.info(f"已找到 {len(completed_cities)} 个已完成的城市")
                    else:
                        completed_cities = set()
            except Exception as e:
                logger.warning(f"加载进度文件失败: {e}")
                completed_cities = set()
        else:
            completed_cities = set()
        
        # 爬取每个城市
        if test_mode:
            for city in tqdm(cities_to_crawl, desc="爬取进度"):
                result = self.crawl_city(city)
                results.append(result)
                time.sleep(REQUEST_DELAY)
        else:
            # 使用线程池并发爬取以充分利用CPU/内存
            from concurrent.futures import ThreadPoolExecutor, as_completed
            futures = {}
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                for city in cities_to_crawl:
                    if city in completed_cities:
                        logger.info(f"{city}: 已爬取，跳过")
                        if city in existing_results:
                            results.append(existing_results[city])
                        continue
                    futures[executor.submit(self.crawl_city, city)] = city

                done_count = 0
                for future in as_completed(futures):
                    city = futures[future]
                    try:
                        res = future.result()
                        results.append(res)
                    except Exception as e:
                        logger.error(f"{city}: 并发任务失败: {e}")
                    finally:
                        done_count += 1
                        # 按频率保存进度
                        if done_count % SAVE_PROGRESS_EVERY == 0:
                            self.save_progress(results)
        
        # 统计结果
        success_count = sum(1 for r in results if r['success'])
        total_files = sum(r['files_downloaded'] for r in results)
        failed_count = len(cities_to_crawl) - success_count
        
        logger.info(f"爬取完成！成功: {success_count}/{len(cities_to_crawl)}, 失败: {failed_count}, 总下载文件数: {total_files}")
        
        # 保存最终结果
        if test_mode:
            summary_file = os.path.join(DATA_DIR, 'test_summary.json')
        else:
            summary_file = os.path.join(DATA_DIR, 'summary.json')
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump({
                'target_year': TARGET_YEAR,
                'test_mode': test_mode,
                'total_cities': len(cities_to_crawl),
                'success_count': success_count,
                'failed_count': failed_count,
                'total_files': total_files,
                'results': results
            }, f, ensure_ascii=False, indent=2)
        
        return results


if __name__ == "__main__":
    spider = FinanceReportSpider()
    spider.run()

