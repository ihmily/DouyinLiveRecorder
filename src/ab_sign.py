# -*- encoding: utf-8 -*-
# A-Bogus 签名算法（抖音 web 端请求参数签名）——纯 Python 复刻线上 JS 逆向版本。
# 结构：bb 字节串 = RC4( SM3 双重散列(url_search_params/suffix/ua) + 时间戳/配置/环境字节 )，
# 再与 12 字节随机前缀拼接后经魔改 base64（s4 表）编码、尾补 '='。
# SM3 部分是标准实现；「魔改」集中在 result_encrypt 的编码表与 gener_random 的位交错，
# 这些常量/表值任何一个改动都会导致签名被拒。
import math
import os
import secrets
import time
from typing import cast

from src.config_bool import parse_config_bool


def rc4_encrypt(plaintext: str, key: str) -> str:
    # 标准 RC4（KSA+PRGA），无魔改；plaintext/key 每字符承载一个原始字节
    s = list(range(256))

    # KSA：用 key 字节循环置换状态数组 S
    j = 0
    for i in range(256):
        j = (j + s[i] + ord(key[i % len(key)])) % 256
        s[i], s[j] = s[j], s[i]

    # PRGA：逐字节生成密钥流并与明文 XOR
    i = j = 0
    result: list[str] = []
    for char in plaintext:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        t = (s[i] + s[j]) % 256
        result.append(chr(s[t] ^ ord(char)))

    return "".join(result)


def left_rotate(x: int, n: int) -> int:
    # 32 位整数循环左移
    n %= 32
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def get_t_j(j: int) -> int:
    # SM3 轮常量 T(j)：j<16 取 0x79CC4519、16<=j<64 取 0x7A879D8A，越界即非法入参
    if 0 <= j < 16:
        return 2043430169  # 0x79CC4519
    elif 16 <= j < 64:
        return 2055708042  # 0x7A879D8A
    else:
        raise ValueError("invalid j for constant Tj")


def ff_j(j: int, x: int, y: int, z: int) -> int:
    # SM3 布尔函数 FF(j)：j<16 取三变量异或，j>=16 取多数函数（与 GG 的分支不同）
    if 0 <= j < 16:
        return (x ^ y ^ z) & 0xFFFFFFFF
    elif 16 <= j < 64:
        return ((x & y) | (x & z) | (y & z)) & 0xFFFFFFFF
    else:
        raise ValueError("invalid j for bool function FF")


def gg_j(j: int, x: int, y: int, z: int) -> int:
    # SM3 布尔函数 GG(j)，j>=16 分支带 ~x 取反（FF 没有）
    # SM3 标准：j<16 → x^y^z；j>=16 → (x&y)|(~x&z)
    if 0 <= j < 16:
        return (x ^ y ^ z) & 0xFFFFFFFF
    elif 16 <= j < 64:
        return ((x & y) | ((~x & 0xFFFFFFFF) & z)) & 0xFFFFFFFF
    else:
        raise ValueError("invalid j for bool function GG")


class SM3:
    # SM3 密码哈希标准的纯 Python 实现；A-Bogus 以 sm3.sum(sm3.sum(x)) 双重散列取摘要
    def __init__(self) -> None:
        # 初始化 SM3 算法常量与初始值
        self.reg: list[int] = []
        self.chunk: list[int] = []
        self.size: int = 0
        self.reset()

    def reset(self) -> None:
        # SM3 标准 IV；历史注：旧实现寄存器值曾取错，修正为与 JS 参考版一致
        self.reg = [1937774191, 1226093241, 388252375, 3666478592, 2842636476, 372324522, 3817729613, 2969243214]
        self.chunk = []
        self.size = 0

    def write(self, data: str | list[int]) -> None:
        # 将输入转换为字节数组
        if isinstance(data, str):
            # 直接转换为UTF-8字节列表
            a: list[int] = list(data.encode("utf-8"))
        else:
            a = data

        self.size += len(a)
        f = 64 - len(self.chunk)

        if len(a) < f:
            # 如果数据长度小于剩余空间，直接添加
            self.chunk.extend(a)
        else:
            # 否则分块处理
            self.chunk.extend(a[:f])

            while len(self.chunk) >= 64:
                self._compress(self.chunk)
                if f < len(a):
                    self.chunk = a[f : min(f + 64, len(a))]
                else:
                    self.chunk = []
                f += 64

    def _fill(self) -> None:
        # 计算比特长度
        bit_length = 8 * self.size

        # 添加填充位
        padding_pos = len(self.chunk)
        self.chunk.append(0x80)
        padding_pos = (padding_pos + 1) % 64

        # 如果剩余空间不足8字节，则填充到下一个块
        if 64 - padding_pos < 8:
            padding_pos -= 64

        # 填充0直到剩余8字节用于存储长度
        while padding_pos < 56:
            self.chunk.append(0)
            padding_pos += 1

        # 添加消息长度（高32位）
        high_bits = bit_length // 4294967296
        for i in range(4):
            self.chunk.append((high_bits >> (8 * (3 - i))) & 0xFF)

        # 添加消息长度（低32位）
        for i in range(4):
            self.chunk.append((bit_length >> (8 * (3 - i))) & 0xFF)

    def _compress(self, data: list[int]) -> None:
        # SM3 压缩函数（单块处理）
        if len(data) < 64:
            raise ValueError("compress error: not enough data")
        else:
            # 消息扩展
            w = [0] * 132

            # 将字节数组转换为字
            for t in range(16):
                w[t] = (data[4 * t] << 24) | (data[4 * t + 1] << 16) | (data[4 * t + 2] << 8) | data[4 * t + 3]
                w[t] &= 0xFFFFFFFF

            # 消息扩展
            for j in range(16, 68):
                a = w[j - 16] ^ w[j - 9] ^ left_rotate(w[j - 3], 15)
                a = a ^ left_rotate(a, 15) ^ left_rotate(a, 23)
                w[j] = (a ^ left_rotate(w[j - 13], 7) ^ w[j - 6]) & 0xFFFFFFFF

            # 计算w'
            for j in range(64):
                w[j + 68] = (w[j] ^ w[j + 4]) & 0xFFFFFFFF

            # 压缩
            a, b, c, d, e, f, g, h = self.reg

            for j in range(64):
                ss1 = left_rotate((left_rotate(a, 12) + e + left_rotate(get_t_j(j), j)) & 0xFFFFFFFF, 7)
                ss2 = ss1 ^ left_rotate(a, 12)
                tt1 = (ff_j(j, a, b, c) + d + ss2 + w[j + 68]) & 0xFFFFFFFF
                tt2 = (gg_j(j, e, f, g) + h + ss1 + w[j]) & 0xFFFFFFFF

                d = c
                c = left_rotate(b, 9)
                b = a
                a = tt1
                h = g
                g = left_rotate(f, 19)
                f = e
                e = (tt2 ^ left_rotate(tt2, 9) ^ left_rotate(tt2, 17)) & 0xFFFFFFFF

            # 更新寄存器
            self.reg[0] ^= a
            self.reg[1] ^= b
            self.reg[2] ^= c
            self.reg[3] ^= d
            self.reg[4] ^= e
            self.reg[5] ^= f
            self.reg[6] ^= g
            self.reg[7] ^= h

    def sum(self, data: str | list[int] | None = None, output_format: str | None = None) -> str | list[int]:
        # 出一轮摘要：填充 + 分块压缩后返回 hex 串或 32 字节数组；
        # data 为 None 时对已累计内容续算（流式接口），否则先重置再一次性写入。
        # 如果提供了输入，则重置并写入
        if data is not None:
            self.reset()
            self.write(data)

        self._fill()

        # 分块压缩
        for f in range(0, len(self.chunk), 64):
            self._compress(self.chunk[f : f + 64])

        result: str | list[int]
        if output_format == "hex":
            # 十六进制输出
            result = "".join(f"{val:08x}" for val in self.reg)
        else:
            # 字节数组输出
            result = []
            for f in range(8):
                c = self.reg[f]
                result.append((c >> 24) & 0xFF)
                result.append((c >> 16) & 0xFF)
                result.append((c >> 8) & 0xFF)
                result.append(c & 0xFF)

        self.reset()
        return result


def result_encrypt(long_str: str, num: str = "s4") -> str:
    # 魔改base64编码表
    encoding_tables = {
        "s0": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",
        "s1": "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s2": "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s3": "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe",
        "s4": "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe",
    }

    # 位移常量
    masks = [16515072, 258048, 4032, 63]  # 对应 0, 1, 2 的掩码，添加63作为第四个掩码
    shifts = [18, 12, 6, 0]  # 对应的位移量

    encoding_table = encoding_tables[num]

    result = ""
    round_num = 0
    long_int = get_long_int(round_num, long_str)

    total_chars = math.ceil(len(long_str) / 3 * 4)

    for i in range(total_chars):
        # 每4个字符处理一组3字节
        if i // 4 != round_num:
            round_num += 1
            long_int = get_long_int(round_num, long_str)

        # 计算当前位置的索引
        index = i % 4

        # 使用掩码和位移提取6位值
        char_index = (long_int & masks[index]) >> shifts[index]

        result += encoding_table[char_index]

    return result


def get_long_int(round_num: int, long_str: str) -> int:
    # 将字节序列转为长整型
    round_num = round_num * 3

    # 获取字符串中的字符，如果超出范围则使用0
    char1 = ord(long_str[round_num]) if round_num < len(long_str) else 0
    char2 = ord(long_str[round_num + 1]) if round_num + 1 < len(long_str) else 0
    char3 = ord(long_str[round_num + 2]) if round_num + 2 < len(long_str) else 0

    return (char1 << 16) | (char2 << 8) | char3


def gener_random(random_num: int, option: list[int]) -> list[int]:
    # 生成随机字节序列（用于 A-Bogus 参数）
    byte1 = random_num & 255
    byte2 = (random_num >> 8) & 255

    return [
        (byte1 & 170) | (option[0] & 85),  # 偶数位与option[0]的奇数位合并
        (byte1 & 85) | (option[0] & 170),  # 奇数位与option[0]的偶数位合并
        (byte2 & 170) | (option[1] & 85),  # 偶数位与option[1]的奇数位合并
        (byte2 & 85) | (option[1] & 170),  # 奇数位与option[1]的偶数位合并
    ]


def generate_random_str() -> str:
    # 生成 A-Bogus 的 12 字节随机前缀（三组 gener_random 合并）；每个字符承载一个
    # 原始字节，上层 result_encrypt 直接按 ord() 取字节、不经任何文本编码。
    #
    # 2026-09-12 修复（CODE_REVIEW_FIX_1 F-19）：原使用与 JS 版本一致的固定值
    # [0.123456789, 0.987654321, 0.555555555]——所有请求的签名前缀完全相同，
    # 服务端可据此对「同前缀签名」做请求指纹聚类，把本项目流量一锅端。
    # 改为每次调用真随机（值域与原实现一致：[0,1) 浮点 ×10000 取整参与位合并，
    # 输出长度与字节结构不变，不影响签名格式兼容性）。
    #
    # 回退开关：个别平台若对「随机段」有值域/一致性校验导致签名被拒，可设
    # 环境变量 DLR_AB_SIGN_FIXED_RANDOM=1 回退到固定值（保持旧行为），便于
    # 定位问题；默认真随机。
    # L-24（2026-10-19）：真随机改走 secrets。`random.random()` 是 Mersenne Twister，观测约
    # 624 个 32-bit 输出即可恢复内部状态并预测后续前缀——而本函数的目的正是「让服务端无法把
    # 同前缀签名聚成一类流量」，可预测的前缀等于把这条防线交还对方。取值域仍是 [0,1) 浮点，
    # 下游 ×10000 取整与位合并逐字不变，签名格式兼容性不受影响。
    # L-55 同族：布尔开关也一并回落到全仓唯一入口 parse_config_bool（原手写 token 集合不认 on/t/y）。
    if parse_config_bool(os.environ.get("DLR_AB_SIGN_FIXED_RANDOM", ""), False):
        random_values = [0.123456789, 0.987654321, 0.555555555]
    else:
        random_values = [secrets.randbelow(10**9) / 1e9 for _ in range(3)]

    # 生成三组随机字节并合并
    random_bytes: list[int] = []
    random_bytes.extend(gener_random(int(random_values[0] * 10000), [3, 45]))
    random_bytes.extend(gener_random(int(random_values[1] * 10000), [1, 0]))
    random_bytes.extend(gener_random(int(random_values[2] * 10000), [1, 5]))

    return "".join(chr(b) for b in random_bytes)


def generate_rc4_bb_str(
    url_search_params: str,
    user_agent: str,
    window_env_str: str,
    suffix: str = "cus",
    arguments: list[int] | None = None,
) -> str:
    # 生成 RC4 加密所需的 bb 字符串
    if arguments is None:
        arguments = [0, 1, 14]

    sm3 = SM3()
    start_time = int(time.time() * 1000)

    # 三次加密处理
    # 1: url_search_params两次sm3之的结果
    url_search_params_list = cast(list[int], sm3.sum(sm3.sum(url_search_params + suffix)))
    # 2: 对后缀两次sm3之的结果
    cus = cast(list[int], sm3.sum(sm3.sum(suffix)))
    # 3: 对ua处理之后的结果
    ua_key = chr(0) + chr(1) + chr(14)  # [1/256, 1, 14]
    ua = cast(list[int], sm3.sum(result_encrypt(rc4_encrypt(user_agent, ua_key), "s3")))

    end_time = start_time + 100

    # 构建配置对象
    # b15 为嵌套配置 dict（含 aid/pageId 等字段），单独存放；
    # b 仅存 int 值，使所有 b[k] 读取处类型为 int，无需 cast。
    b15: dict[str, object] = {
        "aid": 6383,
        "pageId": 110624,
        "boe": False,
        "ddrt": 7,
        "paths": {"include": [{} for _ in range(7)], "exclude": []},
        "track": {"mode": 0, "delay": 300, "paths": []},
        "dump": True,
        "rpU": "hwj",
    }
    b: dict[int, int] = {
        8: 3,
        10: end_time,
        16: start_time,
        18: 44,
    }

    def split_to_bytes(num: int) -> list[int]:
        # 将长整型按字节切分
        return [(num >> 24) & 255, (num >> 16) & 255, (num >> 8) & 255, num & 255]

    # 处理时间戳
    start_time_bytes = split_to_bytes(b[16])
    b[20] = start_time_bytes[0]
    b[21] = start_time_bytes[1]
    b[22] = start_time_bytes[2]
    b[23] = start_time_bytes[3]
    b[24] = int(b[16] / 256 / 256 / 256 / 256) & 255
    b[25] = int(b[16] / 256 / 256 / 256 / 256 / 256) & 255

    # 处理Arguments参数
    arg0_bytes = split_to_bytes(arguments[0])
    b[26] = arg0_bytes[0]
    b[27] = arg0_bytes[1]
    b[28] = arg0_bytes[2]
    b[29] = arg0_bytes[3]

    b[30] = int(arguments[1] / 256) & 255
    b[31] = (arguments[1] % 256) & 255

    arg1_bytes = split_to_bytes(arguments[1])
    b[32] = arg1_bytes[0]
    b[33] = arg1_bytes[1]

    arg2_bytes = split_to_bytes(arguments[2])
    b[34] = arg2_bytes[0]
    b[35] = arg2_bytes[1]
    b[36] = arg2_bytes[2]
    b[37] = arg2_bytes[3]

    # 处理加密结果
    b[38] = url_search_params_list[21]
    b[39] = url_search_params_list[22]
    b[40] = cus[21]
    b[41] = cus[22]
    b[42] = ua[23]
    b[43] = ua[24]

    # 处理结束时间
    end_time_bytes = split_to_bytes(b[10])
    b[44] = end_time_bytes[0]
    b[45] = end_time_bytes[1]
    b[46] = end_time_bytes[2]
    b[47] = end_time_bytes[3]
    b[48] = b[8]
    b[49] = int(b[10] / 256 / 256 / 256 / 256) & 255
    b[50] = int(b[10] / 256 / 256 / 256 / 256 / 256) & 255

    # 处理配置项
    b[51] = cast(int, b15["pageId"])

    page_id_bytes = split_to_bytes(cast(int, b15["pageId"]))
    b[52] = page_id_bytes[0]
    b[53] = page_id_bytes[1]
    b[54] = page_id_bytes[2]
    b[55] = page_id_bytes[3]

    b[56] = cast(int, b15["aid"])
    b[57] = cast(int, b15["aid"]) & 255
    b[58] = (cast(int, b15["aid"]) >> 8) & 255
    b[59] = (cast(int, b15["aid"]) >> 16) & 255
    b[60] = (cast(int, b15["aid"]) >> 24) & 255

    # 处理环境信息
    window_env_list = [ord(char) for char in window_env_str]
    b[64] = len(window_env_list)
    b[65] = b[64] & 255
    b[66] = (b[64] >> 8) & 255

    b[69] = 0
    b[70] = 0
    b[71] = 0

    # 计算校验和
    b[72] = (
        b[18]
        ^ b[20]
        ^ b[26]
        ^ b[30]
        ^ b[38]
        ^ b[40]
        ^ b[42]
        ^ b[21]
        ^ b[27]
        ^ b[31]
        ^ b[35]
        ^ b[39]
        ^ b[41]
        ^ b[43]
        ^ b[22]
        ^ b[28]
        ^ b[32]
        ^ b[36]
        ^ b[23]
        ^ b[29]
        ^ b[33]
        ^ b[37]
        ^ b[44]
        ^ b[45]
        ^ b[46]
        ^ b[47]
        ^ b[48]
        ^ b[49]
        ^ b[50]
        ^ b[24]
        ^ b[25]
        ^ b[52]
        ^ b[53]
        ^ b[54]
        ^ b[55]
        ^ b[57]
        ^ b[58]
        ^ b[59]
        ^ b[60]
        ^ b[65]
        ^ b[66]
        ^ b[70]
        ^ b[71]
    )

    # 构建最终字节数组
    bb: list[int] = [
        b[18],
        b[20],
        b[52],
        b[26],
        b[30],
        b[34],
        b[58],
        b[38],
        b[40],
        b[53],
        b[42],
        b[21],
        b[27],
        b[54],
        b[55],
        b[31],
        b[35],
        b[57],
        b[39],
        b[41],
        b[43],
        b[22],
        b[28],
        b[32],
        b[60],
        b[36],
        b[23],
        b[29],
        b[33],
        b[37],
        b[44],
        b[45],
        b[59],
        b[46],
        b[47],
        b[48],
        b[49],
        b[50],
        b[24],
        b[25],
        b[65],
        b[66],
        b[70],
        b[71],
    ]
    bb.extend(window_env_list)
    bb.append(b[72])

    return rc4_encrypt("".join(chr(byte) for byte in bb), chr(121))


def ab_sign(url_search_params: str, user_agent: str) -> str:
    # A-Bogus 签名主入口：入参为 URL query 串与 UA，返回签名值（上层拼接为请求参数）
    window_env_str = "1920|1080|1920|1040|0|30|0|0|1872|92|1920|1040|1857|92|1|24|Win32"

    # 1. 随机前缀 + RC4(bb) 主体拼接；window_env_str 为固定伪造的浏览器窗口/屏幕尺寸
    # 2. 生成RC4加密的主体部分
    # 3. 合并串再过魔改 base64（s4 表）并添加等号后缀
    return (
        result_encrypt(generate_random_str() + generate_rc4_bb_str(url_search_params, user_agent, window_env_str), "s4")
        + "="
    )
