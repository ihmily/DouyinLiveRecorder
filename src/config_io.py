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

# 配置文件与文件工具模块
#
# 负责：URL 配置行的安全更新与去重（update_file）、删行（delete_line）、主播名自动同步
# （update_anchor_name）、config.ini 读取 + 缺键补写（read_config_value / read_config_bool）、
# 配置数值安全转换（_safe_int / _safe_float）、配置备份（backup_file / backup_file_start）。
#
# main 的模块全局量（config_file / url_config_file / backup_dir / text_encoding /
# file_update_lock / ini_URL_content）一律经 `import main` 在运行时惰性读写：
# `from main import ...` 会形成循环导入，且冻结入口下 main 会被二次执行。


# 段级精确替换：old_str 仅在「等于整行（去行尾换行与首尾空白后）」或「等于行内某个半角/全角
# 逗号分隔段（strip 后）」时才替换，返回重写后的整行（保留原行尾与多逗号），未命中返回 None。
# 不能用整行 str.replace：URL 前缀重叠时（.../room1 与 .../room12）会把别的配置行静默改坏，
# 使用者只在下次「未生效」时才发现。
def _rewrite_line_by_match(text_line: str, old_str: str, new_str: str) -> str | None:
    # 实现下沉在 src/utils.py::rewrite_line_by_segment：utils.replace_url（花椒「地址失效自动
    # 注释」写盘路径）与本模块 update_file 必须同一匹配口径，而反向导入会成环，故实现只能住
    # utils 侧。本函数仅保留原名作薄封装，既有调用点与用例不变。
    return utils.rewrite_line_by_segment(text_line, old_str, new_str)


# 把 file_path 中所有 old_str 替换为 new_str（start_str 非空时给命中行加该前缀，如 "#" 注释掉），
# 顺带去重相同行；返回实际生效的字符串，「失败」（含 old_str 一行未命中）返回 old_str 且不落盘。
# 未命中不得返回 new_str：依赖负信号的调用方（main 的 `update_file(...) or url`、web_api 的
# 「失败返回 old_str」契约）只认返回值，区分不了「未命中」与「替换成功」。
# [历史注] 返回注解由 `str | None` 收窄为 `str`：全部出口恒返回 str（未命中按
# 「负信号」契约返回 old_str，见下），None 分支不存在——旧注解逼调用方做多余判空。
def update_file(file_path: str, old_str: str, new_str: str, start_str: str | None = None) -> str:
    if old_str == new_str and start_str is None:
        return old_str
    with main.file_update_lock:
        file_data: list[str] = []
        # 用 set 做成员判定（原 list 是 O(n)，80+ 房间时退化为 O(N²)）；只记录是否见过，
        # 故天然保持首次出现顺序
        seen: set[str] = set()
        # 是否真的命中过至少一行：必须与 file_data 分开记——去重会让「一行没命中」
        # 在结果文本上完全看不出来，而调用方只认返回值。
        matched = False
        try:
            # newline=""：读写均不做换行符翻译，保留文件原有的 \n / \r\n 风格，
            # 配合下方原子写实现字节级 round-trip（Windows 的 CRLF 不会被改成 LF）
            with open(file_path, "r", encoding=main.text_encoding, newline="") as f:
                for text_line in f:
                    rewritten = _rewrite_line_by_match(text_line, old_str, new_str)
                    if rewritten is not None:
                        matched = True
                        text_line = f"{start_str}{rewritten}" if start_str else rewritten
                    if text_line not in seen:
                        seen.add(text_line)
                        file_data.append(text_line)
        # OSError 必须入组：open() 的 FileNotFoundError/PermissionError（杀软扫描占用、只读挂载）
        # 若不接住，Web 编辑房间端点会以裸 500 收场，而不是按该「负信号 + 重解析裁决」
        # 走；主循环侧也会落入通用 except，与同族 update_anchor_name/delete_line（均捕 OSError）
        # 口径不一。读失败无需快照恢复，返回 old_str 即可。
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
        # old_str 在文件里一行都没命中 → **不落盘**并返回 old_str（与同文件 delete_line 的
        # 「未命中不写文件」同一口径）。否则无谓刷新配置文件 mtime——它正是 GUI/主循环热加载
        # 与备份线程的触发判据；调用方（main.py 的 `url = update_file(...) or url`、web_api
        # 的负信号裁决）也会把「没改到任何东西」读成「已写入」（见上方「未命中不得返回
        # new_str」契约）。注意本判据只看「段级/整行是否命中」，不看内容是否真的变了：
        # `old_str == new_str` 配 `start_str="#"` 的注释形态（main.py 的未知链接注释路径）
        # 内容逐字不变但必须落盘。
        if not matched:
            return old_str
        joined = "".join(file_data)
        # 不用 open(..., "w") 的 truncate+write：读方（主循环、GUI）可能在写入窗口里读到空/半写
        # 文件；改为同目录临时文件 + os.replace（该同族问题）
        if not _atomic_write_text(file_path, joined):
            return old_str
        # 快照推进到本次已落盘内容：后续异常只回滚到最近一次成功修改，而非整个循环开始前的旧值
        main.ini_URL_content = joined
        return new_str


# 原子写文本：同目录临时文件写完后 os.replace 覆盖，读方只会看到旧/新完整内容之一。
# 返回是否成功落盘（False = 写临时文件或 replace 阶段抛 OSError）。
# 唯一实现在 src.utils.atomic_write_text，本函数只是薄封装（沿用原有的 warning 级日志）；
# 可复核：grep -rn "mkstemp" src/ 应只命中 src/utils.py。
def _atomic_write_text(file_path: str, text: str) -> bool:
    ok = utils.atomic_write_text(file_path, text, encoding=main.text_encoding)
    if not ok:
        logger.warning(i18n.tr("原子写失败（已保留原文件）: {file_path}", file_path=file_path))
    return ok


# 备份副本专用原子写：与 _atomic_write_text 的唯一差别是 errors="surrogateescape"。
# 备份读侧用该 errors 把无法解码的字节保留成代理码点，写侧**必须同口径**才能把原字节还原回去——
# 用默认 strict 写会把代理码点判成不可编码并退化成 copy2（宁留明文），用 "replace" 写则把刚才
# 辛苦保住的原字节又换回 U+FFFD，等于修复只做了一半。本函数只服务备份路径，不改变配置主写入口径。
def _atomic_write_redacted(file_path: str, text: str) -> bool:
    ok = utils.atomic_write_text(file_path, text, encoding=main.text_encoding, errors="surrogateescape")
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
        # 原子写：open(..., "w") 直写中途失败会把整份 URL_config.ini 截成空文件——所有房间配置
        # 一次丢失，且这条路径没有 ini_URL_content 的快照恢复兜底。仅在落盘成功时才更新快照，
        # 避免「快照已更新但实际没写成功」让恢复基线失真。
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


# 把 file_path 中删除与 del_line 完全相同的行（delete_all=True 时删除全部匹配行）；
# 返回是否真的删除并落盘成功（False = 未命中 / 读失败 / 原子写失败）。
# 返回值是该契约的一半：调用方（main.py 的重复行清理、web_api 的「删除房间」端点）
# 必须据此决定告警/500，否则删除失败会被回报成成功。
def _same_config_path(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
    # 「这两个路径指向同一份文件」的唯一判据：先 normpath 抹掉 ./ 与重复分隔符、
    # 再 abspath 变成同一基准，Windows 上再 casefold（该平台文件系统大小写不敏感）；
    # 逐字比较会在 Path/分隔符/大小写任一不同处漏判。
    left_abs = os.path.abspath(os.path.normpath(str(left)))
    right_abs = os.path.abspath(os.path.normpath(str(right)))
    if os.name == "nt":
        return left_abs.casefold() == right_abs.casefold()
    return left_abs == right_abs


def delete_line(file_path: str, del_line: str, delete_all: bool = False) -> bool:
    # delete_all=False 时仅删除第一个匹配行
    with main.file_update_lock:
        try:
            # newline="" 与 update_file 一致：默认 universal newlines 会把 \r\n 读成 \n，
            # 而写回不做翻译，于是任意一次删行都会把整个文件的 CRLF 行尾永久改成 LF。
            with open(file_path, "r", encoding=main.text_encoding, newline="") as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError) as e:
            logger.error(i18n.tr("读取 URL 配置失败，跳过删除: {e}", e=e))
            return False
        # 调用方（web_api 的 parse_url_config raw_line、main.py 的 origin_line）读文件时都没传
        # newline=""，传进来的 del_line 恒以 \n 结尾；此处按 newline="" 读到的行是 \r\n 结尾 →
        # 整行精确比较在 CRLF 文件上**恒不成立**，删除退化为永久静默 no-op（面板点「删除」后
        # 房间仍在录）。工作区实际形态即 CRLF（URL_config.ini 14/14 行），Windows 主平台必然命中。
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
            # 未命中不写文件（省掉无谓的原子替换与快照更新）。也刻意不打日志：新增 i18n
            # 模板须同步四语目录，而「删除失败」的用户可见提示归调用方（web_api 端点 / main
            # 主循环）所有，由它们按返回的 False 统一告警——本函数只交回可观测性。
            return False
        # 原 r+truncate 式写在崩溃时会清空整个 URL_config.ini
        joined = "".join(out)
        if not _atomic_write_text(file_path, joined):
            return False
        # 同步 URL 配置快照，与 update_file 保持一致的异常恢复基线
        # 路径必须归一后比较。原先是裸字符串 `==`，而调用方（web_api 的删除房间端点、
        # main.py 的重复行清理）传进来的路径可能是 Path、可能用另一种分隔符、Windows 上大小写
        # 也可能不同——任何一处不逐字相等就恒为 False，于是快照不随删行推进，一次读失败后的
        # 「用快照恢复」会用**删行前的旧内容**把刚删掉的房间写回来。
        if _same_config_path(file_path, main.url_config_file):
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
            # write() 抛 InvalidWriteError（Python 3.14 起），直接写文件会把配置截断损坏。
            # 失败时回滚内存态，避免坏键滞留解析器让后续缺键写回连环失败。
            try:
                buffer = io.StringIO()
                config_parser.write(buffer)
                # 原 open(...,"w") 的 truncate+write 非原子；原子写失败同样要回滚刚 set 进去的默认值
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
# 旧写法 `options.get(read_config_value(...), 兜底)` 对非「是/否」写法**静默**回落到硬编码
# 兜底值（实测致 8 项配置生效值漂移），本函数消除该路径。
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
            # int("1_0") 按 Python 字面量规则合法（=10），用户手误静默变成另一个值；
            # 配置项不接受数字分隔符写法
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
            # 同 _safe_int，拒绝数字分隔符手误
            raise ValueError("underscore in numeric config value")
        result = float(text)
        # nan/inf 静默通过的后果——用户误填 nan 时「磁盘满/阈值」类比较恒为 False，
        # 保护静默失效（nan 与任何值比较均为 False）。非有限值一律告警回默认。
        if not math.isfinite(result):
            raise ValueError("non-finite value")
        return result
    except TypeError, ValueError:
        logger.warning(i18n.tr("配置项数值非法: {value}，使用默认值 {default}", value=repr(value), default=default))
        return default


# 备份内容的凭据脱敏开关。
# config.ini 的 [Cookie]/[Authorization]/[账号密码] 三段是明文凭据，而备份线程每 10 分钟比对
# MD5、一变就复制整份到 backup_config/ 并保留 6 份——同一份凭据在磁盘上常驻 7 处，而备份目录
# 恰是用户最容易整体打包/云同步/发给他人求助的地方。默认在副本里把敏感值替换为 ***（配置项仍在、
# 便于对照排查；恢复时需重新填入凭据）；需要「备份含真实凭据」的用户可设 DLR_BACKUP_KEEP_SECRETS=1 显式放行。
# 判据必须走全仓唯一入口 parse_config_bool：手写 `not in ("1", "true", "yes")` 的 token 集合
# 与之不一致——用户写 `on`/`t`/`y` 想保留明文时会被读成「不保留」、静默按脱敏处理。
# 缺省/空串 default=False（= 不保留明文）→ 取反后仍是「脱敏」，与旧行为逐值等价且覆盖面更全。
def _backup_mask_secrets() -> bool:
    return not parse_config_bool(os.environ.get("DLR_BACKUP_KEEP_SECRETS", ""), False)


# 备份内容的凭据脱敏：按「节/键名命中 **或** 值本身形如凭据」两道判据把敏感值替换为 ***。
# 产物是**归一化**结果（经 ConfigParser 重写：键名小写化、原注释与空行丢失），仅适合对照排查、
# 不适合直接还原。解析失败（非 ini / 编码异常）时返回原文本——不因脱敏失败而丢掉整份备份，
# 但必须显式告警：旧实现静默返回原文，用户以为拿到的是脱敏备份、实际是明文。
# 两道判据缺一不可：只认键名黑名单会滞后于平台命名（MID-N57），仅值形态命中的键会明文进
# backup_config/ 并常驻 6 份副本。_looks_like_secret_value 必须从 src.web_config **同源导入**
# （勿复制第二份判据；web_config 只依赖 stdlib 与 src.config_bool，且这里是函数内延迟导入，不成环）。
# 解析器必须是 **tolerant_config_parser（strict=False）**：默认 strict=True 时 config.ini 一旦出现
# 「同一节内两行同名键」就抛 DuplicateOptionError，被下面的 except 接住后返回未脱敏原文，
# 含明文凭据的整份配置依旧进 backup_config/ 并保留 6 份——而重复键是本仓真实发生过的损坏形态
# （2026-10-17 在本仓 config/config.ini 的 [录制设置] 实测到过）。
def _redact_ini_secrets(text: str) -> str:
    try:
        from src.config_read import tolerant_config_parser
        from src.web_config import _looks_like_secret_value, is_sensitive_item
    except ImportError as e:
        # [2026-10-30 L-07] 旧实现静默返回未脱敏原文，违背本函数上方「解析失败必须显式告警」
        # 的自述——导入失败（打包裁剪/依赖异常）时降级返回原文必须留痕，否则备份侧无法归因。
        logger.warning(
            i18n.tr("脱敏依赖导入失败，本次备份按原文返回（未脱敏）: {type_name}: {e}", type_name=type(e).__name__, e=e)
        )
        return text
    parser = tolerant_config_parser()
    try:
        parser.read_string(text)
    except configparser.Error as e:
        # URL_config.ini 实测没有任何小节（首行即注释行），read_string 恒抛
        # MissingSectionHeaderError：若原样返回未脱敏原文，该文件的每一份备份都是明文。
        # 故对「无小节文件」走整份逐行脱敏通道（见 _redact_plain_lines）：真正的 ini 解析失败
        # 只该丢掉「按节结构判定」这一路能力，不该连值形态脱敏一起放弃。仍然显式告警，
        # 因为逐行通道比按节通道弱（无法用节白名单）。
        logger.warning(
            i18n.tr(
                "配置备份按节解析失败（{e}），已退回逐行值形态脱敏（节白名单不可用），请勿外传",
                e=type(e).__name__,
            )
        )
        return _redact_plain_lines(text)
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


# ①：非 ini / 无小节文件的脱敏通道——逐行过 mask_credentials（值形态 + 键名形态双重覆盖）。
# 为什么不用 ConfigParser：它对无小节文件根本读不进来；而「整份放弃脱敏」等于把凭据红线让给
# 一个解析器的格式要求。为什么保留行尾与行数不变：备份是给用户对照/回滚用的，行结构变了就看不懂了。
def _redact_plain_lines(text: str) -> str:
    from src.utils import mask_credentials

    return "\n".join(mask_credentials(line) for line in text.split("\n"))


# 收紧文件权限为「仅属主可读写」（best-effort）：
# Windows 不支持 POSIX 权限位，os.chmod 只影响只读属性，故失败一律忽略——
# 该步骤是纵深防御，不应因权限设置失败而中断备份或写入流程。
def _harden_permissions(path: str) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# 备份文件名里时间戳的形态：UTC 且带毫秒 + 单调递增序号。三处改动各有各的成因：
#   ① **UTC 而不是 now()**：naive 本地时间在 DST 回落或用户手动回拨时钟时会产出同一串；
#   ② **毫秒**（原 %H-%M-%S 只到秒）：备份线程之外的调用点（Web 面板保存、GUI 保存）也会触发备份，
#      同一秒内两次备份必然同名覆盖，先落的那份内容直接消失；
#   ③ **同毫秒序号**：毫秒也可能撞上，_backup_unique_path 再补 -NN 保证「每次备份一个新文件名」。
_BACKUP_TS_FORMAT = "%Y-%m-%d_%H-%M-%S-%f"
_BACKUP_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}-\d{6})")


# 为本次备份挑一个尚未被占用的文件名：先按时间戳取，撞名就在其后加 -01/-02…
def _backup_unique_path(backup_dir_path: str, base_name: str) -> tuple[str, str]:
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(_BACKUP_TS_FORMAT)
    candidate = f"{base_name}_{stamp}"
    counter = 1
    while os.path.exists(os.path.join(backup_dir_path, candidate)):
        candidate = f"{base_name}_{stamp}-{counter:02d}"
        counter += 1
    return candidate, stamp


# 旋转排序键：**优先解析文件名里的 UTC 时间戳**，解析不出（历史遗留名、用户手工放入的文件）
# 才退回 mtime。原实现只按 getmtime 排——时间戳乱序（跨时区同步、复制/解压保留时间戳、系统时钟回拨）
# 时「最旧的那份」实际是最新的，旋转会**删掉刚生成的那份备份**。解析出的时间戳是 UTC、
# 与本轮新命名同一口径，故新旧文件可混排。
def _backup_sort_key(backup_dir_path: str, name: str) -> tuple[datetime.datetime, float]:
    match = _BACKUP_TS_RE.search(name)
    if match:
        try:
            parsed = datetime.datetime.strptime(match.group(1), _BACKUP_TS_FORMAT).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed, 0.0
    try:
        return (
            datetime.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(backup_dir_path, name)), datetime.timezone.utc
            ),
            1.0,
        )
    except OSError:
        # 见下方：stat 期间文件被删不得让整次备份判失败，退化为「最旧」
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), 2.0


# 备份配置文件到 backup_config 目录；返回是否真的落成了备份（False = 建目录/写入/复制任一环节抛错）。
# 失败必须返回 False 交调用方决定重试：旧签名 `-> None` 且异常全吞，backup_file_start 因而无条件
# 推进 MD5 基线，某次写入失败（磁盘满 / 目标被占用 / 只读挂载）后那份内容就**永久**没有备份。
def _fallback_redacted_copy(file_path: str, backup_file_path: str) -> bool:
    # ②：原子写失败后的第二条脱敏通道——按**字节**读原文、逐行过 mask_credentials、再原子写。
    # 与主通道的区别只是「不做按节结构归一化」，脱敏强度不降级；成功返回 True，失败返回 False
    # 交调用方走最后的 copy2 + .UNMASKED 兜底（宁可留明文备份也不让备份缺失，但必须可识别）。
    try:
        with open(file_path, "rb") as src_f:
            raw = src_f.read()
        text = raw.decode(main.text_encoding, errors="surrogateescape")
        return _atomic_write_redacted(backup_file_path, _redact_plain_lines(text))
    except OSError, UnicodeError:
        return False


def _fallback_unmasked_copy(file_path: str, backup_file_path: str) -> str:
    # ②：所有脱敏写通道都失败时的最后兜底。保留「备份不能缺失」的既有语义，但把文件名加上
    # `.UNMASKED` 后缀并在日志里点名——明文副本必须在文件名层面自证，否则用户会当成脱敏备份外发。
    unmasked_path = backup_file_path if backup_file_path.endswith(".UNMASKED") else backup_file_path + ".UNMASKED"
    _ = shutil.copy2(file_path, unmasked_path)
    logger.warning(
        i18n.tr(
            "配置备份脱敏通道全部失败，已落明文副本（文件名带 .UNMASKED 标记，请勿外传）: {path}",
            path=unmasked_path,
        )
    )
    return unmasked_path


def backup_file(file_path: str, backup_dir_path: str, limit_counts: int = 6) -> bool:
    try:
        if not os.path.exists(backup_dir_path):
            os.makedirs(backup_dir_path)

        backup_file_name, _stamp = _backup_unique_path(backup_dir_path, os.path.basename(file_path))
        backup_file_path = os.path.join(backup_dir_path, backup_file_name).replace("\\", "/")
        # 默认先脱敏再落盘（见 _backup_mask_secrets 说明）
        if _backup_mask_secrets():
            try:
                # 读侧 errors 从 "replace" 改为 "surrogateescape"，与
                # utils.remove_duplicate_lines 同口径。原 "replace" 会把非 UTF-8 字节（外部编辑器存成
                # GBK/UTF-16 的 config.ini）永久换成 U+FFFD 再写进副本——从该备份恢复即得到一份损坏
                # 配置。surrogateescape 把无法解码的字节映射成代理码点，**且写侧必须用同一 errors**
                # 才能还原原字节，故 _atomic_write_text 也显式传了它。
                with open(file_path, "r", encoding=main.text_encoding, errors="surrogateescape") as src_f:
                    content = src_f.read()
                # 备份落盘走 _atomic_write_text——原 open(...,"w") 直写中途崩溃（磁盘满/断电）
                # 会留下半份备份进 6 份轮转，可能恰被用户选来恢复成损坏配置。
                # 写失败时落入下方 except 退回 copy2（宁留明文不丢备份的既有语义）。
                if not _atomic_write_redacted(backup_file_path, _redact_ini_secrets(content)):
                    raise OSError(f"atomic write failed: {backup_file_path}")
            except OSError:
                # 原子写失败时若直接 shutil.copy2，**完全明文**的副本会进 backup_config/
                # （正是用户打包/云同步/求助外发的目录）。改为「按字节流做一次脱敏」再落盘：
                # 读原文 → 逐行脱敏 → 原子写；仍失败才退回 copy2，且副本名加 .UNMASKED
                # 后缀让用户一眼看出这份不能外传（表头逻辑见下方 _fallback_unmasked_copy）。
                if not _fallback_redacted_copy(file_path, backup_file_path):
                    backup_file_path = _fallback_unmasked_copy(file_path, backup_file_path)
        else:
            _ = shutil.copy2(file_path, backup_file_path)
        _harden_permissions(backup_file_path)

        files = os.listdir(backup_dir_path)
        _files = [f for f in files if f.startswith(os.path.basename(file_path))]
        # getmtime 在「listdir 之后、stat 之前文件被别的进程删掉」时抛 FileNotFoundError，
        # 若穿到外层 except，**本次副本明明已落盘**却被判成备份失败（假失败），backup_file_start
        # 因此不推进基线、下一轮重复备份同一份内容。
        # 排序只为挑「最旧的那份来删」；排序键优先取文件名里的 UTC 时间戳（见 _backup_sort_key），
        # 解析不出才回落 mtime，stat 失败退化为「最旧」。
        _files.sort(key=lambda x: _backup_sort_key(backup_dir_path, x))

        while len(_files) > limit_counts:
            oldest_file = _files[0]
            try:
                os.remove(os.path.join(backup_dir_path, oldest_file))
            except OSError as e:
                # 旋转删除为尽力而为：删除失败（沙箱回收站不可用 / 文件被占用）不应使备份整体失败
                logger.warning(i18n.tr("清理过期备份 {oldest_file} 失败（已保留）：{e}", oldest_file=oldest_file, e=e))
                break
            _files = _files[1:]

        # 走到这里说明本次副本已经落盘（旋转删除失败只是多留一份旧备份，不影响本次备份成立，
        # 故上面那圈刻意只 warning + break、不改成 return False）
        return True

    except Exception as e:
        logger.error(i18n.tr("\r备份配置文件 {file_path} 失败：{e}", file_path=file_path, e=e))
        # 第二条不是重复劳动：上面那条只记「现象 + {e}」（模板是既有的，动它会在四语目录里留下
        # 孤儿键），这条记的是该新增的**后果与后续动作**——本轮不推进基线、下一轮同一份内容
        # 还会再试；并按 AGENTS「异常日志必须带异常类型与上下文」补齐异常类型
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
                    # 基线只在备份**真的落盘**后才推进：若无条件推进，一次磁盘满/文件占用就让这份
                    # 配置内容永久失去备份——基线已记成「备份过了」，之后内容不再变化就再也不会
                    # 重试。不推进则下一轮（10 分钟后）仍会再试。
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
        # 守护线程退化成紧循环空转，刷日志并空耗 CPU
        time.sleep(600)
