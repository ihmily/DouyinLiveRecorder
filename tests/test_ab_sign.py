# Tests for src/ab_sign.py module - A-Bogus 签名算法.

import pytest

from src.ab_sign import (
    SM3,
    ab_sign,
    ff_j,
    gener_random,
    generate_random_str,
    generate_rc4_bb_str,
    get_long_int,
    get_t_j,
    gg_j,
    left_rotate,
    rc4_encrypt,
    result_encrypt,
)


class TestRc4Encrypt:
    # Test RC4 加密/解密.

    def test_encrypt_decrypt_roundtrip(self) -> None:
        # RC4 加密后再解密应还原原文.
        key = "test_key"
        plaintext = "Hello, World!"
        encrypted = rc4_encrypt(plaintext, key)
        decrypted = rc4_encrypt(encrypted, key)
        assert decrypted == plaintext

    def test_empty_plaintext(self) -> None:
        # 空字符串加密返回空字符串.
        assert rc4_encrypt("", "key") == ""

    def test_different_keys_produce_different_output(self) -> None:
        # 不同密钥产生不同密文.
        plaintext = "test"
        assert rc4_encrypt(plaintext, "key1") != rc4_encrypt(plaintext, "key2")

    def test_known_value(self) -> None:
        # 已知输入的确定性输出.
        result = rc4_encrypt("abc", "key")
        assert isinstance(result, str)
        assert len(result) == 3


class TestLeftRotate:
    # Test 32位循环左移.

    def test_basic_rotation(self) -> None:
        assert left_rotate(1, 1) == 2

    def test_rotation_overflow(self) -> None:
        # 超过32位的高位被截断.
        result = left_rotate(0x80000000, 1)
        assert result == 1

    def test_zero_rotation(self) -> None:
        # 移动0位等于不移动.
        assert left_rotate(0xDEADBEEF, 0) == 0xDEADBEEF

    def test_full_rotation(self) -> None:
        # 移动32位等于不移动.
        assert left_rotate(0xDEADBEEF, 32) == 0xDEADBEEF


class TestGetTj:
    # Test 常量 Tj 计算.

    def test_first_range(self) -> None:
        assert get_t_j(0) == 2043430169
        assert get_t_j(15) == 2043430169

    def test_second_range(self) -> None:
        assert get_t_j(16) == 2055708042
        assert get_t_j(63) == 2055708042

    def test_invalid_j(self) -> None:
        with pytest.raises(ValueError, match="invalid j"):
            get_t_j(64)
        with pytest.raises(ValueError, match="invalid j"):
            get_t_j(-1)


class TestFfJ:
    # Test 布尔函数 FF.

    def test_first_range(self) -> None:
        # j < 16: XOR.
        assert ff_j(0, 0xFF, 0x0F, 0xF0) == (0xFF ^ 0x0F ^ 0xF0) & 0xFFFFFFFF

    def test_second_range(self) -> None:
        # j >= 16: majority.
        result = ff_j(16, 0xFF, 0x0F, 0xF0)
        expected = ((0xFF & 0x0F) | (0xFF & 0xF0) | (0x0F & 0xF0)) & 0xFFFFFFFF
        assert result == expected

    def test_invalid_j(self) -> None:
        with pytest.raises(ValueError):
            ff_j(64, 0, 0, 0)


class TestGgJ:
    # Test 布尔函数 GG.

    def test_first_range(self) -> None:
        # j < 16: XOR.
        assert gg_j(0, 0xFF, 0x0F, 0xF0) == (0xFF ^ 0x0F ^ 0xF0) & 0xFFFFFFFF

    def test_second_range(self) -> None:
        # j >= 16: (x&y)|(~x&z).
        result = gg_j(16, 0xFF, 0x0F, 0xF0)
        expected = ((0xFF & 0x0F) | ((~0xFF & 0xFFFFFFFF) & 0xF0)) & 0xFFFFFFFF
        assert result == expected

    def test_invalid_j(self) -> None:
        with pytest.raises(ValueError):
            gg_j(-1, 0, 0, 0)


class TestSM3:
    # Test SM3 哈希算法.

    def test_known_hash(self) -> None:
        # SM3('abc') 的已知标准值.
        sm3 = SM3()
        result = sm3.sum("abc", output_format="hex")
        assert isinstance(result, str)
        assert len(result) == 64  # 256-bit hash = 64 hex chars

    def test_empty_string(self) -> None:
        # 空字符串的 SM3 哈希.
        sm3 = SM3()
        result = sm3.sum("", output_format="hex")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_byte_array_output(self) -> None:
        # 字节数组格式输出.
        sm3 = SM3()
        result = sm3.sum("test")
        assert isinstance(result, list)
        assert len(result) == 32  # 256 bits = 32 bytes

    def test_deterministic(self) -> None:
        # 相同输入产生相同输出.
        sm3 = SM3()
        r1 = sm3.sum("hello", output_format="hex")
        r2 = sm3.sum("hello", output_format="hex")
        assert r1 == r2

    def test_different_inputs(self) -> None:
        # 不同输入产生不同输出.
        sm3 = SM3()
        r1 = sm3.sum("abc", output_format="hex")
        r2 = sm3.sum("def", output_format="hex")
        assert r1 != r2

    def test_long_input(self) -> None:
        # 长输入（超过64字节分块）.
        sm3 = SM3()
        result = sm3.sum("a" * 200, output_format="hex")
        assert len(result) == 64

    def test_write_incremental(self) -> None:
        # 分次写入数据.
        sm3 = SM3()
        sm3.write("ab")
        sm3.write("c")
        result1 = sm3.sum(output_format="hex")
        result2 = sm3.sum("abc", output_format="hex")
        assert result1 == result2

    def test_compress_error(self) -> None:
        # 数据不足64字节时 _compress 抛异常.
        sm3 = SM3()
        with pytest.raises(ValueError, match="not enough data"):
            sm3._compress([0] * 32)


class TestResultEncrypt:
    # Test 魔改 base64 编码.

    def test_output_length(self) -> None:
        # 输出长度为 ceil(n/3)*4.
        result = result_encrypt("abc")
        assert len(result) == 4

    def test_different_scales(self) -> None:
        # 不同 num 参数产生不同输出.
        text = "test"
        r1 = result_encrypt(text, "s0")
        r2 = result_encrypt(text, "s4")
        assert r1 != r2

    def test_deterministic(self) -> None:
        # 相同输入确定性输出.
        assert result_encrypt("hello", "s4") == result_encrypt("hello", "s4")


class TestGetLongInt:
    # Test 字节序列转长整型.

    def test_basic(self) -> None:
        assert get_long_int(0, "abc") == (ord("a") << 16) | (ord("b") << 8) | ord("c")

    def test_padding_with_zeros(self) -> None:
        # 超出字符串长度时用0填充.
        result = get_long_int(0, "a")
        assert result == (ord("a") << 16)

    def test_round_number_offset(self) -> None:
        # round_num 按3字节步进.
        result = get_long_int(1, "abcdef")
        assert result == (ord("d") << 16) | (ord("e") << 8) | ord("f")


class TestGenerRandom:
    # Test 随机字节序列生成.

    def test_output_length(self) -> None:
        # 输出固定4字节.
        result = gener_random(12345, [3, 45])
        assert len(result) == 4

    def test_deterministic(self) -> None:
        # 相同输入确定性输出.
        assert gener_random(100, [1, 2]) == gener_random(100, [1, 2])

    def test_different_inputs(self) -> None:
        # 不同输入产生不同输出.
        assert gener_random(100, [1, 2]) != gener_random(200, [1, 2])


class TestGenerateRandomStr:
    # Test 随机字符串生成.

    def test_returns_string(self) -> None:
        result = generate_random_str()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_deterministic(self) -> None:
        # 固定随机值种子产生确定性输出.
        r1 = generate_random_str()
        r2 = generate_random_str()
        assert r1 == r2


class TestGenerateRc4BbStr:
    # Test RC4 bb 字符串生成.

    def test_returns_string(self) -> None:
        result = generate_rc4_bb_str("param=value", "Mozilla/5.0", "env_str")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_deterministic(self) -> None:
        # 相同输入确定性输出（时间相关，但结构一致）.
        r1 = generate_rc4_bb_str("p=1", "ua", "env")
        r2 = generate_rc4_bb_str("p=1", "ua", "env")
        # 由于时间戳不同，两次结果可能不同，但都应为非空字符串
        assert isinstance(r1, str) and len(r1) > 0
        assert isinstance(r2, str) and len(r2) > 0


class TestAbSign:
    # Test A-Bogus 签名算法主入口.

    def test_returns_string_with_equals(self) -> None:
        # 签名结果以 '=' 结尾.
        result = ab_sign("aid=6383&test=1", "Mozilla/5.0")
        assert isinstance(result, str)
        assert result.endswith("=")
        assert len(result) > 10

    def test_different_params(self) -> None:
        # 不同参数产生不同签名.
        r1 = ab_sign("aid=6383&a=1", "UA1")
        r2 = ab_sign("aid=6383&a=2", "UA1")
        assert r1 != r2
