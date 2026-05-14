# FFmpeg 官方下载方式扩展计划

## 一、概述

为 `ffmpeg_install.py` 的 Windows 平台增加 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) 官方 FFmpeg 构建下载方式。采用**官方源优先、蓝奏云兜底**的策略：先尝试从 gyan.dev 下载，失败后再 fallback 到现有的蓝奏云方式。

## 二、当前状态分析

### 2.1 现有下载流程

```
install_ffmpeg() → install_ffmpeg_windows()
                       ├── get_lanzou_download_link()  # 解析蓝奏云直链
                       ├── requests.get(ffmpeg_url)     # 下载 zip
                       ├── tqdm 进度条
                       ├── unzip_file()                  # 解压到 execute_dir
                       └── 设置 PATH 环境变量
```

### 2.2 关键常量与路径

- `ffmpeg_path = os.path.join(execute_dir, 'ffmpeg')` — ffmpeg.exe 预期位于 `{execute_dir}/ffmpeg/ffmpeg.exe`
- 蓝奏云 zip 内部结构：`ffmpeg/bin/ffmpeg.exe`（直接对应）
- 使用的依赖：`requests`, `tqdm`, `zipfile`, `src.logger`

### 2.3 gyan.dev 官方源特征

- URL: `https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip`（~103 MB，release 稳定版）
- 版本信息: `https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.ver`
- zip 内部结构:
  ```
  ffmpeg-X.Y.Z-essentials_build/
    bin/
      ffmpeg.exe
      ffprobe.exe
      ffplay.exe
    doc/
    presets/
    LICENSE
    README.txt
  ```
- 无需登录、无需解析页面 JS（纯直链，与蓝奏云不同）

## 三、修改方案

### 3.1 修改文件

**仅修改** `/workspace/ffmpeg_install.py`

### 3.2 新增函数

#### `download_ffmpeg_official(url: str, dest_dir: str) -> bool`

负责从官方源下载并安装 FFmpeg：

1. 使用 `requests.get(url, stream=True)` 下载 zip 文件到临时路径
2. 使用 `tqdm` 显示下载进度（复用现有模式）
3. 下载完成后，将 zip 解压到临时目录
4. 定位 zip 内的 `bin/` 子目录（`ffmpeg-*-essentials_build/bin/`）
5. 将 `bin/` 下的所有文件复制/移动到 `{dest_dir}/ffmpeg/` 目录
6. 清理临时文件
7. 设置 `PATH` 环境变量并验证安装

#### `install_ffmpeg_official_windows() -> bool`

封装官方下载入口：

1. 构造官方下载 URL: `https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip`
2. 调用 `download_ffmpeg_official(url, execute_dir)`
3. 返回安装结果

### 3.3 修改现有函数

#### `install_ffmpeg_windows()` — 重构为"官方优先 + 蓝奏云兜底"

```python
def install_ffmpeg_windows():
    # 步骤1: 尝试官方源
    logger.debug("尝试从官方源 (gyan.dev) 下载 FFmpeg...")
    if install_ffmpeg_official_windows():
        return True
    
    # 步骤2: 官方源失败，回退到蓝奏云
    logger.warning("官方源下载失败，回退到蓝奏云下载...")
    # ... 现有蓝奏云逻辑保持不变 ...
```

将现有蓝奏云逻辑提取为内部辅助函数 `_install_ffmpeg_lanzou()`，保持代码清晰。

### 3.4 详细设计：`download_ffmpeg_official`

```python
def download_ffmpeg_official(url: str, dest_dir: str) -> bool:
    """
    从官方源下载 FFmpeg zip 并安装
    
    Args:
        url: 官方下载直链 URL
        dest_dir: 目标目录（ffmpeg 文件夹将创建在此目录下）
    
    Returns:
        bool: 安装是否成功
    """
    import tempfile
    import shutil
    
    try:
        # 1. 下载 zip 到临时文件
        zip_file_path = Path(dest_dir) / 'ffmpeg_official_temp.zip'
        
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total_size = int(response.headers.get('Content-Length', 0))
        
        with tqdm(total=total_size, unit="B", unit_scale=True,
                  ncols=100, desc='Downloading ffmpeg (official)') as t:
            with open(zip_file_path, 'wb') as f:
                for data in response.iter_content(block_size=1024):
                    t.update(len(data))
                    f.write(data)
        
        # 2. 解压到临时目录，找到 bin/ 子目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_file_path, 'r') as zf:
                zf.extractall(tmp_dir)
            
            # 查找 bin 目录（适配不同版本的文件夹名）
            bin_dir = None
            for root, dirs, files in os.walk(tmp_dir):
                if os.path.basename(root) == 'bin':
                    # 检查是否包含 ffmpeg.exe
                    if 'ffmpeg.exe' in files:
                        bin_dir = root
                        break
            
            if bin_dir is None:
                logger.error("官方包中未找到 ffmpeg.exe")
                return False
            
            # 3. 将 bin 目录内容移动到 ffmpeg_path
            ffmpeg_target = os.path.join(dest_dir, 'ffmpeg')
            if os.path.exists(ffmpeg_target):
                shutil.rmtree(ffmpeg_target)
            
            shutil.copytree(bin_dir, ffmpeg_target)
        
        # 4. 清理 zip 文件
        if zip_file_path.exists():
            zip_file_path.unlink()
        
        # 5. 设置 PATH 并验证
        os.environ['PATH'] = ffmpeg_path + os.pathsep + (current_env_path or "")
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if result.returncode == 0:
            logger.debug('FFmpeg (官方源) 安装成功')
            return True
        else:
            logger.error('FFmpeg 官方源安装后验证失败')
            return False
            
    except requests.RequestException as e:
        logger.warning(f"官方源下载失败 (网络错误): {e}")
        return False
    except Exception as e:
        logger.error(f"官方源安装失败: {type(e).__name__} - {e}")
        return False
```

### 3.5 蓝奏云逻辑提取

将现有 `install_ffmpeg_windows()` 中的蓝奏云下载 + 安装逻辑提取为 `_install_ffmpeg_lanzou()` 函数：

```python
def _install_ffmpeg_lanzou() -> bool:
    """使用蓝奏云下载安装 FFmpeg（保留原有逻辑不变）"""
    try:
        logger.debug("从蓝奏云下载 FFmpeg...")
        ffmpeg_url = get_lanzou_download_link('https://wweb.lanzouv.com/iHAc22ly3r3g', 'eots')
        if not ffmpeg_url:
            return False
        
        full_file_name = 'ffmpeg_latest_build_20250124.zip'
        version = 'v20250124'
        zip_file_path = Path(execute_dir) / full_file_name
        
        if not Path(zip_file_path).exists():
            response = requests.get(ffmpeg_url, stream=True)
            total_size = int(response.headers.get('Content-Length', 0))
            with tqdm(total=total_size, unit="B", unit_scale=True,
                      ncols=100, desc=f'Downloading ffmpeg ({version})') as t:
                with open(zip_file_path, 'wb') as f:
                    for data in response.iter_content(1024):
                        t.update(len(data))
                        f.write(data)
        
        unzip_file(zip_file_path, execute_dir)
        os.environ['PATH'] = ffmpeg_path + os.pathsep + (current_env_path or "")
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if result.returncode == 0:
            logger.debug('ffmpeg (蓝奏云) 安装成功')
            return True
        else:
            logger.error('ffmpeg 蓝奏云安装后验证失败')
            return False
    except Exception as e:
        logger.error(f"蓝奏云安装失败: {type(e).__name__} - {e}")
        return False
```

### 3.6 重构后的 `install_ffmpeg_windows()`

```python
def install_ffmpeg_windows() -> bool:
    logger.warning("ffmpeg is not installed.")
    
    # 优先尝试官方源
    if install_ffmpeg_official_windows():
        return True
    
    # 官方源失败，回退到蓝奏云
    logger.warning("官方源不可用，尝试蓝奏云下载...")
    if _install_ffmpeg_lanzou():
        return True
    
    logger.error("所有下载方式均失败，请手动安装 ffmpeg")
    return False
```

## 四、假设与决策

| 项目 | 决定 | 理由 |
|------|------|------|
| 官方源选择 | gyan.dev release essentials (.zip) | FFmpeg 官网推荐，稳定版，zip 格式兼容现有解压逻辑 |
| 版本策略 | 使用 latest release 固定链接（非 git master） | URL 稳定不变，无需解析页面获取动态链接 |
| 回退策略 | 官方失败 → 蓝奏云 | "额外添加"语义，保留现有方式作为后备 |
| macOS/Linux | 不修改 | 已使用 brew/apt/yum 官方包管理器 |
| 目录结构 | 适配 gyan.dev 的 `bin/` 子目录 → 提取到 `ffmpeg/` | 保持与现有 ffmpeg_path 兼容 |
| 临时文件清理 | 使用 `tempfile.TemporaryDirectory` + 手动删除 zip | 避免残留文件 |
| 下载进度 | 复用 tqdm，desc 标注 "(official)" 与蓝奏云区分 | 用户体验一致 |

## 五、代码变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `ffmpeg_install.py` | 新增 `download_ffmpeg_official()` | 通用官方源下载安装函数 |
| `ffmpeg_install.py` | 新增 `install_ffmpeg_official_windows()` | Windows 官方源入口 |
| `ffmpeg_install.py` | 新增 `_install_ffmpeg_lanzou()` | 提取蓝奏云逻辑为独立函数 |
| `ffmpeg_install.py` | 修改 `install_ffmpeg_windows()` | 重构为官方优先+兜底 |
| `ffmpeg_install.py` | 新增 `import tempfile, shutil` | 临时目录和文件操作 |

## 六、验证步骤

1. **语法检查**: `python3 -c "import py_compile; py_compile.compile('ffmpeg_install.py', doraise=True)"`
2. **逻辑审查**: 确认官方源失败时正确 fallback 到蓝奏云，蓝奏云失败时返回 False
3. **导入检查**: 确认 `tempfile` 和 `shutil` 是标准库，无需额外安装依赖
4. **兼容性**: 确认 `main.py` 中 `check_ffmpeg_existence()` → `check_ffmpeg()` → `install_ffmpeg()` 调用链不变