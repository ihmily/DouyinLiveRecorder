# -*- encoding: utf-8 -*-
"""
Chrome 内核直播画面渲染与录制模块
支持 Playwright (推荐) 和 CEF 两种后端
"""
import os
import sys
import time
import asyncio
import threading
import subprocess
from pathlib import Path
from typing import Optional, Callable, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class RecordMode(Enum):
    STREAM_ONLY = "stream_only"
    CHROME_RENDER = "chrome_render"
    BOTH = "both"


@dataclass
class ChromeRecorderConfig:
    output_dir: str = "./downloads"
    output_format: str = "mp4"
    video_quality: str = "high"
    fps: int = 30
    hardware_acceleration: bool = True
    window_size: tuple = field(default_factory=lambda: (1280, 720))
    show_browser_ui: bool = False
    auto_record_on_live: bool = True
    record_timeout: int = 7200
    headless: bool = False


class ChromeLiveRecorder:
    def __init__(self, config: ChromeRecorderConfig = None):
        self.config = config or ChromeRecorderConfig()
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.is_recording = False
        self.is_running = False
        self.recording_thread = None
        self.monitor_thread = None
        self.video_path = None
        self.frame_count = 0
        self.start_time = None
        self.current_url = ""
        self._stop_event = threading.Event()

        self.on_live_detected: Optional[Callable] = None
        self.on_live_ended: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_recording_started: Optional[Callable] = None
        self.on_recording_stopped: Optional[Callable[[str], None]] = None
        self.on_status_update: Optional[Callable[[str], None]] = None

    def _notify(self, callback, *args):
        if callback:
            try:
                callback(*args)
            except Exception as e:
                print(f"[ChromeRecorder] 回调执行错误: {e}")

    async def _init_playwright(self):
        try:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            return True
        except ImportError:
            raise RuntimeError("playwright 未安装，请运行: pip install playwright && playwright install chromium")
        except Exception as e:
            raise RuntimeError(f"Playwright 初始化失败: {e}")

    async def start_browser(self, url: str) -> bool:
        try:
            if not self.playwright:
                await self._init_playwright()

            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--window-position=100,100',
                f'--window-size={self.config.window_size[0]},{self.config.window_size[1]}',
                '--start-maximized' if not self.config.window_size else '',
                '--enable-features=NetworkService,NetworkServiceInProcess2',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
            launch_args = [a for a in launch_args if a]

            self.browser = await self.playwright.chromium.launch(
                headless=self.config.headless,
                args=launch_args,
                ignore_default_args=['--enable-automation'],
            )

            self.context = await self.browser.new_context(
                viewport={'width': self.config.window_size[0], 'height': self.config.window_size[1]},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                permissions=['geolocation', 'notifications'],
                accept_downloads=False,
                java_script_enabled=True,
                bypass_csp=True,
                extra_http_headers={
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                },
            )

            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = {runtime: {}};
            """)

            self.page = await self.context.new_page()

            await self.page.route('**/*.png', lambda route: route.abort() if 'ad' in route.request.url.lower() else route.continue_())
            await self.page.route('**/*.gif', lambda route: route.abort() if 'ad' in route.request.url.lower() else route.continue_())

            self.current_url = url
            self.is_running = True
            print(f"[ChromeRecorder] 浏览器已启动，正在加载: {url}")
            self._notify(self.on_status_update, f"正在加载: {url[:50]}...")

            response = await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            if response and response.status >= 400:
                raise Exception(f"页面加载失败: HTTP {response.status}")

            await self.page.wait_for_timeout(2000)
            self._notify(self.on_status_update, "页面加载完成")

            if self.config.auto_record_on_live:
                self.monitor_thread = threading.Thread(target=self._monitor_live_status, daemon=True)
                self.monitor_thread.start()

            return True

        except Exception as e:
            error_msg = f"启动浏览器失败: {e}"
            print(f"[ChromeRecorder] {error_msg}")
            self._notify(self.on_error, error_msg)
            return False

    def _monitor_live_status(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        check_interval = 10
        was_live = False
        
        while self.is_running and not self._stop_event.is_set():
            try:
                is_live_now = loop.run_until_complete(self._check_if_live())
                
                if is_live_now and not was_live:
                    print("[ChromeRecorder] ✅ 检测到直播开始")
                    self._notify(self.on_live_detected)
                    if self.config.auto_record_on_live and not self.is_recording:
                        asyncio.ensure_future(self.start_recording_async())
                    was_live = True
                    
                elif not is_live_now and was_live:
                    print("[ChromeRecorder] ⏸️ 直播已结束或未开始")
                    self._notify(self.on_live_ended)
                    if self.is_recording:
                        asyncio.ensure_future(self.stop_recording_async())
                    was_live = True
                
                elif is_live_now:
                    self._notify(self.on_status_update, "🟢 正在直播")
                else:
                    self._notify(self.on_status_update, "⚪ 等待直播...")

            except Exception as e:
                print(f"[ChromeRecorder] 监控错误: {e}")

            self._stop_event.wait(check_interval)

        if not loop.is_closed():
            loop.close()

    async def _check_if_live(self) -> bool:
        if not self.page:
            return False
            
        try:
            is_live = await self.page.evaluate("""() => {
                const indicators = [
                    '.webcast-interact-container', '.live-player', '[data-module="live"]',
                    '.player-ctrl-btn.is-live', '.room-status-icon.live',
                    '.player-fullscreen', '.live-info', '.bilibili-live-player',
                    '#live-player', 'video[src*="m3u8"]', 'video[src*="flv"]'
                ];
                
                for (const selector of indicators) {
                    if (document.querySelector(selector)) return true;
                }
                
                for (const video of document.querySelectorAll('video')) {
                    if (!video.paused && video.currentTime > 0 && video.readyState > 2) {
                        return true;
                    }
                }
                
                return false;
            }""")
            return bool(is_live)
        except Exception:
            return False

    async def get_anchor_name(self) -> str:
        if not self.page:
            return "未知主播"
            
        try:
            name = await self.page.evaluate("""() => {
                const selectors = [
                    '.anchor-name', '.username', '.host-name', '[data-anchor]',
                    '.dy-account-name', '.Title-ownerName', '.anchorInfo-name',
                    'h1', '[class*="name"]', '[class*="title"]'
                ];
                
                for (const selector of selectors) {
                    const el = document.querySelector(selector);
                    if (el && el.textContent.trim()) {
                        return el.textContent.trim().substring(0, 50);
                    }
                }
                
                return document.title || '未知主播';
            }""")
            return name or "未知主播"
        except Exception:
            return "未知主播"

    async def start_recording_async(self, anchor_name: str = None) -> bool:
        if self.is_recording or not self.page:
            return False
            
        try:
            os.makedirs(self.config.output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_name = "".join(c for c in (anchor_name or "recording") if c.isalnum() or c in '_ -')[:30]
            filename = f"{safe_name}_{timestamp}_chrome.{self.config.output_format}"
            output_file = os.path.join(self.config.output_dir, filename)

            print(f"[ChromeRecorder] 🎬 开始录制画面...")
            
            try:
                await self.page.video().start(
                    path=output_file,
                    size={'width': self.config.window_size[0], 'height': self.config.window_size[1]}
                )
            except Exception as video_error:
                print(f"[ChromeRecorder] 内置视频API不可用，尝试备用方案: {video_error}")
                output_file = await self._start_ffmpeg_recording(output_file)

            self.is_recording = True
            self.start_time = time.time()
            self.frame_count = 0
            self.video_path = output_file
            
            self._notify(self.on_recording_started, output_file)
            self._notify(self.on_status_update, "🔴 正在录制画面...")
            
            print(f"[ChromeRecorder] 录制已启动 → {output_file}")
            return True

        except Exception as e:
            error_msg = f"启动录制失败: {e}"
            print(f"[ChromeRecorder] ❌ {error_msg}")
            self._notify(self.on_error, error_msg)
            return False

    async def _start_ffmpeg_recording(self, output_file: str) -> str:
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-f', 'image2pipe', '-vcodec', 'png',
            '-i', '-',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
            output_file
        ]
        
        self.ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=10**7
        )
        
        self._ffmpeg_output = output_file
        threading.Thread(target=self._screenshot_loop, daemon=True).start()
        
        return output_file

    def _screenshot_loop(self):
        import io
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.is_recording and not self._stop_event.is_set():
            try:
                screenshot_bytes = loop.run_until_complete(self._take_screenshot())
                if screenshot_bytes and self.ffmpeg_process and self.ffmpeg_process.stdin:
                    self.ffmpeg_process.stdin.write(screenshot_bytes)
                    self.ffmpeg_process.stdin.flush()
                    self.frame_count += 1
            except Exception as e:
                print(f"[ChromeRecorder] 截图错误: {e}")
                break
                
            time.sleep(1.0 / self.config.fps)
        
        loop.close()

    async def _take_screenshot(self) -> bytes:
        if self.page:
            try:
                return await self.page.screenshot(type='png', full_page=False)
            except Exception:
                pass
        return b''

    async def stop_recording_async(self) -> Optional[str]:
        if not self.is_recording:
            return None
            
        print("[ChromeRecorder] ⏹️ 正在停止录制...")
        self.is_recording = False
        
        video_file = None
        
        try:
            if hasattr(self, 'ffmpeg_process') and self.ffmpeg_process:
                try:
                    self.ffmpeg_process.stdin.close()
                    self.ffmpeg_process.wait(timeout=15)
                    video_file = getattr(self, '_ffmpeg_output', None)
                except Exception:
                    try:
                        self.ffmpeg_process.kill()
                    except:
                        pass
                finally:
                    self.ffmpeg_process = None
            
            if self.page:
                try:
                    video_file = await self.page.video().stop()
                except Exception:
                    pass

        except Exception as e:
            print(f"[ChromeRecorder] 停止录制错误: {e}")

        duration = time.time() - self.start_time if self.start_time else 0
        final_path = video_file or self.video_path
        
        print(f"\n[ChromeRecorder] ✅ 录制完成:")
        print(f"   文件: {final_path}")
        print(f"   时长: {duration:.1f}秒 ({duration/60:.1f}分钟)")
        print(f"   帧数: {self.frame_count}")
        
        self._notify(self.on_recording_stopped, final_path or "")
        self._notify(self.on_status_update, "⏹️ 录制已停止")
        
        return final_path

    def stop_browser(self):
        print("[ChromeRecorder] 正在关闭浏览器...")
        self.is_running = False
        self._stop_event.set()
        
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=5)
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=3)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            if self.is_recording:
                loop.run_until_complete(self.stop_recording_async())
        except Exception as e:
            print(f"[ChromeRecorder] 关闭时停止录制出错: {e}")

        try:
            if self.context:
                loop.run_until_complete(self.context.close())
            if self.browser:
                loop.run_until_complete(self.browser.close())
            if self.playwright:
                loop.run_until_complete(self.playwright.stop())
        except Exception as e:
            print(f"[ChromeRecorder] 关闭浏览器出错: {e}")
        finally:
            if not loop.is_closed():
                loop.close()

        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        
        print("[ChromeRecorder] 浏览器已关闭")

    def take_screenshot_sync(self, save_path: str = None) -> Optional[str]:
        if not self.page:
            return None
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            if not save_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(self.config.output_dir, f"screenshot_{timestamp}.png")
            
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            
            loop.run_until_complete(self.page.screenshot(path=save_path, full_page=False))
            print(f"[ChromeRecorder] 📸 截图已保存: {save_path}")
            return save_path
        except Exception as e:
            print(f"[ChromeRecorder] 截图失败: {e}")
            return None
        finally:
            loop.close()


class ChromeRecorderManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.recorders = {}
                cls._instance._id_counter = 0
            return cls._instance

    def create_recorder(self, config: ChromeRecorderConfig = None) -> tuple:
        with self._lock:
            self._id_counter += 1
            recorder_id = self._id_counter
            recorder = ChromeLiveRecorder(config)
            self.recorders[recorder_id] = recorder
            return recorder_id, recorder

    def get_recorder(self, recorder_id: int) -> Optional[ChromeLiveRecorder]:
        return self.recorders.get(recorder_id)

    def remove_recorder(self, recorder_id: int):
        with self._lock:
            if recorder_id in self.recorders:
                del self.recorders[recorder_id]

    def stop_all(self):
        for recorder in list(self.recorders.values()):
            try:
                recorder.stop_browser()
            except Exception:
                pass
        self.recorders.clear()


async def quick_record(url: str, output_dir: str = "./downloads", 
                       duration: int = 3600, headless: bool = False) -> str:
    config = ChromeRecorderConfig(
        output_dir=output_dir,
        headless=headless,
        window_size=(1920, 1080),
        auto_record_on_live=True,
        record_timeout=duration
    )
    
    recorder = ChromeLiveRecorder(config)
    
    try:
        success = await recorder.start_browser(url)
        if not success:
            raise Exception("浏览器启动失败")
        
        print("等待直播开始（或手动按 Ctrl+C 停止）...")
        
        await asyncio.wait_for(
            asyncio.Event().wait(),
            timeout=duration
        )
    except asyncio.TimeoutError:
        print("录制超时")
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        if recorder.is_recording:
            await recorder.stop_recording_async()
        recorder.stop_browser()
    
    return recorder.video_path or ""


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python chrome_recorder.py <直播间URL> [输出目录] [时长秒]")
        print("示例: python chrome_recorder.py https://live.douyin.com/example ./downloads 1800")
        sys.exit(1)
    
    url = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "./downloads"
    duration = int(sys.argv[3]) if len(sys.argv) > 3 else 3600
    
    print("=" * 60)
    print("🎬 Chrome 直播画面录制工具")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"输出: {output_dir}")
    print(f"时长: {duration}秒")
    print("=" * 60)
    
    result = asyncio.run(quick_record(url, output_dir, duration))
    print(f"\n✅ 完成! 视频保存到: {result}")
