# -*- coding: utf-8 -*-
import configparser
import datetime
import io
import math
import os
import re
import shutil
import time

from loguru import logger

import i18n
import main
from src import utils
from src.config_bool import format_config_bool, parse_config_bool
from src.ffmpeg_proc import _get_error_line

# 配置文件与文件工具（独立模块）
#
# 负责：URL 配置行的安全更新与去重（update_file）、删行（delete_line）、主播名自动同步
# （update_anchor_name）、config.ini 读取 + 缺键补写（read_config_value / read_config_bool）、
# 配置数值安全转换（_safe_int / _safe_float）、配置备份（backup_file / backup_file_start）。
#
# 用到 main 的少量模块全局量（config_file / url_config_file / backup_dir / text_encoding /
# file_update_lock / ini_URL_content），一律经 `import main` 在运行时惰性读写：
# `from main import ...` 会形成循环导入，且冻结入口下 main 会被二次执行。


# 段级精确替换（2026-09-12 审查 6.1）：old_str 仅在「等于整行（去行尾换行与首尾空白后）」
# 或「等于行内某个半角/全角逗号分隔段（strip 后）」时才替换为 new_str；返回重写后的整行文本
# （保留原行尾与多逗号），未命中返回 None。
# 原实现是整行 str.replace，URL 前缀重叠时（.../room1 与 .../room12）会把别的配置行静默改坏，
# 使用者只在下次「未生效」时才发现。
def _rewrite_line_by_match(text_line: str, old_str: str, new_str: str) -> str | None:
    # 2026-09-30（M-18）：实现下沉为 src/utils.py::rewrite_line_by_segment——utils.replace_url
    # （花椒「地址失效自动注释」写盘路径）与本模块 update_file 必须同一匹配口径，而 config_io
    # 依赖 utils、反向导入会成环，故实现只能住在 utils 侧。本函数仅保留原名作薄封装，
    # 既有调用点与用例（tests/test_config_io_update_file.py）不变。
    return utils.rewrite_line_by_segment(text_line, old_str, new_str)


# 把 file_path 中所有 old_str 替换为 new_str（start_str 非空时给命中行加该前缀，如 "#" 注释掉），
# 顺带去重相同行；返回实际生效的字符串（失败时返回 old_str）
# [M-07 2026-10-19 补] 「失败」含「old_str 未命中任何行」：此时不落盘、返回 old_str。
# 旧实现未命中也照样整文件重写并返回 new_str，与「替换成功」同形，依赖负信号的调用方会拿到假成功。
def update_file(file_path: str, old_str: str, new_str: str, start_str: str | None = None) -> str | None:
    if old_str == new_str and start_str is None:
        return old_str
    with main.file_update_lock:
        file_data: list[str] = []
        # 2026-09-12 审查（低危 6.1）：原先用 list 做成员判定是 O(n)，80+ 房间时退化为 O(N²)；
        # 换 set 后仍是 O(1)，且「只记录是否见过」的用法天然保持首次出现顺序
        seen: set[str] = set()
        # M-07（2026-10-19）：是否真的命中过至少一行。必须与 file_data 分开记——去重会让
        # 「一行没命中但内容被重写」这件事在结果文本上完全看不出来，而调用方（main.py 的
        # `update_file(...) or url`、web_api 的 MIN-2243「失败返回 old_str」负信号契约）
        # 只认返回值，区分不了「未命中」与「替换成功」两种形态。
        matched = False
        try:
            # newline=""：读写均不做换行符翻译，保留文件原有的 \n / \r\n 风格，
            # 配合下方原子写实现字节级 round-trip（Windows 的 CRLF 不会被 universal newlines 改成 LF）
            with open(file_path, "r", encoding=main.text_encoding, newline="") as f:
                for text_line in f:
                    rewritten = _rewrite_line_by_match(text_line, old_str, new_str)
                    if rewritten is not None:
                        matched = True
                        text_line = f"{start_str}{rewritten}" if start_str else rewritten
                    if text_line not in seen:
                        seen.add(text_line)
                        file_data.append(text_line)
        # M-12（2026-10-02）：OSError 必须入组——open() 的 FileNotFoundError/PermissionError
        # （Windows 杀软扫描占用、只读挂载）此前直接外抛：Web 编辑房间端点以裸 500 收场而非
        # 按设计「负信号 + 重解析裁决」（web_api.py 的 MIN-2243 注释明确依赖「update_file 失败
        # 时返回 old_str」契约），主循环侧落入通用 except，与同族 update_anchor_name/delete_line
        # （均捕 OSError）口径不一。读失败无需快照恢复，返回 old_str 即可。
        except (RuntimeError, UnicodeDecodeError, OSError) as e:
            logger.error(
                i18n.tr(
                    "错误信息: {type_name}: {e} 发生错误的行数: {get_error_line}",
                    type_name=type(e).__name__,
                    e=e,
                    get_error_line=_get_error_line(e),
                )
            )
            # 读取失败时用导入期快照恢复，避免整份 URL 配置被写成空文件
            if main.ini_URL_content:
                _ = _atomic_write_text(file_path, main.ini_URL_content)
                return old_str
            return old_str
        if not file_data:
            return old_str
        # M-07（2026-10-19）：old_str 在文件里一行都没命中 → **不落盘**并返回 old_str。
        # 旧实现此处会把「原样读回来的内容」再原子重写一遍并返回 new_str，两个后果：
        #   ① 调用方（main.py 的 `url = update_file(...) or url`、web_api 端点按 MIN-2243
        #      「失败返回 old_str」做的负信号裁决）把「没改到任何东西」读成「已写入」，
        #      面板回报成功而配置行其实还是旧的；
        #   ② 无谓地刷新配置文件 mtime、并把 main.ini_URL_content 快照推进到一份「其实没发生
        #      变化」的内容，而 mtime 正是 GUI/主循环热加载与备份线程的触发判据。
        # 与同文件 delete_line 的「未命中不写文件」（SEV-05）保持同一口径。
        # 注意本判据只看「段级/整行是否命中」，不看内容是否真的变了：`old_str == new_str` 配
        # `start_str="#"` 的注释形态（main.py 的未知链接注释路径）内容逐字不变但必须落盘。
        if not matched:
            return old_str
        joined = "".join(file_data)
        # 2026-09-12 审查 6.1：原 open(..., "w") 是 truncate+write 的非原子写，读方（主循环、GUI）
        # 可能在写入窗口里读到空/半写文件；改为同目录临时文件 + os.replace
        if not _atomic_write_text(file_path, joined):
            return old_str
        # 快照推进到本次已落盘内容：后续异常只回滚到最近一次成功修改，而非整个循环开始前的旧值
        main.ini_URL_content = joined
        return new_str


# 原子写文本：同目录临时文件写完后 os.replace 覆盖，读方只会看到旧/新完整内容之一。
# 返回是否成功落盘（False = 写临时文件或 replace 阶段抛 OSError）。
# 真正的写入实现只有一处：src.utils.atomic_write_text；本函数是薄封装，沿用原有的 warning 级日志。
# 可复核判据：
#   grep -rn "mkstemp" src/            # 仅 src/utils.py 命中
#   grep -rn "atomic_write_text" src/  # utils 定义 + config_io/web_config 两个薄封装
#   [历史注] WD-15（2026-09-18）下沉为唯一实现；SEV-2211（2026-09-22）发现 web_config
#   另持一份弱化副本并已删除，故「唯一实现」这一陈述如今才全仓成立。
def _atomic_write_text(file_path: str, text: str) -> bool:
    ok = utils.atomic_write_text(file_path, text, encoding=main.text_encoding)
    if not ok:
        logger.warning(i18n.tr("原子写失败（已保留原文件）: {file_path}", file_path=file_path))
    return ok


# 将 URL 配置文件中指定 URL 所在行的主播名字段更新为 new_name（行内无主播名字段时追加），
# 保留画质段/注释前缀/行尾换行；返回是否发生了变更（未命中/已是目标名/写失败均返回 False）
def update_anchor_name(url: str, new_name: str) -> bool:
    # 主播名自动同步：按 URL 精确定位配置行（段级匹配，避免 URL 前缀相似的行误命中），
    # 持锁读写避免与录制线程的 update_file / Web API 写入并发半写
    if not url or not new_name:
        return False
    with main.file_update_lock:
        if not os.path.exists(main.url_config_file):
            return False
        try:
            # newline=""：读/写均不做换行符翻译，保留文件原有的 \n / \r\n 行尾风格
            with open(main.url_config_file, "r", encoding=main.text_encoding, newline="") as f:
                lines = f.readlines()
        except (RuntimeError, UnicodeDecodeError, OSError) as e:
            logger.error(i18n.tr("读取 URL 配置失败，跳过主播名更新: {e}", e=e))
            return False
        changed = False
        out_lines: list[str] = []
        for raw_line in lines:
            rewritten = _rewrite_anchor_field(raw_line, url, new_name)
            if rewritten is not None:
                changed = True
                out_lines.append(rewritten)
            else:
                out_lines.append(raw_line)
        if not changed:
            return False
        joined = "".join(out_lines)
        # WD-15：原先的 open(..., "w") 直写（truncate+write）中途失败会把整份 URL_config.ini
        # 截成空文件——所有房间配置一次丢失，且这条路径没有 ini_URL_content 的快照恢复兜底。
        # 改原子写后，仅在落盘成功时才更新快照，避免「快照已更新但实际没写成功」让恢复基线失真。
        if not _atomic_write_text(main.url_config_file, joined):
            logger.warning(i18n.tr("主播名写回 URL 配置失败（已忽略，下轮重试）"))
            return False
        # 与 update_file 保持一致的异常恢复基线
        main.ini_URL_content = joined
        return True


# 重写单行配置的主播名字段；行不匹配 URL 或已是目标名时返回 None（无需变更）
def _rewrite_anchor_field(raw_line: str, url: str, new_name: str) -> str | None:
    # 行格式: [画质,]URL[,主播: 名称]，行首 # 表示注释（禁用）——重写时两类前缀全部保留
    stripped = raw_line.rstrip("\r\n")
    eol = raw_line[len(stripped) :]
    # 分离注释前缀（保留原有 # 数量）
    comment_prefix = ""
    body = stripped
    if body.lstrip().startswith("#"):
        idx = body.find("#")
        comment_prefix = body[: idx + 1]
        body = body[idx + 1 :]
    if not body.strip():
        return None
    # 段级 URL 匹配：防止前缀相似（如 /1 与 /12）的 URL 误改他行
    segments = [seg.strip() for seg in re.split(r"[,，]", body)]
    if url not in segments:
        return None
    # 主播名字段取最后一个「主播:」/「主播：」之后的尾段整体替换（名字可含空格）；
    # 全角冒号行统一重写为半角，与 main.py 的行解析约定一致
    idx = max(body.rfind("主播:"), body.rfind("主播："))
    if idx >= 0:
        head = body[:idx].rstrip()
        if body[idx + 3 :].strip() == new_name:
            return None  # 已是目标名，幂等跳过
        rebuilt = f"{head}主播: {new_name}"
    else:
        # 行内无主播名字段：在行尾追加（URL 段原样保留）
        rebuilt = f"{body.rstrip()},主播: {new_name}"
    return f"{comment_prefix}{rebuilt}{eol}"


# 从 file_path 中删除与 del_line 完全相同的行，delete_all=True 时删除全部匹配行；
# 返回是否真的删除并落盘成功（False = 未命中 / 读失败 / 原子写失败）。
# 返回值是 SEV-05 的一部分：调用方（main.py 的重复行清理、web_api 的「删除房间」端点）
# 必须据此决定告警/500，否则删除失败会被回报成成功。
def delete_line(file_path: str, del_line: str, delete_all: bool = False) -> bool:
    # delete_all=False 时仅删除第一个匹配行
    with main.file_update_lock:
        try:
            # MI-11：补 newline=""，与 update_file 一致。默认 universal newlines 会把 \r\n
            # 读成 \n，而写回走 newline="" 不做翻译，于是任意一次删行都会把整个文件的
            # CRLF 行尾永久改成 LF。
            with open(file_path, "r", encoding=main.text_encoding, newline="") as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError) as e:
            logger.error(i18n.tr("读取 URL 配置失败，跳过删除: {e}", e=e))
            return False
        # SEV-05（2026-09-20）：MI-11 只修了写侧，读侧留下反向缺口——本函数所有调用方
        # （web_api 的 parse_url_config raw_line、main.py 的 origin_line）读文件时都没传
        # newline=""，即传进来的 del_line 恒以 \n 结尾；此处按 newline="" 读原文，文件行是
        # \r\n 结尾 → 整行精确比较在 CRLF 文件上**恒不成立**，删除退化为永久静默 no-op，
        # 而旧实现无返回值、调用方无条件回报成功（面板点「删除」后房间仍在录）。
        # 工作区实际形态即 CRLF（URL_config.ini 14/14 行），Windows 主平台必然命中。
        # 现两侧先剥行尾再比较，写出时仍保留各行原始行尾（不做 LF/CRLF 翻译）。
        target = del_line.rstrip("\r\n")
        deleted_one = False
        out: list[str] = []
        for txt_line in lines:
            if txt_line.rstrip("\r\n") == target and (delete_all or not deleted_one):
                deleted_one = True
                continue
            out.append(txt_line)
        if not deleted_one:
            # 未命中不写文件（省掉无谓的原子替换与快照更新）。此处刻意不打日志：新增 i18n
            # 模板须同步四语目录，而「删除失败」的用户可见提示归调用方（web_api 端点 /
            # main 主循环）所有，由它们按返回的 False 统一告警——本函数只交回可观测性。
            return False
        # 2026-09-12 审查 6.5：原 r+truncate 式写在崩溃时会清空整个 URL_config.ini
        joined = "".join(out)
        if not _atomic_write_text(file_path, joined):
            return False
        # 同步 URL 配置快照，与 update_file 保持一致的异常恢复基线
        if file_path == main.url_config_file:
            main.ini_URL_content = joined
        return True


# 从 config_parser 读取 section/option 的值；缺节或缺键时把 default_value 补写回配置文件
# 并返回该默认值。返回值一律为字符串。
def read_config_value(
    config_parser: configparser.RawConfigParser, section: str, option: str, default_value: str | int | float | bool = ""
) -> str:
    try:
        if "录制设置" not in config_parser.sections():
            config_parser.add_section("录制设置")
        if "推送配置" not in config_parser.sections():
            config_parser.add_section("推送配置")
        if "Cookie" not in config_parser.sections():
            config_parser.add_section("Cookie")
        if "Authorization" not in config_parser.sections():
            config_parser.add_section("Authorization")
        if "账号密码" not in config_parser.sections():
            config_parser.add_section("账号密码")
        return config_parser.get(section, option)
    except configparser.NoSectionError, configparser.NoOptionError:
        # 兜底创建 section（白名单外的 section 直接 set 会抛 NoSectionError），
        # 并持 file_update_lock 写回，避免与录制线程的 update_config 并发半写。
        with main.file_update_lock:
            if section not in config_parser.sections():
                config_parser.add_section(section)
            config_parser.set(section, option, str(default_value))
            # 写回失败（瞬时占用 / 并发进程 / 编辑器锁 / 只读挂载）只记 warning 并返回默认值，
            # 不再抛出——否则「任何缺键 + 配置不可写」会让整个 app 在 import 阶段崩溃；
            # 与 backup_file 的 best-effort 模式保持一致。
            # 先在内存里完整序列化、成功后才落盘：键名含 = / : 等 configparser 分隔符时
            # write() 抛 InvalidWriteError（Python 3.14 起；3.13 是静默写成功），
            # 直接写文件会把配置截断损坏。失败时回滚内存态，避免坏键滞留解析器
            # 让后续缺键写回连环失败。
            try:
                buffer = io.StringIO()
                config_parser.write(buffer)
                # 2026-09-12 审查 6.5：原 open(...,"w") 的 truncate+write 非原子；
                # 原子写失败同样要回滚刚 set 进去的默认值
                if not _atomic_write_text(main.config_file, buffer.getvalue()):
                    _ = config_parser.remove_option(section, option)
            except (OSError, configparser.Error) as e:
                logger.warning(
                    i18n.tr(
                        "配置项 {section}/{option} 缺省值写回失败（已忽略）: {type_name}: {e}",
                        section=section,
                        option=option,
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
                _ = config_parser.remove_option(section, option)
        return str(default_value)


# 读取布尔型配置项（全仓统一入口）：语义 = read_config_value + parse_config_bool。
# 键缺失时按 default 补写回配置文件（「是」/「否」，与 read_config_value 的自愈语义一致），
# 已存在的值原样解析、不被覆写——识别 是/否、true/false、1/0、yes/no、on/off（大小写不敏感），
# 无法识别的值返回 default。
# 取代旧写法 `options.get(read_config_value(...), 兜底)`：那种字典查表对非「是/否」写法**静默**
# 回落到硬编码兜底值（2026-09-17 实测致 8 项配置生效值漂移），本函数消除该路径。
def read_config_bool(
    config_parser: configparser.RawConfigParser, section: str, option: str, default: bool = False
) -> bool:
    # default 兼作「缺键时的补写值」与「无法识别时的返回值」
    raw = read_config_value(config_parser, section, option, format_config_bool(default))
    return parse_config_bool(raw, default)


# 把配置项 value 安全转为 int；为空或非法时打印告警并返回 default
def _safe_int(value: str | None, default: int) -> int:
    # 非法值必须告警后回退：直接 int() 抛 ValueError 会让 main() 主循环整体崩溃
    try:
        text = str(value).strip()
        if "_" in text:
            # L-35（2026-10-02）：int("1_0") 按 Python 字面量规则合法（=10），用户手误静默变成
            # 另一个值；配置项不接受数字分隔符写法
            raise ValueError("underscore in numeric config value")
        return int(text)
    except TypeError, ValueError:
        logger.warning(i18n.tr("配置项数值非法: {value}，使用默认值 {default}", value=repr(value), default=default))
        return default


# 把配置项 value 安全转为 float；为空或非法时打印告警并返回 default
def _safe_float(value: str | None, default: float) -> float:
    try:
        text = str(value).strip()
        if "_" in text:
            # L-35：同 _safe_int，拒绝数字分隔符手误
            raise ValueError("underscore in numeric config value")
        result = float(text)
        # L-35（2026-10-02）：nan/inf 静默通过的后果——用户误填 nan 时「磁盘满/阈值」类比较
        # 恒为 False，保护静默失效（nan 与任何值比较均为 False）。非有限值一律告警回默认。
        if not math.isfinite(result):
            raise ValueError("non-finite value")
        return result
    except TypeError, ValueError:
        logger.warning(i18n.tr("配置项数值非法: {value}，使用默认值 {default}", value=repr(value), default=default))
        return default


# CR-07：备份内容的凭据脱敏开关。
# 背景：config.ini 的 [Cookie]/[Authorization]/[账号密码] 三段是明文凭据，而备份线程每 10 分钟
# 比对 MD5、一变就 shutil.copy2 整份文件到 backup_config/ 并保留 6 份——同一份凭据在磁盘上
# 常驻 7 处，而备份目录恰是用户最容易整体打包/云同步/发给他人求助的地方。
# 默认在副本里把敏感值替换为 ***（配置项仍在、便于对照排查；恢复时需重新填入凭据）。
# 需要「备份含真实凭据」以完整还原的用户可设 DLR_BACKUP_KEEP_SECRETS=1 显式放行。
def _backup_mask_secrets() -> bool:
    # L-55（2026-10-19）：此处原为手写 `not in ("1", "true", "yes")`，与全仓唯一入口
    # src.config_bool.parse_config_bool 的 token 集合不一致——用户写 `on`/`t`/`y` 想保留明文备份时，
    # 旧判据把它们读成「不保留」，静默按脱敏处理（开与关写反却无任何提示）。
    # 缺省/空串 default=False（= 不保留明文）→ 取反后仍是「脱敏」，与旧行为逐值等价且覆盖面更全。
    return not parse_config_bool(os.environ.get("DLR_BACKUP_KEEP_SECRETS", ""), False)


# 备份内容的凭据脱敏：按「节/键名命中 **或** 值本身形如凭据」两道判据把敏感值替换为 ***。
# [历史注] L-33（2026-10-02）更正：本段原声称「节名与键名保留」并暗示产物与原文形态一致，
# 实际经 ConfigParser 重写后 optionxform 小写化键名、原注释与空行全部丢失——脱敏备份是
# **归一化产物**，仅适合对照排查、不适合直接还原。解析失败（非 ini / 编码异常）时返回
# 原文本——不因脱敏失败而丢掉整份备份。
# MID-N57（2026-09-21）：此前只接了 is_sensitive_item 一道判据，与面板侧 read_config_safe
# （web_config.py CR-10）的双口径分叉——键名黑名单天然滞后于平台命名，仅值形态命中的键会明文
# 进 backup_config/ 并常驻 6 份副本。
# _looks_like_secret_value 必须从 src.web_config **同源导入**（勿复制第二份判据）：web_config 只依赖
# stdlib 与 src.config_bool，且这里是函数内延迟导入，不构成导入环。
#
# [S-02 2026-10-19] 解析器必须是 **tolerant_config_parser（strict=False）**，不能用
# `configparser.ConfigParser(interpolation=None)`：该构造默认 strict=True，config.ini 一旦出现
# 「同一节内两行同名键」就抛 DuplicateOptionError，被下面的 except 接住后**返回未脱敏原文**，
# 于是含明文 [Cookie]/[Authorization]/账号密码 的整份配置被写进 backup_config/ 并保留 6 份。
# 这不是假想形态——src/config_read.py 的注释记载 2026-10-17 在本仓 config/config.ini 的
# [录制设置] 实测到过重复键，即「恰恰是真实发生过的那一种配置损坏形态会让脱敏整条链路静默失效」。
# 解析**仍**失败时（如 URL_config.ini 全篇注释 → MissingSectionHeaderError）保留原文以保证
# 备份不丢，但必须显式告警——旧实现静默返回原文，用户以为默认是脱敏备份、实际拿到明文。
def _redact_ini_secrets(text: str) -> str:
    try:
        from src.config_read import tolerant_config_parser
        from src.web_config import _looks_like_secret_value, is_sensitive_item
    except ImportError:
        return text
    parser = tolerant_config_parser()
    try:
        parser.read_string(text)
    except configparser.Error as e:
        # 未脱敏即落盘是本仓凭据红线的例外，只能发生在「这份内容根本不是 ini」的形态上，
        # 因此必须点名到类型与文件性质，不能像旧实现那样静默放行。
        logger.warning(
            i18n.tr(
                "配置备份未能脱敏（解析失败：{e}），本次副本可能包含明文凭据，请勿外传",
                e=type(e).__name__,
            )
        )
        return text
    out = io.StringIO()
    for section in parser.sections():
        _ = out.write(f"[{section}]\n")
        for key, value in parser.items(section):
            if value.strip() and (is_sensitive_item(section, key) or _looks_like_secret_value(value)):
                _ = out.write(f"{key} = ***\n")
            else:
                _ = out.write(f"{key} = {value}\n")
        _ = out.write("\n")
    return out.getvalue()


# 收紧文件权限为「仅属主可读写」（best-effort）：
# Windows 不支持 POSIX 权限位，os.chmod 只影响只读属性，故失败一律忽略——
# 该步骤是纵深防御，不应因权限设置失败而中断备份或写入流程。
def _harden_permissions(path: str) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# 备份配置文件到 backup_config 目录；返回是否真的落成了备份（False = 建目录/写入/复制任一环节抛错）。
# [M-10 2026-10-19 补] 旧签名是 `-> None` 且异常全吞，backup_file_start 因此无条件推进 MD5 基线：
# 某一次写入失败（磁盘满 / 目标被占用 / 只读挂载）后，那份内容的版本就**永久**没有备份，
# 而基线已把它记成「已备份」——正是备份机制要避免的形态。现在失败一律返回 False 交调用方决定重试。
def backup_file(file_path: str, backup_dir_path: str, limit_counts: int = 6) -> bool:
    try:
        if not os.path.exists(backup_dir_path):
            os.makedirs(backup_dir_path)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file_name = os.path.basename(file_path) + "_" + timestamp
        backup_file_path = os.path.join(backup_dir_path, backup_file_name).replace("\\", "/")
        # CR-07：默认先脱敏再落盘（见 _backup_mask_secrets 说明）
        if _backup_mask_secrets():
            try:
                with open(file_path, "r", encoding=main.text_encoding, errors="replace") as src_f:
                    content = src_f.read()
                # L-34（2026-10-02）：备份落盘改走 _atomic_write_text——原 open(...,"w") 直写
                # 在中途崩溃（磁盘满/断电）时留下半份备份进 6 份轮转，可能恰被用户选来恢复
                # 成损坏配置。写失败时落入下方 except 退回 copy2（宁留明文不丢备份的既有语义）。
                if not _atomic_write_text(backup_file_path, _redact_ini_secrets(content)):
                    raise OSError(f"atomic write failed: {backup_file_path}")
            except OSError:
                # 读不到就退回原样复制，宁可留下明文备份也不要备份缺失
                _ = shutil.copy2(file_path, backup_file_path)
        else:
            _ = shutil.copy2(file_path, backup_file_path)
        _harden_permissions(backup_file_path)

        files = os.listdir(backup_dir_path)
        _files = [f for f in files if f.startswith(os.path.basename(file_path))]
        # L-54（2026-10-19）：getmtime 在「listdir 之后、stat 之前文件被别的进程删掉」时抛
        # FileNotFoundError（OSError 子类）。旧实现让它穿到外层 except，于是**本次副本明明已落盘**
        # 却被判成备份失败（假失败），backup_file_start 因此不推进基线、下一轮重复备份同一份内容。
        # 排序只是挑「最旧的那份来删」，退化为按名排序（备份名含时间戳、字典序即时间序）不会
        # 删错目标，故此处按尽力而为处理。
        try:
            _files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir_path, x)))
        except OSError:
            _files.sort()

        while len(_files) > limit_counts:
            oldest_file = _files[0]
            try:
                os.remove(os.path.join(backup_dir_path, oldest_file))
            except OSError as e:
                # 旋转删除为尽力而为：删除失败（沙箱回收站不可用 / 文件被占用）不应使备份整体失败
                logger.warning(i18n.tr("清理过期备份 {oldest_file} 失败（已保留）：{e}", oldest_file=oldest_file, e=e))
                break
            _files = _files[1:]

        # M-10：走到这里说明本次副本已经落盘（旋转删除失败只是多留一份旧备份，不影响本次备份成立，
        # 故上面那圈刻意只 warning + break、不改成 return False）
        return True

    except Exception as e:
        logger.error(i18n.tr("\r备份配置文件 {file_path} 失败：{e}", file_path=file_path, e=e))
        # 第二条不是重复劳动：上面那条只记「现象 + {e}」（模板是既有的，动它会在四语目录里留下
        # 孤儿键），这条记的是 M-10 新增的**后果与后续动作**——本轮不推进基线、下一轮同一份内容
        # 还会再试一次；并按 AGENTS「异常日志必须带异常类型与上下文」补齐异常类型
        # （中文 Windows 下部分异常 str() 为空，只打 {e} 会落成一条空白行）。
        logger.warning(
            i18n.tr(
                "配置文件备份未成功，本轮不更新备份基线（下轮将重试）: {file_path} - {type_name}: {e}",
                file_path=file_path,
                type_name=type(e).__name__,
                e=e,
            )
        )
        return False


# 守护线程主体：每 10 分钟比对 config.ini / URL_config.ini 的 MD5，仅在内容变化时备份
# （首轮 MD5 与初值 "" 必然不同，故启动即落一份备份）；无入参，死循环不返回
def backup_file_start() -> None:
    config_md5 = ""
    url_config_md5 = ""

    while True:
        try:
            if os.path.exists(main.config_file):
                new_config_md5 = utils.check_md5(main.config_file)
                if new_config_md5 != config_md5:
                    # M-10（2026-10-19）：基线只在备份**真的落盘**后才推进。旧写法无条件推进，
                    # 于是一次磁盘满/文件占用就让这份配置内容永久失去备份——基线已记成「备份过了」，
                    # 之后内容不再变化就再也不会重试。不推进则下一轮（10 分钟后）仍会再试一次。
                    if backup_file(main.config_file, main.backup_dir):
                        config_md5 = new_config_md5

            if os.path.exists(main.url_config_file):
                new_url_config_md5 = utils.check_md5(main.url_config_file)
                if new_url_config_md5 != url_config_md5:
                    # 同上：URL_config.ini 侧同一条契约
                    if backup_file(main.url_config_file, main.backup_dir):
                        url_config_md5 = new_url_config_md5
        except Exception as e:
            logger.error(i18n.tr("备份配置文件失败, 错误信息: {e}", e=e))
        # sleep 必须在 try 外：否则 check_md5/backup 持续失败时异常分支不等待，
        # 守护线程退化成紧循环空转，疯狂刷日志并空耗 CPU
        time.sleep(600)
