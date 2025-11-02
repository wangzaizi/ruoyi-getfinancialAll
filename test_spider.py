"""
测试爬虫脚本
用于测试少量城市，验证功能是否正常
"""
import sys
from spider import FinanceReportSpider
from utils import print_statistics


def main():
    print("="*60)
    print("财政报告爬虫 - 测试模式")
    print("="*60)
    print(f"目标年份：2024年")
    print(f"模式：测试模式（仅爬取少量城市）")
    print("="*60)
    
    # 默认测试城市
    test_cities = ["赣州市", "北京市", "上海市", "杭州市", "深圳市"]
    
    print(f"\n将测试以下城市：")
    for i, city in enumerate(test_cities, 1):
        print(f"  {i}. {city}")
    
    # 询问是否使用默认测试城市
    response = input("\n使用默认测试城市？(y/n): ").strip().lower()
    if response != 'y':
        print("\n请输入要测试的城市名称（用逗号分隔，例如：赣州市,北京市）:")
        cities_input = input("城市列表: ").strip()
        if cities_input:
            test_cities = [city.strip() for city in cities_input.split(',') if city.strip()]
    
    if not test_cities:
        print("未输入有效城市，使用默认测试城市")
        test_cities = ["赣州市", "北京市", "上海市", "杭州市", "深圳市"]
    
    print(f"\n开始测试爬取 {len(test_cities)} 个城市...\n")
    
    try:
        spider = FinanceReportSpider()
        results = spider.run(test_mode=True, test_cities=test_cities)
        
        print("\n" + "="*60)
        print("测试完成！")
        print("="*60)
        
        # 详细统计
        success_count = sum(1 for r in results if r['success'])
        total_files = sum(r['files_downloaded'] for r in results)
        
        print(f"\n测试结果：")
        print(f"  成功: {success_count}/{len(test_cities)}")
        print(f"  失败: {len(test_cities) - success_count}/{len(test_cities)}")
        print(f"  下载文件数: {total_files}")
        
        print(f"\n详细信息：")
        for result in results:
            status = "✓ 成功" if result['success'] else "✗ 失败"
            print(f"  {result['city']}: {status}", end="")
            if result['website']:
                print(f" - 网站: {result['website']}", end="")
            if result['files_downloaded'] > 0:
                print(f" - 文件: {result['files_downloaded']}", end="")
            if result['errors']:
                print(f" - 错误: {len(result['errors'])}个", end="")
            print()
        
        # 显示错误信息
        failed_results = [r for r in results if not r['success']]
        if failed_results:
            print(f"\n失败详情：")
            for result in failed_results:
                print(f"  {result['city']}:")
                for error in result['errors']:
                    print(f"    - {error}")
        
        print("\n测试结果已保存到 data/test_summary.json")
        print("="*60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
    except Exception as e:
        print(f"\n\n测试发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

