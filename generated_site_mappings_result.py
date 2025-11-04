"""
基于已生成的城市站点映射，构建带检索起点与过滤规则的城市配置：
- 在原有 CITY_SITE_OVERRIDES 基础上，为每个城市增加 urls（检索起点）与 filters（过滤条件）
- 暂不启用暴力遍历，但保留配置开关位（violent_fallback_enabled=False）

检索起点策略：
1) 从市政府(gov)与财政局(fin)根域出发，拼接常见“公开/财政/重点领域”等栏目路径
2) 结合用户提供的路径语义（政府信息公开/法定主动公开内容/预算决算/政府预算决算公开/2024年政府预算决算公开；
   政策>财政信息>财政预决算；政务公开>重点领域信息公开>财政资金>财政预决算及三公经费>市级政府财政预决算），
   归纳成一组常见路径集合进行起点拼接

过滤规则：统一要求 文本/URL 同时满足：
- 关键词：决算（必含）
- 年份：2024（必含，可在文本或URL）
- 层级：本级/本市/城市名（含“某某市”变体）至少命中一个
- 排除：部门/单位/街道/镇/乡（避免部门级决算）
"""

from typing import Dict, List
from urllib.parse import urljoin

# 选择最新的生成文件（你也可以改成固定导入指定文件）
from generated_site_mappings202511041549 import CITY_SITE_OVERRIDES as BASE_MAPPINGS


COMMON_SECTION_PATHS: List[str] = [
    # 政府信息公开/法定主动公开/财政（预算决算）
    "/zfxxgk/", "/zwgk/", "/xxgk/", "/gk/", "/gsgg/",
    "/zfxxgk/fdzdgknr/", "/zwgk/fdzdgknr/", "/xxgk/fdzdgknr/",
    "/zfxxgk/zdlyxxgk/", "/zwgk/zdlyxxgk/", "/zdlyxxgk/",
    # 财政专栏
    "/czxxgk/", "/czgk/", "/czzx/", "/cz/",
    # 部门信息公开中的财政局
    "/bmxxgk/czj/", "/bmxxgk/", "/bmxxgkml/czj/",
    # 重点领域财政资金
    "/zdlyxxgk/czzj/", "/zdlyxxgk/czxx/", "/zdlyxxgk/czzjxxgk/",
    # 预算/决算常见目录
    "/ysjs/", "/ys/", "/js/", "/ysqk/", "/jsqk/",
    "/ysjsgk/", "/ysjsxx/", "/ysxx/", "/jsxx/",
    # 预决算及三公经费
    "/caiwuyusuan/", "/yusuan/", "/yujuesuan/", "/yusuanjuesuan/",
    "/sangong/", "/sgjf/", "/czzj/sg/",
    # 财政局主页（部分城市财政局内容在根下）
    "/czj/"
]


def build_city_urls(gov: str, fin: str) -> List[str]:
    roots = []
    if gov:
        roots.append(gov.rstrip("/"))
    if fin and fin not in roots:
        roots.append(fin.rstrip("/"))

    urls: List[str] = []
    for root in roots:
        for path in COMMON_SECTION_PATHS:
            try:
                urls.append(urljoin(root + "/", path.lstrip("/")))
            except Exception:
                # 保护性忽略无效拼接
                continue
    # 去重并保持顺序
    seen = set()
    deduped: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def build_filters(city: str) -> Dict:
    city_variants = [city]
    if not city.endswith("市"):
        city_variants.append(f"{city}市")
    return {
        "year": 2024,
        "must_include": ["决算"],
        "must_include_any": ["本级", "本市", *city_variants],
        "exclude_any": ["部门", "单位", "街道", "镇", "乡"],
        "extra_keywords_any": [
            "预算", "财政预决算", "政府预算决算公开", "三公经费"
        ],
    }


def build_result_mapping() -> Dict[str, Dict]:
    result: Dict[str, Dict] = {}
    for city, sites in BASE_MAPPINGS.items():
        gov = (sites.get("gov") or "").strip()
        fin = (sites.get("fin") or "").strip()
        urls = build_city_urls(gov, fin)
        result[city] = {
            "gov": gov,
            "fin": fin,
            "urls": urls,
            "filters": build_filters(city),
            "violent_fallback_enabled": False,  # 保留开关，默认关闭
        }
    # 特例：和田地区为空时仍保留结构
    if "和田地区" in result:
        pass
    return result


# 暴露最终结构
CITY_SITE_SOURCES_WITH_URLS: Dict[str, Dict] = build_result_mapping()

if __name__ == "__main__":
    # 简单输出统计
    total = len(CITY_SITE_SOURCES_WITH_URLS)
    with_urls = sum(1 for v in CITY_SITE_SOURCES_WITH_URLS.values() if v.get("urls"))
    print(f"共 {total} 个城市，含检索起点的城市数：{with_urls}")
"""
城市站点映射（自动生成）。若有错误请手动修正。

CITY_SITE_OVERRIDES = {
    "城市名": {"gov": "市政府根域", "fin": "财政局根域"}
}
"""

CITY_SITE_OVERRIDES = {
    "七台河市": {"gov": "https://www.qth.gov.cn", "fin": ""},
    "三亚市": {"gov": "https://www.sanya.gov.cn", "fin": "https://mof.sanya.gov.cn"},
    "三明市": {"gov": "http://www.sanming.gov.cn", "fin": "http://cz.sm.gov.cn"},
    "三沙市": {"gov": "https://www.sansha.gov.cn", "fin": ""},
    "三门峡市": {"gov": "https://www.smx.gov.cn", "fin": "http://czj.smx.gov.cn"},
    "上海市": {"gov": "https://www.shanghai.gov.cn", "fin": "https://czj.sh.gov.cn"},
    "上饶市": {"gov": "https://www.zgsr.gov.cn", "fin": "https://www.zgsr.gov.cn/czj"},
    "东莞市": {"gov": "http://www.dongguan.gov.cn", "fin": "https://czj.dg.gov.cn"},
    "东营市": {"gov": "http://www.dongying.gov.cn", "fin": ""},
    "中卫市": {"gov": "https://www.nxzw.gov.cn/", "fin": ""},
    "中山市": {"gov": "https://www.zs.gov.cn", "fin": "https://czj.zs.gov.cn"},
    "临夏回族自治州": {"gov": "https://www.linxia.gov.cn/", "fin": ""},
    "临汾市": {"gov": "http://www.linfen.gov.cn", "fin": "http://czj.linfen.gov.cn"},
    "临沂市": {"gov": "https://www.linyi.gov.cn", "fin": "https://czj.linyi.gov.cn"},
    "临沧市": {"gov": "http://lincang.gov.cn", "fin": ""},
    "丹东市": {"gov": "https://www.dandong.gov.cn", "fin": ""},
    "丽水市": {"gov": "https://www.lishui.gov.cn", "fin": "https://www.zjzwfw.gov.cn"},
    "丽江市": {"gov": "https://www.lijiang.gov.cn", "fin": ""},
    "乌兰察布市": {"gov": "https://www.wulanchabu.gov.cn", "fin": "https://czj.wulanchabu.gov.cn"},
    "乌海市": {"gov": "http://www.wuhai.gov.cn", "fin": "http://czj.wuhai.gov.cn"},
    "乌鲁木齐市": {"gov": "https://www.wlmq.gov.cn", "fin": ""},
    "乐山市": {"gov": "https://www.leshan.gov.cn", "fin": ""},
    "九江市": {"gov": "https://www.jiujiang.gov.cn", "fin": ""},
    "云浮市": {"gov": "https://www.yunfu.gov.cn", "fin": ""},
    "亳州市": {"gov": "https://www.bozhou.gov.cn", "fin": "https://cz.bozhou.gov.cn"},
    "伊春市": {"gov": "https://www.yichun.gov.cn", "fin": "http://czj.yichun.gov.cn"},
    "伊犁哈萨克自治州": {"gov": "https://www.xjyl.gov.cn/", "fin": ""},
    "佛山市": {"gov": "https://www.foshan.gov.cn", "fin": ""},
    "佳木斯市": {"gov": "https://www.jms.gov.cn", "fin": ""},
    "保定市": {"gov": "https://www.baoding.gov.cn", "fin": ""},
    "保山市": {"gov": "https://www.baoshan.gov.cn", "fin": ""},
    "信阳市": {"gov": "https://www.xinyang.gov.cn", "fin": "https://czj.xinyang.gov.cn"},
    "儋州市": {"gov": "https://www.danzhou.gov.cn", "fin": ""},
    "克孜勒苏柯尔克孜自治州": {"gov": "https://www.xjkz.gov.cn/", "fin": ""},
    "克拉玛依市": {"gov": "https://www.klmy.gov.cn", "fin": ""},
    "六安市": {"gov": "https://www.luan.gov.cn", "fin": "https://czj.luan.gov.cn"},
    "六盘水市": {"gov": "https://www.lps.gov.cn", "fin": ""},
    "兰州市": {"gov": "https://www.lanzhou.gov.cn/", "fin": "https://czj.lanzhou.gov.cn/"},
    "兴安盟": {"gov": "https://www.xam.gov.cn", "fin": "http://czj.xam.gov.cn"},
    "内江市": {"gov": "https://www.neijiang.gov.cn", "fin": ""},
    "凉山彝族自治州": {"gov": "https://www.lsz.gov.cn/", "fin": "https://czj.lsz.gov.cn/"},
    "包头市": {"gov": "http://www.bt.gov.cn", "fin": "https://czj.baotou.gov.cn"},
    "北京市": {"gov": "https://www.beijing.gov.cn", "fin": "https://czj.beijing.gov.cn"},
    "北海市": {"gov": "http://www.beihai.gov.cn", "fin": ""},
    "十堰市": {"gov": "https://www.shiyan.gov.cn", "fin": "http://czj.shiyan.gov.cn"},
    "南京市": {"gov": "https://www.nanjing.gov.cn", "fin": "https://czj.nanjing.gov.cn"},
    "南充市": {"gov": "https://www.nanchong.gov.cn", "fin": "https://czj.nc.gov.cn"},
    "南宁市": {"gov": "https://www.nanning.gov.cn/", "fin": "https://nncz.nanning.gov.cn/"},
    "南平市": {"gov": "https://www.np.gov.cn", "fin": "https://czj.np.gov.cn"},
    "南昌市": {"gov": "https://www.nc.gov.cn", "fin": "https://czj.nc.gov.cn"},
    "南通市": {"gov": "https://www.nantong.gov.cn", "fin": "https://czj.nantong.gov.cn"},
    "南阳市": {"gov": "https://www.nanyang.gov.cn", "fin": ""},
    "博尔塔拉蒙古自治州": {"gov": "https://www.xjboz.gov.cn/", "fin": ""},
    "厦门市": {"gov": "https://www.xm.gov.cn", "fin": "https://cz.xm.gov.cn"},
    "双鸭山市": {"gov": "http://www.shuangyashan.gov.cn", "fin": ""},
    "台州市": {"gov": "https://www.taizhou.gov.cn", "fin": "https://czj.taizhou.gov.cn"},
    "合肥市": {"gov": "https://www.hefei.gov.cn", "fin": "https://czj.hefei.gov.cn"},
    "吉安市": {"gov": "https://www.jian.gov.cn", "fin": "http://czj.jian.gov.cn"},
    "吉林市": {"gov": "https://www.jl.gov.cn", "fin": ""},
    "吐鲁番市": {"gov": "https://www.tlf.gov.cn", "fin": ""},
    "吕梁市": {"gov": "http://www.lvliang.gov.cn", "fin": ""},
    "吴忠市": {"gov": "https://www.wuzhong.gov.cn", "fin": ""},
    "周口市": {"gov": "https://www.zhoukou.gov.cn", "fin": "https://czj.zhoukou.gov.cn"},
    "呼伦贝尔市": {"gov": "https://www.hlbe.gov.cn", "fin": "https://czj.hlbe.gov.cn"},
    "呼和浩特市": {"gov": "http://mzj.huhhot.gov.cn/", "fin": "http://czj.huhhot.gov.cn/"},
    "和田地区": {"gov": "", "fin": ""},
    "咸宁市": {"gov": "http://www.xianning.gov.cn", "fin": "http://czj.xianning.gov.cn"},
    "咸阳市": {"gov": "https://www.xianyang.gov.cn", "fin": "https://czj.xianyang.gov.cn"},
    "哈密市": {"gov": "https://www.hami.gov.cn", "fin": ""},
    "哈尔滨市": {"gov": "https://www.harbin.gov.cn/", "fin": ""},
    "唐山市": {"gov": "https://www.tangshan.gov.cn", "fin": "https://czj.tangshan.gov.cn"},
    "商丘市": {"gov": "https://shangqiu.gov.cn/", "fin": "https://czj.shangqiu.gov.cn/"},
    "商洛市": {"gov": "https://www.shangluo.gov.cn", "fin": ""},
    "喀什地区": {"gov": "https://www.kashi.gov.cn/", "fin": ""},
    "嘉兴市": {"gov": "https://www.jiaxing.gov.cn", "fin": "https://czj.jiaxing.gov.cn"},
    "嘉峪关市": {"gov": "https://www.jyg.gov.cn", "fin": ""},
    "四平市": {"gov": "http://www.siping.gov.cn", "fin": "http://cz.siping.gov.cn"},
    "固原市": {"gov": "https://www.gy.gov.cn", "fin": ""},
    "塔城地区": {"gov": "https://www.xjtc.gov.cn/", "fin": ""},
    "大同市": {"gov": "https://www.datong.gov.cn", "fin": ""},
    "大庆市": {"gov": "https://www.daqing.gov.cn", "fin": ""},
    "大理白族自治州": {"gov": "https://www.dali.gov.cn/", "fin": ""},
    "大连市": {"gov": "https://zwfw.dl.gov.cn/", "fin": "https://czj.dl.gov.cn"},
    "天水市": {"gov": "https://www.tianshui.gov.cn", "fin": ""},
    "天津市": {"gov": "http://www.tianjin.gov.cn", "fin": "https://cz.tj.gov.cn"},
    "太原市": {"gov": "https://www.taiyuan.gov.cn", "fin": ""},
    "威海市": {"gov": "https://www.weihai.gov.cn", "fin": "https://czj.weihai.gov.cn"},
    "娄底市": {"gov": "https://www.hnloudi.gov.cn", "fin": "https://czj.hnloudi.gov.cn"},
    "孝感市": {"gov": "https://www.xiaogan.gov.cn", "fin": "https://czj.xiaogan.gov.cn"},
    "宁德市": {"gov": "https://www.ningde.gov.cn", "fin": "https://czj.ningde.gov.cn"},
    "宁波市": {"gov": "https://www.ningbo.gov.cn", "fin": "https://czj.ningbo.gov.cn"},
    "安庆市": {"gov": "https://www.anqing.gov.cn", "fin": "https://czj.anqing.gov.cn"},
    "安康市": {"gov": "https://www.ankang.gov.cn", "fin": "https://czj.ankang.gov.cn"},
    "安阳市": {"gov": "https://www.anyang.gov.cn", "fin": "https://czj.anyang.gov.cn"},
    "安顺市": {"gov": "https://www.anshun.gov.cn", "fin": ""},
    "定西市": {"gov": "https://www.dingxi.gov.cn", "fin": "http://czj.dingxi.gov.cn"},
    "宜宾市": {"gov": "https://www.yibin.gov.cn", "fin": "https://czj.yibin.gov.cn"},
    "宜昌市": {"gov": "http://www.yichang.gov.cn", "fin": ""},
    "宜春市": {"gov": "https://www.yichun.gov.cn", "fin": "http://czj.yichun.gov.cn"},
    "宝鸡市": {"gov": "http://www.baoji.gov.cn", "fin": "http://czj.baoji.gov.cn"},
    "宣城市": {"gov": "https://www.xuancheng.gov.cn", "fin": "https://czj.xuancheng.gov.cn"},
    "宿州市": {"gov": "https://www.suzhou.gov.cn", "fin": ""},
    "宿迁市": {"gov": "https://www.suqian.gov.cn", "fin": ""},
    "山南市": {"gov": "http://www.shannan.gov.cn", "fin": "http://czj.shannan.gov.cn"},
    "岳阳市": {"gov": "https://www.yueyang.gov.cn", "fin": "https://czj.yueyang.gov.cn"},
    "崇左市": {"gov": "http://www.chongzuo.gov.cn", "fin": ""},
    "巴中市": {"gov": "https://www.bzs.gov.cn", "fin": ""},
    "巴彦淖尔市": {"gov": "https://www.bynr.gov.cn", "fin": "http://czj.bynr.gov.cn"},
    "巴音郭楞蒙古自治州": {"gov": "https://www.xjbz.gov.cn", "fin": ""},
    "常州市": {"gov": "https://www.changzhou.gov.cn", "fin": "https://czj.changzhou.gov.cn"},
    "常德市": {"gov": "https://www.changde.gov.cn", "fin": "https://czj.changde.gov.cn"},
    "平凉市": {"gov": "https://www.pingliang.gov.cn", "fin": "https://czj.pingliang.gov.cn"},
    "平顶山市": {"gov": "https://www.pds.gov.cn", "fin": "https://czj.pds.gov.cn"},
    "广元市": {"gov": "https://www.gy.gov.cn", "fin": ""},
    "广安市": {"gov": "https://www.guang-an.gov.cn/", "fin": ""},
    "广州市": {"gov": "http://www.guangzhou.gov.cn", "fin": "https://czj.gz.gov.cn"},
    "庆阳市": {"gov": "https://www.qy.gov.cn", "fin": ""},
    "廊坊市": {"gov": "https://www.lf.gov.cn", "fin": "http://czj.lf.gov.cn"},
    "延安市": {"gov": "https://www.yanan.gov.cn", "fin": "https://czj.yanan.gov.cn"},
    "延边朝鲜族自治州": {"gov": "http://yanbian.gov.cn", "fin": "http://czj.yanbian.gov.cn"},
    "开封市": {"gov": "https://www.kaifeng.gov.cn", "fin": "http://czj.kaifeng.gov.cn"},
    "张家口市": {"gov": "http://www.zjks.gov.cn", "fin": ""},
    "张家界市": {"gov": "https://www.zjj.gov.cn", "fin": "https://cz.zjj.gov.cn"},
    "张掖市": {"gov": "https://www.zhangye.gov.cn", "fin": ""},
    "徐州市": {"gov": "https://www.xz.gov.cn", "fin": "https://czj.xz.gov.cn"},
    "德宏傣族景颇族自治州": {"gov": "https://www.dh.gov.cn", "fin": ""},
    "德州市": {"gov": "https://www.dezhou.gov.cn", "fin": "http://czj.dezhou.gov.cn"},
    "德阳市": {"gov": "https://www.deyang.gov.cn", "fin": ""},
    "忻州市": {"gov": "https://www.xz.gov.cn", "fin": "https://czj.xz.gov.cn"},
    "怀化市": {"gov": "https://www.huaihua.gov.cn", "fin": ""},
    "怒江傈僳族自治州": {"gov": "https://www.nujiang.gov.cn", "fin": "https://www.nujiang.gov.cn/czj/"},
    "恩施土家族苗族自治州": {"gov": "http://enshi.gov.cn/", "fin": "http://czj.enshi.gov.cn/"},
    "惠州市": {"gov": "https://www.huizhou.gov.cn", "fin": ""},
    "成都市": {"gov": "https://www.chengdu.gov.cn", "fin": "https://cdcz.chengdu.gov.cn/"},
    "扬州市": {"gov": "https://www.yangzhou.gov.cn", "fin": "https://czj.yangzhou.gov.cn"},
    "承德市": {"gov": "https://www.chengde.gov.cn", "fin": ""},
    "抚州市": {"gov": "https://www.fuzhou.gov.cn", "fin": ""},
    "抚顺市": {"gov": "https://www.fushun.gov.cn", "fin": ""},
    "拉萨市": {"gov": "https://www.lasa.gov.cn", "fin": "https://czj.lasa.gov.cn"},
    "揭阳市": {"gov": "http://www.jieyang.gov.cn", "fin": ""},
    "攀枝花市": {"gov": "http://www.panzhihua.gov.cn", "fin": "http://czj.panzhihua.gov.cn"},
    "文山壮族苗族自治州": {"gov": "https://www.ynws.gov.cn", "fin": ""},
    "新乡市": {"gov": "https://www.xinxiang.gov.cn", "fin": ""},
    "新余市": {"gov": "https://www.xinyu.gov.cn", "fin": "https://czj.xinyu.gov.cn"},
    "无锡市": {"gov": "https://www.wuxi.gov.cn", "fin": "https://cz.wuxi.gov.cn"},
    "日喀则市": {"gov": "http://www.rikaze.gov.cn", "fin": "http://czj.rikaze.gov.cn"},
    "日照市": {"gov": "http://www.rizhao.gov.cn", "fin": "http://czj.rizhao.gov.cn"},
    "昆明市": {"gov": "https://www.km.gov.cn", "fin": "https://czj.km.gov.cn"},
    "昌吉回族自治州": {"gov": "https://www.cj.gov.cn/", "fin": "https://www.cjs.gov.cn/"},
    "昌都市": {"gov": "https://www.changdu.gov.cn/", "fin": "https://czj.changdu.gov.cn/"},
    "昭通市": {"gov": "https://www.zt.gov.cn", "fin": ""},
    "晋中市": {"gov": "https://www.jz.gov.cn", "fin": "https://czj.jz.gov.cn"},
    "晋城市": {"gov": "https://www.jcs.gov.cn", "fin": ""},
    "普洱市": {"gov": "https://www.pes.gov.cn/", "fin": ""},
    "景德镇市": {"gov": "https://www.jdz.gov.cn", "fin": "https://cz.jdz.gov.cn"},
    "曲靖市": {"gov": "https://www.qj.gov.cn", "fin": "https://czj.qj.gov.cn"},
    "朔州市": {"gov": "http://www.shuozhou.gov.cn", "fin": "http://czj.shuozhou.gov.cn"},
    "朝阳市": {"gov": "https://chaoyang.gov.cn/", "fin": ""},
    "本溪市": {"gov": "https://www.benxi.gov.cn", "fin": "https://czj.benxi.gov.cn"},
    "来宾市": {"gov": "http://www.laibin.gov.cn", "fin": ""},
    "杭州市": {"gov": "https://www.hangzhou.gov.cn", "fin": "https://czj.hangzhou.gov.cn"},
    "松原市": {"gov": "https://www.jlsy.gov.cn", "fin": ""},
    "林芝市": {"gov": "http://www.linzhi.gov.cn", "fin": ""},
    "果洛藏族自治州": {"gov": "http://www.guoluo.gov.cn/", "fin": ""},
    "枣庄市": {"gov": "http://www.zaozhuang.gov.cn", "fin": ""},
    "柳州市": {"gov": "http://www.liuzhou.gov.cn", "fin": ""},
    "株洲市": {"gov": "https://www.zhuzhou.gov.cn", "fin": "https://czj.zhuzhou.gov.cn"},
    "桂林市": {"gov": "https://www.guilin.gov.cn", "fin": "https://czj.guilin.gov.cn"},
    "梅州市": {"gov": "https://www.meizhou.gov.cn", "fin": ""},
    "梧州市": {"gov": "http://www.wuzhou.gov.cn", "fin": "http://czj.wuzhou.gov.cn"},
    "楚雄彝族自治州": {"gov": "https://cxz.gov.cn/", "fin": ""},
    "榆林市": {"gov": "http://www.yulin.gov.cn", "fin": "http://czj.yulin.gov.cn"},
    "武威市": {"gov": "https://www.gswuwei.gov.cn/", "fin": ""},
    "武汉市": {"gov": "https://www.wuhan.gov.cn", "fin": "https://czj.wuhan.gov.cn"},
    "毕节市": {"gov": "https://www.bijie.gov.cn", "fin": ""},
    "永州市": {"gov": "https://www.yongzhou.gov.cn", "fin": ""},
    "汉中市": {"gov": "https://www.hanzhong.gov.cn", "fin": "https://czj.hanzhong.gov.cn"},
    "汕头市": {"gov": "https://www.shantou.gov.cn", "fin": ""},
    "汕尾市": {"gov": "https://www.shanwei.gov.cn", "fin": ""},
    "江门市": {"gov": "https://www.jiangmen.gov.cn", "fin": ""},
    "池州市": {"gov": "https://www.chizhou.gov.cn", "fin": "https://czj.chizhou.gov.cn"},
    "沈阳市": {"gov": "https://www.shenyang.gov.cn", "fin": "https://czj.shenyang.gov.cn"},
    "沧州市": {"gov": "https://www.cangzhou.gov.cn", "fin": ""},
    "河池市": {"gov": "http://www.hechi.gov.cn", "fin": ""},
    "河源市": {"gov": "http://www.heyuan.gov.cn", "fin": ""},
    "泉州市": {"gov": "https://www.quanzhou.gov.cn", "fin": "https://czj.quanzhou.gov.cn"},
    "泰安市": {"gov": "https://www.taian.gov.cn", "fin": "https://czj.taian.gov.cn"},
    "泰州市": {"gov": "https://www.taizhou.gov.cn", "fin": "https://czj.taizhou.gov.cn"},
    "泸州市": {"gov": "https://www.luzhou.gov.cn/", "fin": ""},
    "洛阳市": {"gov": "https://www.ly.gov.cn", "fin": "https://cz.ly.gov.cn"},
    "济南市": {"gov": "http://www.jinan.gov.cn", "fin": ""},
    "济宁市": {"gov": "https://www.jining.gov.cn", "fin": ""},
    "海东市": {"gov": "https://www.haidong.gov.cn", "fin": ""},
    "海北藏族自治州": {"gov": "https://www.haibei.gov.cn/", "fin": ""},
    "海南藏族自治州": {"gov": "https://www.hainanzhou.gov.cn/", "fin": ""},
    "海口市": {"gov": "https://www.haikou.gov.cn", "fin": ""},
    "海西蒙古族藏族自治州": {"gov": "https://www.haixi.gov.cn/", "fin": ""},
    "淄博市": {"gov": "https://www.zibo.gov.cn", "fin": ""},
    "淮北市": {"gov": "https://www.huaibei.gov.cn", "fin": "https://czj.huaibei.gov.cn"},
    "淮南市": {"gov": "https://www.huainan.gov.cn", "fin": "https://cz.huainan.gov.cn"},
    "淮安市": {"gov": "http://www.huaian.gov.cn", "fin": "http://czj.huaian.gov.cn"},
    "深圳市": {"gov": "http://www.shenzhen.gov.cn", "fin": ""},
    "清远市": {"gov": "http://www.qingyuan.gov.cn", "fin": ""},
    "温州市": {"gov": "https://www.wenzhou.gov.cn", "fin": "https://czj.wenzhou.gov.cn"},
    "渭南市": {"gov": "https://www.weinan.gov.cn/", "fin": ""},
    "湖州市": {"gov": "https://www.huzhou.gov.cn", "fin": "https://czj.huzhou.gov.cn"},
    "湘潭市": {"gov": "https://www.xiangtan.gov.cn", "fin": "https://cz.xiangtan.gov.cn"},
    "湘西土家族苗族自治州": {"gov": "https://www.xxz.gov.cn/", "fin": ""},
    "湛江市": {"gov": "https://www.zhanjiang.gov.cn", "fin": ""},
    "滁州市": {"gov": "https://www.chuzhou.gov.cn", "fin": ""},
    "滨州市": {"gov": "http://www.binzhou.gov.cn", "fin": "http://cz.binzhou.gov.cn"},
    "漯河市": {"gov": "http://www.tahe.gov.cn", "fin": ""},
    "漳州市": {"gov": "https://www.zhangzhou.gov.cn", "fin": "http://czj.zhangzhou.gov.cn"},
    "潍坊市": {"gov": "http://www.weifang.gov.cn", "fin": "http://czj.weifang.gov.cn"},
    "潮州市": {"gov": "https://www.chaozhou.gov.cn", "fin": ""},
    "濮阳市": {"gov": "https://www.puyang.gov.cn", "fin": ""},
    "烟台市": {"gov": "https://www.yantai.gov.cn", "fin": "https://czj.yantai.gov.cn"},
    "焦作市": {"gov": "https://www.jiaozuo.gov.cn", "fin": "https://czj.jiaozuo.gov.cn"},
    "牡丹江市": {"gov": "https://www.mdj.gov.cn", "fin": ""},
    "玉林市": {"gov": "http://www.yulin.gov.cn", "fin": "http://czj.yulin.gov.cn"},
    "玉树藏族自治州": {"gov": "https://www.yushuzhou.gov.cn/", "fin": ""},
    "玉溪市": {"gov": "https://www.yuxi.gov.cn", "fin": ""},
    "珠海市": {"gov": "https://www.zhuhai.gov.cn", "fin": ""},
    "甘南藏族自治州": {"gov": "http://www.gnzrmzf.gov.cn/", "fin": ""},
    "甘孜藏族自治州": {"gov": "https://www.gzz.gov.cn/", "fin": ""},
    "白城市": {"gov": "http://www.bc.gov.cn", "fin": ""},
    "白山市": {"gov": "http://www.cbs.gov.cn/", "fin": ""},
    "白银市": {"gov": "https://www.baiyin.gov.cn", "fin": ""},
    "百色市": {"gov": "http://www.baise.gov.cn", "fin": "http://czj.baise.gov.cn"},
    "益阳市": {"gov": "https://www.yiyang.gov.cn", "fin": ""},
    "盐城市": {"gov": "https://www.ycs.gov.cn", "fin": "https://czj.yancheng.gov.cn"},
    "盘锦市": {"gov": "https://www.panjin.gov.cn", "fin": "https://czj.panjin.gov.cn"},
    "眉山市": {"gov": "https://www.ms.gov.cn", "fin": ""},
    "石嘴山市": {"gov": "https://www.shizuishan.gov.cn", "fin": ""},
    "石家庄市": {"gov": "https://www.sjz.gov.cn", "fin": ""},
    "福州市": {"gov": "https://www.fuzhou.gov.cn", "fin": ""},
    "秦皇岛市": {"gov": "http://www.qhd.gov.cn/", "fin": ""},
    "红河哈尼族彝族自治州": {"gov": "https://www.hh.gov.cn/", "fin": ""},
    "绍兴市": {"gov": "https://www.sx.gov.cn", "fin": ""},
    "绥化市": {"gov": "https://www.suihua.gov.cn", "fin": "https://czj.sh.gov.cn"},
    "绵阳市": {"gov": "https://www.my.gov.cn", "fin": "https://czj.my.gov.cn"},
    "聊城市": {"gov": "http://www.liaocheng.gov.cn", "fin": "http://czj.liaocheng.gov.cn"},
    "肇庆市": {"gov": "https://www.zhaoqing.gov.cn", "fin": ""},
    "自贡市": {"gov": "https://www.zg.gov.cn", "fin": ""},
    "舟山市": {"gov": "https://www.zhoushan.gov.cn", "fin": "https://czj.zs.gov.cn"},
    "芜湖市": {"gov": "https://www.wuhu.gov.cn/", "fin": ""},
    "苏州市": {"gov": "https://www.suzhou.gov.cn", "fin": ""},
    "茂名市": {"gov": "http://www.maoming.gov.cn", "fin": "http://czj.maoming.gov.cn"},
    "荆州市": {"gov": "https://www.jingzhou.gov.cn", "fin": "http://czj.jingzhou.gov.cn"},
    "荆门市": {"gov": "https://www.jingmen.gov.cn", "fin": "http://czj.jingmen.gov.cn"},
    "莆田市": {"gov": "https://www.putian.gov.cn", "fin": "https://czj.putian.gov.cn"},
    "菏泽市": {"gov": "http://www.heze.gov.cn", "fin": ""},
    "萍乡市": {"gov": "https://www.pingxiang.gov.cn", "fin": "https://czj.pingxiang.gov.cn"},
    "营口市": {"gov": "https://www.yingkou.gov.cn", "fin": "https://czj.yingkou.gov.cn"},
    "葫芦岛市": {"gov": "https://www.hld.gov.cn", "fin": "https://czj.hld.gov.cn"},
    "蚌埠市": {"gov": "https://www.bengbu.gov.cn", "fin": "https://czj.bengbu.gov.cn"},
    "衡水市": {"gov": "http://www.hengshui.gov.cn", "fin": "http://czj.hengshui.gov.cn"},
    "衡阳市": {"gov": "https://www.hengyang.gov.cn", "fin": ""},
    "衢州市": {"gov": "https://www.qz.gov.cn", "fin": "https://czj.qz.gov.cn"},
    "襄阳市": {"gov": "http://www.xiangyang.gov.cn", "fin": "http://czj.xiangyang.gov.cn"},
    "西双版纳傣族自治州": {"gov": "https://www.xsbn.gov.cn/", "fin": ""},
    "西宁市": {"gov": "https://www.xining.gov.cn", "fin": "https://czj.xining.gov.cn"},
    "西安市": {"gov": "https://www.xa.gov.cn", "fin": ""},
    "许昌市": {"gov": "https://www.xuchang.gov.cn", "fin": "https://czj.xuchang.gov.cn"},
    "贵港市": {"gov": "http://www.gxgg.gov.cn/", "fin": ""},
    "贵阳市": {"gov": "https://www.guiyang.gov.cn", "fin": "https://czj.guiyang.gov.cn"},
    "贺州市": {"gov": "http://www.gxhz.gov.cn/", "fin": ""},
    "资阳市": {"gov": "http://www.ziyang.gov.cn", "fin": ""},
    "赣州市": {"gov": "https://www.ganzhou.gov.cn", "fin": "https://czj.ganzhou.gov.cn"},
    "赤峰市": {"gov": "http://www.chifeng.gov.cn", "fin": "http://czj.chifeng.gov.cn"},
    "辽源市": {"gov": "http://www.liaoyuan.gov.cn", "fin": "http://czj.liaoyuan.gov.cn"},
    "辽阳市": {"gov": "http://www.liaoyang.gov.cn", "fin": "http://czj.liaoyang.gov.cn"},
    "达州市": {"gov": "https://www.dazhou.gov.cn", "fin": ""},
    "运城市": {"gov": "https://www.yuncheng.gov.cn", "fin": ""},
    "连云港市": {"gov": "https://www.lyg.gov.cn", "fin": "http://czj.lyg.gov.cn"},
    "迪庆藏族自治州": {"gov": "http://www.diqing.gov.cn/", "fin": ""},
    "通化市": {"gov": "http://www.tonghua.gov.cn", "fin": ""},
    "通辽市": {"gov": "https://www.tongliao.gov.cn", "fin": "https://czj.tongliao.gov.cn"},
    "遂宁市": {"gov": "https://www.suining.gov.cn", "fin": ""},
    "遵义市": {"gov": "https://www.zunyi.gov.cn", "fin": "https://czj.zunyi.gov.cn"},
    "邢台市": {"gov": "http://www.xingtai.gov.cn", "fin": ""},
    "那曲市": {"gov": "http://www.naqu.gov.cn", "fin": ""},
    "邯郸市": {"gov": "https://www.hd.gov.cn", "fin": ""},
    "邵阳市": {"gov": "https://www.shaoyang.gov.cn", "fin": "https://czj.shaoyang.gov.cn"},
    "郑州市": {"gov": "https://www.zhengzhou.gov.cn", "fin": ""},
    "郴州市": {"gov": "https://www.czs.gov.cn", "fin": ""},
    "鄂尔多斯市": {"gov": "https://www.ordos.gov.cn/", "fin": ""},
    "鄂州市": {"gov": "https://www.ezhou.gov.cn", "fin": "https://czj.ezhou.gov.cn"},
    "酒泉市": {"gov": "https://www.jiuquan.gov.cn", "fin": "https://czj.jiuquan.gov.cn"},
    "重庆市": {"gov": "https://www.cq.gov.cn", "fin": "https://czj.cq.gov.cn"},
    "金华市": {"gov": "https://www.jinhua.gov.cn", "fin": "http://czj.jinhua.gov.cn"},
    "金昌市": {"gov": "https://www.jcs.gov.cn", "fin": ""},
    "钦州市": {"gov": "http://www.qinzhou.gov.cn", "fin": "http://czj.qinzhou.gov.cn"},
    "铁岭市": {"gov": "http://www.tieling.gov.cn", "fin": "https://czj.tl.gov.cn"},
    "铜仁市": {"gov": "https://www.tongren.gov.cn", "fin": ""},
    "铜川市": {"gov": "http://www.tongchuan.gov.cn", "fin": ""},
    "铜陵市": {"gov": "https://www.tl.gov.cn", "fin": "https://czj.tl.gov.cn"},
    "银川市": {"gov": "https://www.yinchuan.gov.cn", "fin": "https://czj.yinchuan.gov.cn"},
    "锡林郭勒盟": {"gov": "https://www.xlgl.gov.cn/", "fin": ""},
    "锦州市": {"gov": "https://www.jz.gov.cn", "fin": "https://czj.jz.gov.cn"},
    "镇江市": {"gov": "https://www.zhenjiang.gov.cn", "fin": "https://czj.zhenjiang.gov.cn"},
    "长春市": {"gov": "http://www.changchun.gov.cn", "fin": "http://czj.changchun.gov.cn"},
    "长沙市": {"gov": "http://www.changsha.gov.cn", "fin": ""},
    "长治市": {"gov": "https://www.changzhi.gov.cn/", "fin": ""},
    "阜新市": {"gov": "https://www.fuxin.gov.cn", "fin": "https://czj.fuxin.gov.cn"},
    "阜阳市": {"gov": "https://www.fuyang.gov.cn", "fin": "https://czj.fy.gov.cn"},
    "防城港市": {"gov": "https://www.fcgs.gov.cn", "fin": ""},
    "阳江市": {"gov": "http://www.yangjiang.gov.cn", "fin": ""},
    "阳泉市": {"gov": "https://www.yq.gov.cn", "fin": "https://czj.yq.gov.cn"},
    "阿克苏地区": {"gov": "https://www.akss.gov.cn/", "fin": ""},
    "阿勒泰地区": {"gov": "https://www.xjalt.gov.cn/", "fin": ""},
    "阿坝藏族羌族自治州": {"gov": "https://www.abazhou.gov.cn/", "fin": ""},
    "阿拉善盟": {"gov": "https://www.als.gov.cn/", "fin": ""},
    "阿里地区": {"gov": "https://al.gov.cn/", "fin": ""},
    "陇南市": {"gov": "https://www.longnan.gov.cn", "fin": ""},
    "随州市": {"gov": "http://www.suizhou.gov.cn", "fin": ""},
    "雅安市": {"gov": "https://www.yaan.gov.cn", "fin": "https://czj.yaan.gov.cn"},
    "青岛市": {"gov": "http://www.qingdao.gov.cn", "fin": ""},
    "鞍山市": {"gov": "http://www.anshan.gov.cn", "fin": ""},
    "韶关市": {"gov": "https://www.sg.gov.cn", "fin": ""},
    "马鞍山市": {"gov": "https://www.mas.gov.cn", "fin": "https://cz.mas.gov.cn"},
    "驻马店市": {"gov": "https://www.zhumadian.gov.cn", "fin": ""},
    "鸡西市": {"gov": "https://www.jixi.gov.cn", "fin": ""},
    "鹤壁市": {"gov": "https://www.hebi.gov.cn/", "fin": ""},
    "鹤岗市": {"gov": "https://www.hegang.gov.cn", "fin": ""},
    "鹰潭市": {"gov": "http://www.yingtan.gov.cn", "fin": "http://czj.yingtan.gov.cn"},
    "黄冈市": {"gov": "https://www.hg.gov.cn/", "fin": ""},
    "黄南藏族自治州": {"gov": "http://www.huangnan.gov.cn/", "fin": ""},
    "黄山市": {"gov": "https://www.huangshan.gov.cn", "fin": "https://czj.huangshan.gov.cn"},
    "黄石市": {"gov": "https://www.huangshi.gov.cn", "fin": "https://czj.huangshi.gov.cn"},
    "黑河市": {"gov": "https://www.heihe.gov.cn", "fin": ""},
    "黔东南苗族侗族自治州": {"gov": "https://www.qdn.gov.cn/", "fin": ""},
    "黔南布依族苗族自治州": {"gov": "https://www.qiannan.gov.cn/", "fin": ""},
    "黔西南布依族苗族自治州": {"gov": "https://www.qxn.gov.cn/", "fin": ""},
    "齐齐哈尔市": {"gov": "https://www.qqhr.gov.cn/", "fin": ""},
    "龙岩市": {"gov": "https://www.longyan.gov.cn", "fin": "https://czj.longyan.gov.cn"},
}
