"""
城市站点映射（优先使用），可按需补充与修正。

结构：
CITY_SITE_OVERRIDES = {
    "城市名": {
        "gov": "市政府网站根域",
        "fin": "市财政局网站根域（若有）"
    },
    ...
}
"""

CITY_SITE_OVERRIDES = {
    # 直辖市
    "北京市": {"gov": "https://www.beijing.gov.cn", "fin": "https://czj.beijing.gov.cn"},
    "上海市": {"gov": "https://www.shanghai.gov.cn", "fin": "https://czj.shanghai.gov.cn"},
    "天津市": {"gov": "https://www.tianjin.gov.cn", "fin": "https://cz.tj.gov.cn"},
    "重庆市": {"gov": "https://www.cq.gov.cn", "fin": "https://czj.cq.gov.cn"},

    # 部分示例省会/副省级城市（其余城市可逐步补全或运行时自动生成）
    "广州市": {"gov": "https://www.gz.gov.cn", "fin": "https://czj.gz.gov.cn"},
    "深圳市": {"gov": "http://www.shenzhen.gov.cn", "fin": "https://czj.sz.gov.cn"},
    "杭州市": {"gov": "https://www.hangzhou.gov.cn", "fin": "https://czj.hangzhou.gov.cn"},
    "南京市": {"gov": "https://www.nanjing.gov.cn", "fin": "https://czj.nanjing.gov.cn"},
    "武汉市": {"gov": "https://www.wuhan.gov.cn", "fin": "https://czj.wuhan.gov.cn"},
    "成都市": {"gov": "https://www.chengdu.gov.cn", "fin": "https://czj.chengdu.gov.cn"},
    "西安市": {"gov": "http://www.xa.gov.cn", "fin": "http://czj.xa.gov.cn"},
    "合肥市": {"gov": "https://www.hefei.gov.cn", "fin": "https://cz.hefei.gov.cn"},
    "济南市": {"gov": "http://www.jinan.gov.cn", "fin": "http://jnswj.jinan.gov.cn"},
    "青岛市": {"gov": "http://www.qingdao.gov.cn", "fin": "http://czj.qingdao.gov.cn"},

    # 示例：赣州
    "赣州市": {"gov": "https://www.ganzhou.gov.cn", "fin": "https://czj.ganzhou.gov.cn"},
}


