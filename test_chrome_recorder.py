# -*- encoding: utf-8 -*-
"""
Chrome 直播录制功能 - 快速测试脚本
用于验证 Chrome 渲染和录制是否正常工作
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.chrome_recorder import ChromeLiveRecorder, ChromeRecorderConfig, quick_record


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║          🎬 Chrome 直播画面录制工具 - 快速测试                  ║
╠══════════════════════════════════════════════════════════════╣
║  功能: 使用真实 Chrome 浏览器内核渲染并录制直播画面              ║
║  优势: 完整保留弹幕/礼物/互动特效，绕过反爬检测                 ║
╚══════════════════════════════════════════════════════════════╝
    """)


def test_basic_recording():
    """基础录制测试"""
    if len(sys.argv) < 2:
        print("用法: python test_chrome_recorder.py <直播间URL> [时长秒]")
        print()
        print("示例:")
        print("  python test_chrome_recorder.py https://live.douyin.com/example 60")
        print("  python test_chrome_recorder.py https://www.douyu.com/123456 120")
        print()
        print("支持平台: 抖音、斗鱼、虎牙、B站、快手等所有网页端直播")
        return

    url = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    
    print(f"📍 目标URL: {url}")
    print(f"⏱️  录制时长: {duration}秒")
    print(f"📁  输出目录: ./downloads")
    print("-" * 60)
    
    try:
        result = asyncio.run(quick_record(url, "./downloads", duration))
        print("\n" + "=" * 60)
        if result and os.path.exists(result):
            size_mb = os.path.getsize(result) / (1024 * 1024)
            print(f"✅ 测试成功！")
            print(f"   文件: {result}")
            print(f"   大小: {size_mb:.2f} MB")
        else:
            print("⚠️  测试完成但未生成视频文件（可能直播未开始）")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断录制")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_interactive_mode():
    """交互式测试模式（更详细的控制）"""
    print("\n🔧 进入交互式测试模式...")
    
    url = input("请输入直播间URL: ").strip()
    if not url or 'http' not in url:
        print("❌ 无效的URL")
        return
    
    config = ChromeRecorderConfig(
        output_dir="./downloads",
        fps=30,
        window_size=(1280, 720),
        hardware_acceleration=True,
        auto_record_on_live=False
    )
    
    recorder = ChromeLiveRecorder(config)
    
    recorder.on_live_detected = lambda: print("✅ 检测到直播中！")
    recorder.on_live_ended = lambda: print("⏸️  直播未开始或已结束")
    recorder.on_error = lambda e: print(f"❌ 错误: {e}")
    recorder.on_status_update = lambda s: print(f"📊 {s}")
    recorder.on_recording_started = lambda p: print(f"🎬 开始录制: {p}")
    recorder.on_recording_stopped = lambda p: print(f"⏹️  录制结束: {p}")
    
    print(f"\n正在启动浏览器加载: {url}")
    
    try:
        success = await recorder.start_browser(url)
        if not success:
            print("❌ 浏览器启动失败")
            return
        
        print("\n浏览器已启动！可用命令:")
        print("  r - 开始/停止录制")
        print("  s - 截图")
        print("  a - 获取主播名称")
        print("  l - 检查直播状态")
        print("  q - 退出")
        
        while True:
            cmd = input("\n> ").strip().lower()
            
            if cmd == 'q':
                break
            elif cmd == 'r':
                if recorder.is_recording:
                    path = await recorder.stop_recording_async()
                    print(f"已停止录制: {path}")
                else:
                    name = await recorder.get_anchor_name()
                    success = await recorder.start_recording_async(name)
                    if success:
                        print("已开始录制")
            elif cmd == 's':
                path = recorder.take_screenshot_sync()
                print(f"截图保存到: {path}" if path else "截图失败")
            elif cmd == 'a':
                name = await recorder.get_anchor_name()
                print(f"主播: {name}")
            elif cmd == 'l':
                is_live = await recorder._check_if_live()
                print(f"直播状态: {'🟢 进行中' if is_live else '⚪ 未开始'}")
            else:
                print("未知命令")
        
    except KeyboardInterrupt:
        print("\n正在退出...")
    finally:
        recorder.stop_browser()
        print("✅ 已清理资源")


def test_installation():
    """检查依赖安装情况"""
    print("\n🔍 检查依赖安装情况...\n")
    
    issues = []
    
    try:
        import playwright
        print("✅ playwright 已安装 (版本: {playwright.__version__})")
    except ImportError:
        issues.append("❌ playwright 未安装 → 运行: pip install playwright")
    
    try:
        from playwright.sync_api import sync_playwright
        print("✅ playwright Python 绑定正常")
    except ImportError as e:
        issues.append(f"❌ playwright 导入失败: {e}")
    
    try:
        from src.chrome_recorder import ChromeLiveRecorder, ChromeRecorderConfig
        print("✅ chrome_recorder 模块可导入")
    except ImportError as e:
        issues.append(f"❌ chrome_recorder 模块缺失: {e}")
    
    if not issues:
        print("\n✅ 所有依赖已就绪！可以运行测试了。")
        
        has_chromium = False
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
                has_chromium = True
            print("✅ Chromium 浏览器已下载")
        except Exception as e:
            print(f"⚠️  Chromium 未下载: {e}")
            print("   运行: playwright install chromium")
    else:
        print("\n⚠️  发现以下问题:")
        for issue in issues:
            print(f"  {issue}")
    
    return len(issues) == 0


if __name__ == '__main__':
    print_banner()
    
    if len(sys.argv) > 1 and sys.argv[1] != '--check' and sys.argv[1] != '--interactive':
        test_basic_recording()
    elif '--interactive' in sys.argv or '-i' in sys.argv:
        asyncio.run(test_interactive_mode())
    elif '--check' in sys.argv or '-c' in sys.argv:
        test_installation()
    else:
        print("使用方法:")
        print("  1. 检查依赖: python test_chrome_recorder.py --check")
        print("  2. 快速录制: python test_chrome_recorder.py <URL> [时长]")
        print("  3. 交互模式: python test_chrome_recorder.py --interactive")
        print()
        print("推荐先运行 --check 检查环境配置")
