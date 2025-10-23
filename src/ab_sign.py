# -*- encoding: utf-8 -*-
import math
import time


def rc4_encrypt(plaintext: str, key: str) -> str:
    # 初始化状态数组
    s = list(range(256))

    # 使用密钥对状态数组进行置换
    j = 0
    for i in range(256):
        j = (j + s[i] + ord(key[i % len(key)])) % 256
        s[i], s[j] = s[j], s[i]

    # 生成密钥流并加密
    i = j = 0
    result = []
    for char in plaintext:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        t = (s[i] + s[j]) % 256
        result.append(chr(s[t] ^ ord(char)))

    return ''.join(result)


def left_rotate(x: int, n: int) -> int:
    n %= 32
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def get_t_j(j: int) -> int:
    if 0 <= j < 16:
        return 2043430169  # 0x79CC4519
    elif 16 <= j < 64:
        return 2055708042  # 0x7A879D8A
    else:
        raise ValueError("invalid j for constant Tj")


def ff_j(j: int, x: int, y: int, z: int) -> int:
    if 0 <= j < 16:
        return (x ^ y ^ z) & 0xFFFFFFFF
    elif 16 <= j < 64:
        return ((x & y) | (x & z) | (y & z)) & 0xFFFFFFFF
    else:
        raise ValueError("invalid j for bool function FF")


def gg_j(j: int, x: int, y: int, z: int) -> int:
    if 0 <= j < 16:
        return (x ^ y ^ z) & 0xFFFFFFFF
    elif 16 <= j < 64:
        return ((x & y) | (~x & z)) & 0xFFFFFFFF
    else:
        raise ValueError("invalid j for bool function GG")


class SM3:
    def __init__(self):
        self.reg = []
        self.chunk = []
        self.size = 0
        self.reset()

    def reset(self):
        # 初始化寄存器值 - 修正为与JS版本相同的值
        self.reg = [
            1937774191, 1226093241, 388252375, 3666478592,
            2842636476, 372324522, 3817729613, 2969243214
        ]
        self.chunk = []
        self.size = 0

    def write(self, data):
        # 将输入转换为字节数组
        if isinstance(data, str):
            # 直接转换为UTF-8字节列表
            a = list(data.encode('utf-8'))
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
                    self.chunk = a[f:min(f + 64, len(a))]
                else:
                    self.chunk = []
                f += 64

    def _fill(self):
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

    def _compress(self, data):
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

    def sum(self, data=None, output_format=None):
        """
        计算哈希值
        """
        # 如果提供了输入，则重置并写入
        if data is not None:
            self.reset()
            self.write(data)

        self._fill()

        # 分块压缩
        for f in range(0, len(self.chunk), 64):
            self._compress(self.chunk[f:f + 64])

        if output_format == 'hex':
            # 十六进制输出
            result = ''.join(f'{val:08x}' for val in self.reg)
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


def result_encrypt(long_str: str, num: str | None = None) -> str:
    # 魔改base64编码表
    encoding_tables = {
        "s0": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",
        "s1": "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s2": "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
        "s3": "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe",
        "s4": "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe"
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
    round_num = round_num * 3

    # 获取字符串中的字符，如果超出范围则使用0
    char1 = ord(long_str[round_num]) if round_num < len(long_str) else 0
    char2 = ord(long_str[round_num + 1]) if round_num + 1 < len(long_str) else 0
    char3 = ord(long_str[round_num + 2]) if round_num + 2 < len(long_str) else 0

    return (char1 << 16) | (char2 << 8) | char3


def gener_random(random_num: int, option: list[int]) -> list[int]:
    byte1 = random_num & 255
    byte2 = (random_num >> 8) & 255

    return [
        (byte1 & 170) | (option[0] & 85),  # 偶数位与option[0]的奇数位合并
        (byte1 & 85) | (option[0] & 170),  # 奇数位与option[0]的偶数位合并
        (byte2 & 170) | (option[1] & 85),  # 偶数位与option[1]的奇数位合并
        (byte2 & 85) | (option[1] & 170),  # 奇数位与option[1]的偶数位合并
    ]


def generate_random_str() -> str:
    """
    生成随机字符串

    Returns:
        随机字符串
    """
    # 使用与JS版本相同的固定随机值
    random_values = [0.123456789, 0.987654321, 0.555555555]

    # 生成三组随机字节并合并
    random_bytes = []
    random_bytes.extend(gener_random(int(random_values[0] * 10000), [3, 45]))
    random_bytes.extend(gener_random(int(random_values[1] * 10000), [1, 0]))
    random_bytes.extend(gener_random(int(random_values[2] * 10000), [1, 5]))

    return ''.join(chr(b) for b in random_bytes)


def generate_rc4_bb_str(url_search_params: str, user_agent: str, window_env_str: str,
                        suffix: str = "cus", arguments: list[int] | None = None) -> str:
    if arguments is None:
        arguments = [0, 1, 14]

    sm3 = SM3()
    start_time = int(time.time() * 1000)

    # 三次加密处理
    # 1: url_search_params两次sm3之的结果
    url_search_params_list = sm3.sum(sm3.sum(url_search_params + suffix))
    # 2: 对后缀两次sm3之的结果
    cus = sm3.sum(sm3.sum(suffix))
    # 3: 对ua处理之后的结果
    ua_key = chr(0) + chr(1) + chr(14)  # [1/256, 1, 14]
    ua = sm3.sum(result_encrypt(
        rc4_encrypt(user_agent, ua_key),
        "s3"
    ))

    end_time = start_time + 100

    # 构建配置对象
    b = {
        8: 3,
        10: end_time,
        15: {
            "aid": 6383,
            "pageId": 110624,
            "boe": False,
            "ddrt": 7,
            "paths": {
                "include": [{} for _ in range(7)],
                "exclude": []
            },
            "track": {
                "mode": 0,
                "delay": 300,
                "paths": []
            },
            "dump": True,
            "rpU": "hwj"
        },
        16: start_time,
        18: 44,
        19: [1, 0, 1, 5],
    }

    def split_to_bytes(num: int) -> list[int]:
        return [
            (num >> 24) & 255,
            (num >> 16) & 255,
            (num >> 8) & 255,
            num & 255
        ]

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
    b[51] = b[15]['pageId']

    page_id_bytes = split_to_bytes(b[15]['pageId'])
    b[52] = page_id_bytes[0]
    b[53] = page_id_bytes[1]
    b[54] = page_id_bytes[2]
    b[55] = page_id_bytes[3]

    b[56] = b[15]['aid']
    b[57] = b[15]['aid'] & 255
    b[58] = (b[15]['aid'] >> 8) & 255
    b[59] = (b[15]['aid'] >> 16) & 255
    b[60] = (b[15]['aid'] >> 24) & 255

    # 处理环境信息
    window_env_list = [ord(char) for char in window_env_str]
    b[64] = len(window_env_list)
    b[65] = b[64] & 255
    b[66] = (b[64] >> 8) & 255

    b[69] = 0
    b[70] = 0
    b[71] = 0

    # 计算校验和
    b[72] = b[18] ^ b[20] ^ b[26] ^ b[30] ^ b[38] ^ b[40] ^ b[42] ^ b[21] ^ b[27] ^ b[31] ^ \
            b[35] ^ b[39] ^ b[41] ^ b[43] ^ b[22] ^ b[28] ^ b[32] ^ b[36] ^ b[23] ^ b[29] ^ \
            b[33] ^ b[37] ^ b[44] ^ b[45] ^ b[46] ^ b[47] ^ b[48] ^ b[49] ^ b[50] ^ b[24] ^ \
            b[25] ^ b[52] ^ b[53] ^ b[54] ^ b[55] ^ b[57] ^ b[58] ^ b[59] ^ b[60] ^ b[65] ^ \
            b[66] ^ b[70] ^ b[71]

    # 构建最终字节数组
    bb = [
        b[18], b[20], b[52], b[26], b[30], b[34], b[58], b[38], b[40], b[53], b[42], b[21],
        b[27], b[54], b[55], b[31], b[35], b[57], b[39], b[41], b[43], b[22], b[28], b[32],
        b[60], b[36], b[23], b[29], b[33], b[37], b[44], b[45], b[59], b[46], b[47], b[48],
        b[49], b[50], b[24], b[25], b[65], b[66], b[70], b[71]
    ]
    bb.extend(window_env_list)
    bb.append(b[72])

    return rc4_encrypt(
        ''.join(chr(byte) for byte in bb),
        chr(121)
    )


def ab_sign(url_search_params: str, user_agent: str) -> str:
    window_env_str = "1920|1080|1920|1040|0|30|0|0|1872|92|1920|1040|1857|92|1|24|Win32"

    # 1. 生成随机字符串前缀
    # 2. 生成RC4加密的主体部分
    # 3. 对结果进行最终加密并添加等号后缀
    return result_encrypt(
        generate_random_str() +
        generate_rc4_bb_str(url_search_params, user_agent, window_env_str),
        "s4"
    ) + "="
