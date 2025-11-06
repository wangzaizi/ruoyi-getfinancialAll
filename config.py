"""
配置文件
"""
import os

# 基础配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
LOG_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")

# 创建必要的目录
for directory in [DOWNLOAD_DIR, LOG_DIR, DATA_DIR]:
    os.makedirs(directory, exist_ok=True)

# 爬虫配置
CONCURRENT_REQUESTS = 5  # 并发请求数
REQUEST_DELAY = 2  # 请求延迟（秒）
TIMEOUT = 30  # 请求超时时间（秒）
MAX_RETRIES = 3  # 最大重试次数

# 报告年份
# 支持多年份目标（例如同时抓取 2024 与 2025）
# 兼容：保留 TARGET_YEAR 作为默认的“主年份”（取 TARGET_YEARS 中最大值）
TARGET_YEARS = [2024, 2025]
TARGET_YEAR = max(TARGET_YEARS)

# 显式屏蔽年份（用于排除旧年内容，如 2023）
NO_TARGET_YEARS = [2023]

# 搜索关键词
SEARCH_KEYWORDS = [
    "决算",
    "预算"
]

# 文件类型
TARGET_FILE_TYPES = [".pdf", ".doc", ".docx", ".xls", ".xlsx",".rar",".zip"]

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

