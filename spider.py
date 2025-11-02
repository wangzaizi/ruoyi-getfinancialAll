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
        
    def search_government_website(self, city: str) -> Optional[str]:
        """
        搜索政府网站URL
        """
        try:
            # 首先检查已知网站映射
            if city in self.known_websites:
                known_url = self.known_websites[city]
                try:
                    response = self.session.head(known_url, timeout=5, allow_redirects=True)
                    if response.status_code in [200, 301, 302]:
                        logger.info(f"{city}: 使用已知网站 {response.url}")
                        return response.url
                except:
                    logger.debug(f"{city}: 已知网站 {known_url} 无法访问")
            
            # 处理城市名称，生成可能的域名
            city_name = city.replace("市", "").replace("地区", "").replace("自治州", "").replace("盟", "").replace("自治区", "")
            
            # 特殊城市名称处理
            city_name_mappings = {
                "北京": "beijing",
                "上海": "shanghai",
                "天津": "tianjin",
                "重庆": "chongqing",
                "赣州": "ganzhou",
                "杭州": "hangzhou",
                "深圳": "shenzhen",
            }
            
            # 生成可能的URL列表
            possible_urls = []
            
            # 标准格式
            possible_urls.extend([
                f"https://www.{city_name}.gov.cn",
                f"http://www.{city_name}.gov.cn",
                f"https://{city_name}.gov.cn",
                f"http://{city_name}.gov.cn",
            ])
            
            # 如果有拼音映射，添加拼音版本
            pinyin_name = city_name_mappings.get(city_name)
            if pinyin_name:
                possible_urls.extend([
                    f"https://www.{pinyin_name}.gov.cn",
                    f"http://www.{pinyin_name}.gov.cn",
                ])
            
            # 直接尝试访问（先验证URL是否有效）
            for url in possible_urls:
                try:
                    response = self.session.head(url, timeout=5, allow_redirects=True)
                    if response.status_code in [200, 301, 302]:
                        final_url = response.url if response.url != url else url
                        logger.info(f"{city}: 直接访问成功 {final_url}")
                        return final_url
                except Exception as e:
                    logger.debug(f"{city}: 尝试 {url} 失败: {e}")
                    continue
            
            # 如果直接访问失败，使用百度搜索
            logger.info(f"{city}: 开始使用百度搜索...")
            search_queries = [
                f"{city} 政府网站",
                f"{city} 人民政府",
                f"{city} 官网",
            ]
            
            for search_query in search_queries:
                try:
                    search_url = f"https://www.baidu.com/s?wd={quote(search_query)}"
                    response = self.session.get(search_url, timeout=TIMEOUT)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 查找所有链接
                        links = soup.find_all('a', href=True)
                        
                        for link in links:
                            href = link.get('href', '')
                            link_text = link.get_text().strip()
                            
                            # 检查是否包含.gov.cn
                            if '.gov.cn' in href:
                                # 提取真实URL
                                # 百度搜索结果的链接格式可能是 /link?url=...
                                if '/link?url=' in href:
                                    # 尝试提取真实URL
                                    try:
                                        match = re.search(r'url=([^&]+)', href)
                                        if match:
                                            decoded_url = quote(match.group(1), safe='')
                                            # 再次尝试提取
                                            if '.gov.cn' in decoded_url:
                                                real_url = match.group(1)
                                                if real_url.startswith('http'):
                                                    logger.info(f"{city}: 从百度搜索结果找到 {real_url}")
                                                    return real_url
                                    except:
                                        pass
                                
                                # 直接提取http(s)://...格式的URL
                                url_match = re.search(r'(https?://[^\s"\'<>]+\.gov\.cn[^\s"\'<>]*)', href)
                                if url_match:
                                    found_url = url_match.group(1)
                                    logger.info(f"{city}: 从百度搜索结果提取 {found_url}")
                                    return found_url
                            
                            # 也检查链接文本中是否包含.gov.cn
                            if '.gov.cn' in link_text:
                                url_match = re.search(r'(https?://[^\s"\'<>]+\.gov\.cn[^\s"\'<>]*)', link_text)
                                if url_match:
                                    found_url = url_match.group(1)
                                    logger.info(f"{city}: 从链接文本找到 {found_url}")
                                    return found_url
                        
                        # 查找页面内容中的.gov.cn链接
                        page_text = response.text
                        gov_links = re.findall(r'(https?://[^\s"\'<>]+\.gov\.cn[^\s"\'<>]*)', page_text)
                        for gov_link in gov_links[:5]:  # 只检查前5个
                            if city_name in gov_link or city in gov_link:
                                logger.info(f"{city}: 从页面内容找到 {gov_link}")
                                return gov_link
                                
                except Exception as e:
                    logger.debug(f"{city}: 百度搜索查询 '{search_query}' 失败: {e}")
                    continue
            
            # 如果以上都失败，尝试已知的常见政府网站域名格式
            known_patterns = [
                f"https://www.{city_name}.gov.cn",
                f"http://www.{city_name}.gov.cn",
                f"https://{city_name.lower()}.gov.cn",
                f"http://{city_name.lower()}.gov.cn",
            ]
            
            if pinyin_name:
                known_patterns.extend([
                    f"https://www.{pinyin_name}.gov.cn",
                    f"http://www.{pinyin_name}.gov.cn",
                ])
            
            logger.warning(f"{city}: 所有搜索方法都失败，未找到政府网站")
                    
        except Exception as e:
            logger.error(f"搜索 {city} 政府网站失败: {e}")
        
        return None
    
    def extract_all_form_fields(self, form) -> Dict:
        """
        提取表单中的所有字段及其值
        返回字段字典: {field_name: field_value}
        """
        fields = {}
        
        # 提取所有input字段
        for input_elem in form.find_all('input'):
            input_type = input_elem.get('type', 'text').lower()
            name = input_elem.get('name')
            value = input_elem.get('value', '')
            
            if name:
                # 跳过submit和button类型的input
                if input_type not in ['submit', 'button', 'image']:
                    fields[name] = value
        
        # 提取所有select字段
        for select_elem in form.find_all('select'):
            name = select_elem.get('name')
            if name:
                # 获取默认选中的option
                selected_option = select_elem.find('option', selected=True)
                if selected_option:
                    fields[name] = selected_option.get('value', '')
                else:
                    # 如果没有选中的，取第一个option
                    first_option = select_elem.find('option')
                    if first_option:
                        fields[name] = first_option.get('value', '')
                    else:
                        fields[name] = ''
        
        # 提取所有textarea字段
        for textarea_elem in form.find_all('textarea'):
            name = textarea_elem.get('name')
            if name:
                fields[name] = textarea_elem.get_text().strip()
        
        return fields
    
    def find_search_form(self, page_url: str) -> Optional[Dict]:
        """
        在页面中查找搜索表单
        返回: {'action': 表单提交URL, 'method': 提交方法, 'input_name': 输入框名称, 
               'form': form元素, 'all_fields': 所有表单字段, 'page_url': 页面URL}
        """
        try:
            response = self.session.get(page_url, timeout=TIMEOUT)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找所有form标签
            forms = soup.find_all('form')
            
            for form in forms:
                # 查找搜索输入框（常见的name/id属性）
                search_inputs = form.find_all(['input', 'textarea'], {
                    'type': ['text', 'search', None],
                    'name': re.compile(r'(q|keyword|search|word|query|key|wd|text|input|searchWord)', re.I)
                })
                
                # 如果没找到，尝试通过其他属性查找
                if not search_inputs:
                    search_inputs = form.find_all('input', {
                        'id': re.compile(r'(q|keyword|search|word|query|key|wd|text|input|searchInput|searchWord)', re.I)
                    })
                
                # 或者查找包含"搜索"、"search"等关键词的输入框
                if not search_inputs:
                    for input_elem in form.find_all(['input', 'textarea']):
                        placeholder = input_elem.get('placeholder', '').lower()
                        name = input_elem.get('name', '').lower()
                        input_id = input_elem.get('id', '').lower()
                        if any(kw in (placeholder + name + input_id) for kw in ['搜索', 'search', '查询', 'query', 'word']):
                            search_inputs = [input_elem]
                            break
                
                if search_inputs:
                    input_elem = search_inputs[0]
                    input_name = input_elem.get('name') or input_elem.get('id') or 'q'
                    
                    # 获取表单action（提交URL）
                    action = form.get('action', '')
                    if not action:
                        action = page_url
                    else:
                        action = urljoin(page_url, action)
                    
                    # 获取提交方法
                    method = form.get('method', 'get').lower()
                    
                    # 提取所有表单字段
                    all_fields = self.extract_all_form_fields(form)
                    
                    logger.info(f"找到搜索表单: action={action}, method={method}, input_name={input_name}, 共{len(all_fields)}个字段")
                    
                    return {
                        'action': action,
                        'method': method,
                        'input_name': input_name,
                        'form': form,
                        'all_fields': all_fields,
                        'page_url': page_url
                    }
            
            return None
            
        except Exception as e:
            logger.debug(f"查找搜索表单失败 {page_url}: {e}")
            return None
    
    def do_native_form_submit(self, search_info: Dict, test_keyword: str = "决算") -> Optional[Dict]:
        """
        进行一次真实的表单提交，捕获所有实际使用的参数
        返回: {'success_url': 成功的结果URL, 'params_template': 参数模板字典, 'method': 实际使用的方法}
        """
        try:
            action = search_info['action']
            declared_method = search_info['method']
            input_name = search_info['input_name']
            all_fields = search_info.get('all_fields', {})
            
            logger.info(f"执行原生表单提交测试，关键词: {test_keyword}")
            
            # 构建完整的表单数据（使用所有字段的默认值，只替换搜索关键词）
            form_data = all_fields.copy()
            form_data[input_name] = test_keyword
            
            # 尝试GET方法
            logger.info("尝试GET方法进行原生提交...")
            try:
                get_response = self.session.get(action, params=form_data, timeout=TIMEOUT, allow_redirects=True)
                if get_response.status_code == 200:
                    # 检查响应是否包含搜索结果（简单检查：包含关键词或结果相关的内容）
                    response_text = get_response.text.lower()
                    if (test_keyword in response_text or 
                        '结果' in response_text or 
                        'search' in response_text or
                        len(get_response.text) > 1000):  # 有足够的内容
                        logger.info(f"GET方法原生提交成功，URL: {get_response.url}")
                        # 从URL中提取参数（如果是GET）
                        parsed_url = urlparse(get_response.url)
                        actual_params = dict(parse_qsl(parsed_url.query))
                        return {
                            'success_url': get_response.url,
                            'params_template': actual_params,
                            'method': 'get',
                            'response_text_length': len(get_response.text)
                        }
            except Exception as e:
                logger.debug(f"GET方法原生提交失败: {e}")
            
            # 尝试POST方法
            logger.info("尝试POST方法进行原生提交...")
            try:
                post_response = self.session.post(action, data=form_data, timeout=TIMEOUT, allow_redirects=True)
                if post_response.status_code == 200:
                    response_text = post_response.text.lower()
                    if (test_keyword in response_text or 
                        '结果' in response_text or 
                        'search' in response_text or
                        len(post_response.text) > 1000):
                        logger.info(f"POST方法原生提交成功，URL: {post_response.url}")
                        # POST的参数就是提交的form_data
                        return {
                            'success_url': post_response.url,
                            'params_template': form_data.copy(),
                            'method': 'post',
                            'response_text_length': len(post_response.text)
                        }
            except Exception as e:
                logger.debug(f"POST方法原生提交失败: {e}")
            
            logger.warning("原生表单提交测试失败（GET和POST都失败）")
            return None
            
        except Exception as e:
            logger.error(f"执行原生表单提交失败: {e}")
            return None
    
    def submit_search(self, search_info: Dict, search_keyword: str, method_override: Optional[str] = None, params_template: Optional[Dict] = None) -> Optional[str]:
        """
        提交搜索请求
        返回搜索结果页面URL或None
        
        Args:
            search_info: 搜索表单信息
            search_keyword: 搜索关键词
            method_override: 强制使用的方法 ('get' 或 'post')，如果为None则使用表单声明的method
            params_template: 参数模板（来自原生提交的成功参数）
        """
        try:
            action = search_info['action']
            method = method_override or search_info['method']
            input_name = search_info['input_name']
            
            # 如果提供了参数模板，使用模板（只替换搜索关键词）
            if params_template:
                params = params_template.copy()
                params[input_name] = search_keyword
                
                # 更新一些可能需要动态更新的字段（如时间戳）
                from datetime import datetime, timedelta
                if 'startTime' in params:
                    # 设置开始时间为目标年份的开始
                    params['startTime'] = f"{TARGET_YEAR}-01-01 00:00:00"
                if 'endTime' in params:
                    # 设置结束时间为当前或目标年份的结束
                    params['endTime'] = f"{TARGET_YEAR}-12-31 23:59:59"
                if 'timeStamp' in params:
                    # 更新时间戳
                    params['timeStamp'] = str(int(time.time()))
            else:
                # 没有模板，使用默认方式
                all_fields = search_info.get('all_fields', {})
                params = all_fields.copy()
                params[input_name] = search_keyword
            
            if method == 'get':
                response = self.session.get(action, params=params, timeout=TIMEOUT, allow_redirects=True)
            else:
                response = self.session.post(action, data=params, timeout=TIMEOUT, allow_redirects=True)
            
            if response.status_code == 200:
                # 验证响应是否包含搜索结果
                response_text = response.text.lower()
                if (search_keyword in response_text or 
                    '结果' in response_text or 
                    'search' in response_text or
                    len(response.text) > 1000):
                    return response.url
            
            logger.warning(f"搜索请求失败 ({method.upper()})，状态码: {response.status_code}")
            return None
                
        except Exception as e:
            logger.error(f"提交搜索请求失败 ({method_override or search_info['method']}): {e}")
            return None
    
    def submit_search_both_methods(self, search_info: Dict, search_keyword: str, params_template: Optional[Dict] = None) -> List[str]:
        """
        无论成功失败，都使用GET和POST两种方法提交搜索
        返回所有成功的结果URL列表
        
        Args:
            search_info: 搜索表单信息
            search_keyword: 搜索关键词
            params_template: 参数模板（如果有）
        """
        result_urls = []
        
        # 方法1: 尝试GET方法
        logger.info(f"尝试使用GET方法搜索: {search_keyword}")
        get_url = self.submit_search(search_info, search_keyword, method_override='get', params_template=params_template)
        if get_url:
            logger.info(f"GET方法成功，结果URL: {get_url}")
            result_urls.append(get_url)
        else:
            logger.info("GET方法未获得有效结果")
        
        # 方法2: 尝试POST方法（无论GET是否成功）
        logger.info(f"尝试使用POST方法搜索: {search_keyword}")
        post_url = self.submit_search(search_info, search_keyword, method_override='post', params_template=params_template)
        if post_url:
            logger.info(f"POST方法成功，结果URL: {post_url}")
            # 去重：如果POST的URL和GET的不同，才添加
            if post_url not in result_urls:
                result_urls.append(post_url)
        else:
            logger.info("POST方法未获得有效结果")
        
        if result_urls:
            logger.info(f"总共获得 {len(result_urls)} 个搜索结果URL (GET和POST合并)")
        else:
            logger.warning("GET和POST两种方法都未获得有效结果")
        
        return result_urls
    
    def matches_keywords(self, text: str, keyword: str) -> bool:
        """
        检查文本是否同时包含搜索关键词和年份
        不要求连续，不要求前后顺序
        """
        if not text:
            return False
        
        text_lower = text.lower()
        keyword_lower = keyword.lower()
        year_str = str(TARGET_YEAR)
        
        # 检查是否同时包含关键词和年份（不要求连续或顺序）
        has_keyword = keyword_lower in text_lower or any(kw.lower() in text_lower for kw in SEARCH_KEYWORDS)
        has_year = year_str in text
        
        return has_keyword and has_year
    
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
    
    def parse_search_results(self, results_page_url: str, search_keyword: str) -> List[Dict]:
        """
        解析搜索结果页面，提取相关链接
        要求结果同时包含搜索关键词（如"决算"）和年份（如"2024"），不要求连续或顺序
        支持分页，会遍历所有页面直到结尾
        """
        all_reports = []
        processed_pages = set()  # 用于避免重复处理同一页面
        current_page_url = results_page_url
        max_pages = 100  # 防止无限循环，最多遍历100页
        
        try:
            page_count = 0
            while current_page_url and page_count < max_pages:
                # 避免重复处理
                if current_page_url in processed_pages:
                    logger.info(f"页面已处理过，跳过: {current_page_url}")
                    break
                processed_pages.add(current_page_url)
                
                page_count += 1
                logger.info(f"解析搜索结果页面 {page_count}: {current_page_url}")
                
                response = self.session.get(current_page_url, timeout=TIMEOUT)
                if response.status_code != 200:
                    logger.warning(f"无法访问页面 {current_page_url}，状态码: {response.status_code}")
                    break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 常见的搜索结果容器选择器（用于记录日志）
                result_selectors = [
                    'div.result', 'div.search-result', 'div.result-item',
                    'li.result', 'li.search-item', 'div.list-item',
                    'ul.search-results li', 'div.content-list li',
                    'div.news-list li', 'ul.list li'
                ]
                
                # 检查是否找到特定容器（仅用于日志记录）
                for selector in result_selectors:
                    elements = soup.select(selector)
                    if elements:
                        logger.info(f"找到特定结果容器 {selector}，包含 {len(elements)} 个元素")
                        break
                
                # 无论如何，都要搜索页面中的所有链接
                all_links = soup.find_all('a', href=True)
                logger.info(f"页面 {page_count} 找到 {len(all_links)} 个链接，开始过滤...")
                
                processed_urls = set()  # 用于去重
                page_reports = []
                
                for link in all_links:
                    href = link.get('href', '')
                    title = link.get_text().strip()
                    
                    # 跳过无效链接
                    if not href or href.startswith('javascript:') or href.startswith('#'):
                        continue
                    
                    # 构建完整URL
                    try:
                        full_url = urljoin(current_page_url, href)
                    except:
                        continue
                    
                    # 去重
                    if full_url in processed_urls:
                        continue
                    processed_urls.add(full_url)
                    
                    # 获取链接周围的文本（包括父元素的文本）
                    link_text = title
                    parent = link.parent
                    if parent:
                        parent_text = parent.get_text().strip()
                        if parent_text and len(parent_text) > len(title):
                            link_text = parent_text
                    
                    # 获取完整的文本内容（标题 + URL + 周围文本）
                    combined_text = f"{title} {href} {link_text}"
                    
                    # 检查是否同时包含关键词和年份（不要求连续或顺序）
                    if self.matches_keywords(combined_text, search_keyword):
                        page_reports.append({
                            'title': title or href.split('/')[-1] or full_url.split('/')[-1],
                            'url': full_url,
                            'keyword': 'search_result'
                        })
                
                logger.info(f"页面 {page_count} 提取到 {len(page_reports)} 个相关链接")
                all_reports.extend(page_reports)
                
                # 查找下一页
                next_page_url = self.find_next_page_url(current_page_url, soup)
                if next_page_url:
                    logger.info(f"找到下一页: {next_page_url}")
                    current_page_url = next_page_url
                    time.sleep(REQUEST_DELAY)  # 延迟避免请求过快
                else:
                    logger.info(f"已到达最后一页（第 {page_count} 页）")
                    break
            
            logger.info(f"总共遍历了 {page_count} 页，提取到 {len(all_reports)} 个相关链接（同时包含'{search_keyword}'和'{TARGET_YEAR}'）")
            
        except Exception as e:
            logger.error(f"解析搜索结果失败 {results_page_url}: {e}")
        
        return all_reports
    
    def use_site_search(self, base_url: str, city: str) -> List[Dict]:
        """
        使用站内搜索功能查找财政报告
        """
        reports = []
        
        try:
            logger.info(f"{city}: 尝试使用站内搜索...")
            
            # 先在首页查找搜索表单
            search_form_info = self.find_search_form(base_url)
            
            # 如果首页没找到，尝试常见页面
            if not search_form_info:
                common_pages = ['/search', '/search.html', '/so', '/s']
                for page in common_pages:
                    page_url = urljoin(base_url, page)
                    search_form_info = self.find_search_form(page_url)
                    if search_form_info:
                        break
            
            if not search_form_info:
                logger.warning(f"{city}: 未找到搜索表单")
                return reports
            
            # 步骤1: 先进行一次原生表单提交，捕获参数模板
            logger.info(f"{city}: 执行原生表单提交测试...")
            native_result = self.do_native_form_submit(search_form_info, "决算")
            params_template = None
            if native_result:
                params_template = native_result.get('params_template')
                logger.info(f"{city}: 成功捕获参数模板，包含 {len(params_template)} 个参数")
                logger.debug(f"{city}: 参数模板: {params_template}")
            else:
                logger.warning(f"{city}: 原生表单提交测试失败，将使用默认参数")
            
            # 使用多个搜索关键词
            search_keywords = [
                f"决算",
                
            ]
            
            for keyword in search_keywords:
                logger.info(f"{city}: 搜索关键词: {keyword}")
                
                # 提交搜索（无论成功失败，都使用GET和POST两种方法，使用参数模板）
                results_urls = self.submit_search_both_methods(search_form_info, keyword, params_template=params_template)
                
                if not results_urls:
                    logger.warning(f"{city}: 搜索关键词 '{keyword}' 未获得结果（GET和POST都失败）")
                    continue
                
                # 解析所有搜索结果页面（GET和POST的结果都解析）
                for results_url in results_urls:
                    logger.info(f"{city}: 解析搜索结果页面: {results_url}")
                    found_reports = self.parse_search_results(results_url, keyword)
                    
                    # 去重添加
                    for report in found_reports:
                        if report['url'] not in [r['url'] for r in reports]:
                            reports.append(report)
                    
                    # 避免请求过快
                    time.sleep(REQUEST_DELAY)
            
        except Exception as e:
            logger.error(f"{city}: 站内搜索失败: {e}")
        
        return reports
    
    def search_finance_reports(self, base_url: str, city: str) -> List[Dict]:
        """
        搜索财政报告链接
        """
        reports = []
        
        try:
            # 方法1: 尝试多个可能的路径
            search_paths = [
                "/czj/",  # 财政局
                "/zfxxgk/",  # 政府信息公开
                "/czxxgk/",  # 财政信息公开
                "/zdlyxxgk/",  # 重点领域信息公开
                "/bmxxgk/czj/",  # 部门信息公开/财政局
                "/cz/",  # 财政
                "/czzx/",  # 财政中心
                "/czgk/",  # 财政公开
            ]
            
            for path in search_paths:
                try:
                    url = urljoin(base_url, path)
                    response = self.session.get(url, timeout=TIMEOUT)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        # 搜索包含关键词的链接
                        for keyword in SEARCH_KEYWORDS:
                            links = soup.find_all('a', href=True, string=re.compile(keyword))
                            for link in links:
                                href = link.get('href', '')
                                title = link.get_text().strip()
                                
                                # 检查是否包含目标年份
                                if str(TARGET_YEAR) in title or str(TARGET_YEAR) in href:
                                    full_url = urljoin(url, href)
                                    reports.append({
                                        'title': title,
                                        'url': full_url,
                                        'keyword': keyword
                                    })
                        
                        # 也搜索所有链接中包含关键词的
                        all_links = soup.find_all('a', href=True)
                        for link in all_links:
                            href = link.get('href', '')
                            title = link.get_text().strip()
                            
                            # 检查链接文本或URL中是否包含关键词和目标年份
                            if any(kw in title for kw in SEARCH_KEYWORDS) or any(kw in href for kw in SEARCH_KEYWORDS):
                                if str(TARGET_YEAR) in title or str(TARGET_YEAR) in href:
                                    full_url = urljoin(url, href)
                                    if full_url not in [r['url'] for r in reports]:
                                        reports.append({
                                            'title': title,
                                            'url': full_url,
                                            'keyword': 'general'
                                        })
                                        
                except Exception as e:
                    logger.debug(f"搜索路径 {path} 失败: {e}")
                    continue
            
            # 方法2: 如果没找到，尝试使用站内搜索
            if not reports:
                logger.info(f"{city}: 直接搜索未找到，尝试使用站内搜索...")
                search_reports = self.use_site_search(base_url, city)
                reports.extend(search_reports)
                    
        except Exception as e:
            logger.error(f"搜索 {city} 财政报告失败: {e}")
        
        return reports
    
    def extract_pdf_links(self, page_url: str) -> List[Dict]:
        """
        从页面中提取PDF链接
        """
        pdf_links = []
        
        try:
            response = self.session.get(page_url, timeout=TIMEOUT)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 查找所有链接
                links = soup.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    title = link.get_text().strip()
                    
                    # 检查是否是PDF或其他目标文件
                    if any(href.lower().endswith(ext) for ext in TARGET_FILE_TYPES):
                        full_url = urljoin(page_url, href)
                        pdf_links.append({
                            'title': title or href.split('/')[-1],
                            'url': full_url
                        })
                
                # 也查找iframe中的内容
                iframes = soup.find_all('iframe', src=True)
                for iframe in iframes:
                    iframe_src = urljoin(page_url, iframe.get('src', ''))
                    if any(iframe_src.lower().endswith(ext) for ext in TARGET_FILE_TYPES):
                        pdf_links.append({
                            'title': 'iframe_content',
                            'url': iframe_src
                        })
                        
        except Exception as e:
            logger.error(f"提取PDF链接失败 {page_url}: {e}")
        
        return pdf_links
    
    def download_file(self, url: str, save_path: str) -> bool:
        """
        下载文件（带重试机制）
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
                    # 因为有些服务器可能错误地设置了Content-Type
                    if is_html and not url_lower.endswith('.html'):
                        if has_file_extension:
                            logger.info(f"URL包含文件扩展名，尽管Content-Type是HTML，仍尝试下载: {url}")
                            # 继续下载
                        else:
                            logger.warning(f"URL返回的是HTML而非文件，且URL不包含文件扩展名: {url}")
                            return False
                    
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    
                    # 检查文件大小
                    total_size = int(response.headers.get('Content-Length', 0))
                    downloaded_size = 0
                    
                    with open(save_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded_size += len(chunk)
                    
                    # 验证文件大小
                    if total_size > 0 and os.path.getsize(save_path) != total_size:
                        logger.warning(f"文件大小不匹配: {url}")
                        if attempt < MAX_RETRIES - 1:
                            continue
                        return False
                    
                    # 验证文件不为空
                    if os.path.getsize(save_path) == 0:
                        logger.warning(f"下载的文件为空: {url}")
                        os.remove(save_path)
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
            
            # 2. 搜索财政报告
            reports = self.search_finance_reports(website_url, city)
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
                    # 提取页面中的PDF链接
                    pdf_links = self.extract_pdf_links(report['url'])
                    
                    # 如果没有直接找到PDF，尝试下载页面本身
                    if not pdf_links:
                        # 检查报告URL本身是否是文件
                        if any(report['url'].lower().endswith(ext) for ext in TARGET_FILE_TYPES):
                            pdf_links = [{'title': report['title'], 'url': report['url']}]
                    
                    # 下载文件
                    for pdf_link in pdf_links:
                        file_ext = Path(pdf_link['url']).suffix or '.pdf'
                        safe_title = re.sub(r'[<>:"/\\|?*]', '_', pdf_link['title'])
                        filename = f"{safe_title}{file_ext}"
                        save_path = os.path.join(city_dir, filename)
                        
                        # 检查是否已下载（检查文件大小，避免下载空文件）
                        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                            logger.info(f"{city}: 文件已存在，跳过 {filename}")
                            downloaded_count += 1
                            continue
                        
                        if self.download_file(pdf_link['url'], save_path):
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
        for city in tqdm(cities_to_crawl, desc="爬取进度"):
            # 检查是否已完成（非测试模式）
            if not test_mode and city in completed_cities:
                logger.info(f"{city}: 已爬取，跳过")
                if city in existing_results:
                    results.append(existing_results[city])
                continue
            
            result = self.crawl_city(city)
            results.append(result)
            
            # 保存进度
            if not test_mode:
                self.save_progress(results)
            
            # 延迟
            time.sleep(REQUEST_DELAY)
        
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

