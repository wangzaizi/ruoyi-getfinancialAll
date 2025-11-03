import sys
import subprocess
from spider import FinanceReportSpider
from mapping_tool import run_city_mapping_mode as mapping_run_city_mapping_mode
from utils import print_statistics

def run_test_mode():
    """启动测试模式"""
    print("\n启动测试模式...")
    # print("提示：可以运行 python test_spider.py 进行更详细的测试")
    subprocess.run([sys.executable, "test_spider.py"])

def run_full_mode():
    """启动完整爬取模式"""
    print("\n开始爬取所有城市...")
    try:
        spider = FinanceReportSpider()
        spider.run()
        
        print("\n" + "="*60)
        print("爬取完成！")
        print("="*60)
        print_statistics()
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
        print_statistics()
    except Exception as e:
        print(f"\n\n发生错误: {e}")
        import traceback
        traceback.print_exc()

def run_city_mapping_mode():
    """运行城市站点映射测试（不改 spider.py，只基于 site_mappings.py）"""
    print("\n开始城市站点映射测试（日志中给出建议，手动更新 site_mappings.py）……")
    try:
        mapping_run_city_mapping_mode(auto_update=False)
    except Exception as e:
        print(f"运行失败: {e}")

def main():
    print("="*60)
    print("中国地级行政区划财政报告爬虫")
    print("="*60)
    print(f"目标：爬取334个地级行政区划的财政决算报告")
    print(f"年份：2024年")
    print("="*60)
    
    # 显示当前统计
    print_statistics()

    # 检查命令行参数
    if len(sys.argv) > 1:
        mode_arg = sys.argv[1]
        if mode_arg == 'test':
            run_test_mode()
        elif mode_arg == 'full':
            run_full_mode()
        else:
            print(f"\n错误: 未知的模式参数 '{mode_arg}'。请使用 'test' 或 'full'。")
            sys.exit(1)
        return

    # 如果没有命令行参数，则进入交互模式
    print("\n请选择运行模式：")
    print("  1. 测试模式（测试少量城市）")
    print("  2. 完整模式（爬取所有334个城市）")
    print("  3. 城市站点映射测试（生成/验证市政府/财政局网站映射）")
    mode = input("请输入选择 (1/2/3): ").strip()
    
    if mode == "1":
        run_test_mode()
    elif mode == "2":
        response = input("\n是否开始/继续爬取所有城市？(y/n): ").strip().lower()
        if response == 'y':
            run_full_mode()
        else:
            print("已取消")
    elif mode == "3":
        run_city_mapping_mode()
    else:
        print("无效选择，已取消。")



if __name__ == "__main__":
    main()

