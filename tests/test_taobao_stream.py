import asyncio
import os
import unittest

from src import spider, stream


class TestTaobaoIntegration(unittest.TestCase):
    def test_fetches_real_taobao_stream_urls(self):
        url = "https://tbzb.taobao.com/live?liveId=557156521789"
        cookies = "_m_h5_tk=2007b3c0ac705a948417b47ea0f92638_1773349778735;_m_h5_tk_enc=8b6eb1331f579522765e81bfe5289990"

        if not url or not cookies:
            self.skipTest(
                "Set TAOBAO_TEST_URL and TAOBAO_TEST_COOKIES to run this integration test"
            )

        json_data = asyncio.run(spider.get_taobao_stream_url(url=url, cookies=cookies))
        self.assertTrue(
            json_data.get("anchor_name"), "Expected Taobao anchor_name to be resolved"
        )

        if not json_data.get("is_live"):
            self.skipTest(
                f"Taobao live room is offline: {json_data.get('anchor_name')}"
            )

        port_info = asyncio.run(
            stream.get_stream_url(
                json_data,
                "OD",
                url_type="all",
                hls_extra_key="hlsUrl",
                flv_extra_key="flvUrl",
            )
        )

        print(f"m3u8_url={port_info.get('m3u8_url')}")
        print(f"flv_url={port_info.get('flv_url')}")

        self.assertTrue(port_info.get("m3u8_url") or port_info.get("flv_url"))


if __name__ == "__main__":
    unittest.main()
