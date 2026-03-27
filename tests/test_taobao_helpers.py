import importlib.util
from pathlib import Path
import unittest


HELPERS_PATH = Path(__file__).resolve().parents[1] / "src" / "taobao_utils.py"
SPEC = importlib.util.spec_from_file_location("taobao_utils", HELPERS_PATH)
taobao_utils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(taobao_utils)

get_taobao_live_id = taobao_utils.get_taobao_live_id
is_taobao_live_url = taobao_utils.is_taobao_live_url
get_cookie_value = taobao_utils.get_cookie_value
merge_cookie_header = taobao_utils.merge_cookie_header
build_taobao_sign = taobao_utils.build_taobao_sign


class TestTaobaoHelpers(unittest.TestCase):
    def test_detects_supported_taobao_live_urls(self):
        urls = (
            "https://m.tb.cn/h.TWp0HTd",
            "https://tbzb.taobao.com/live?liveId=557156521789",
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(is_taobao_live_url(url))

    def test_extracts_live_id_from_tbzb_live_url(self):
        url = "https://tbzb.taobao.com/live?liveId=557156521789"
        self.assertEqual(get_taobao_live_id(url), "557156521789")

    def test_extracts_live_id_from_redirect_style_url(self):
        url = "https://huodong.m.taobao.com/act/talent/live.html?id=557156521789"
        self.assertEqual(get_taobao_live_id(url), "557156521789")

    def test_merges_refreshed_taobao_cookie_values(self):
        cookie = "_m_h5_tk=old_token; _m_h5_tk_enc=old_enc; cna=keep_me"
        merged = merge_cookie_header(
            cookie,
            {"_m_h5_tk": "new_token", "_m_h5_tk_enc": "new_enc", "isg": "new_isg"},
        )
        self.assertEqual(get_cookie_value(merged, "_m_h5_tk"), "new_token")
        self.assertEqual(get_cookie_value(merged, "_m_h5_tk_enc"), "new_enc")
        self.assertEqual(get_cookie_value(merged, "cna"), "keep_me")
        self.assertEqual(get_cookie_value(merged, "isg"), "new_isg")

    def test_builds_taobao_sign_with_token_prefix(self):
        token = "sampletoken123_1700000000000"
        data = '{"liveId":"557156521789","creatorId":null}'
        self.assertEqual(
            build_taobao_sign(token, 1234567890123, data),
            "2d678931295fc39ea82599c50e4a6f4e",
        )

    def test_parses_real_tbzb_url_and_cookie_sample(self):
        url = "https://tbzb.taobao.com/live?liveId=557156521789"
        cookies = "_m_h5_tk=sampletoken123_1700000000000;_m_h5_tk_enc=sample_enc_token"

        live_id = get_taobao_live_id(url)
        token = get_cookie_value(cookies, "_m_h5_tk")
        token_enc = get_cookie_value(cookies, "_m_h5_tk_enc")
        data = f'{{"liveId":"{live_id}","creatorId":null}}'

        self.assertTrue(is_taobao_live_url(url))
        self.assertEqual(live_id, "557156521789")
        self.assertEqual(token, "sampletoken123_1700000000000")
        self.assertEqual(token_enc, "sample_enc_token")
        self.assertEqual(
            build_taobao_sign(token, 1234567890123, data),
            "2d678931295fc39ea82599c50e4a6f4e",
        )


if __name__ == "__main__":
    unittest.main()
