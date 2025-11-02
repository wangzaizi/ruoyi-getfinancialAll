"""
爬虫启动脚本
提供交互式界面
"""
import sys
from spider import FinanceReportSpider
from utils import print_statistics


def main():
    print("="*60)
    print("中国地级行政区划财政报告爬虫")
    print("="*60)
    print(f"目标：爬取334个地级行政区划的财政决算报告")
    print(f"年份：2024年")
    print("="*60)
    
    # 显示当前统计
    print_statistics()
    
    # 询问运行模式
    print("\n请选择运行模式：")
    print("  1. 测试模式（测试少量城市）")
    print("  2. 完整模式（爬取所有334个城市）")
    mode = input("请输入选择 (1/2): ").strip()
    
    if mode == "1":
        print("\n启动测试模式...")
        print("提示：可以运行 python test_spider.py 进行更详细的测试")
        import subprocess
        subprocess.run([sys.executable, "test_spider.py"])
        return
    
    # 询问是否继续
    response = input("\n是否开始/继续爬取所有城市？(y/n): ").strip().lower()
    if response != 'y':
        print("已取消")
        return
    
    print("\n开始爬取...\n")
    
    try:
        spider = FinanceReportSpider()
        results = spider.run()
        
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


if __name__ == "__main__":
    main()

