# -*- coding: utf-8 -*-
import asyncio
from streamget.logger import logger
from streamget import spider

# 以下示例直播间链接不保证时效性，请自行查看链接是否能正常访问
# Please note that the following example live room links may not be up-to-date
LIVE_STREAM_CONFIG = {
    "douyin": {
        "url": "https://live.douyin.com/745964462470",
        "func": spider.get_douyin_app_stream_data,
    },
    "tiktok": {
        "url": "https://www.tiktok.com/@pearlgaga88/live",
        "func": spider.get_tiktok_stream_data,
    },
    "kuaishou": {
        "url": "https://live.kuaishou.com/u/yall1102",
        "func": spider.get_kuaishou_stream_data,
    },
    "huya": {
        "url": "https://www.huya.com/116",
        "func": spider.get_huya_app_stream_url,
    },
    "douyu": {
        "url": "https://www.douyu.com/topic/wzDBLS6?rid=4921614&dyshid=",
        "func": spider.get_douyu_info_data,
    },
    "yy": {
        "url": "https://www.yy.com/22490906/22490906",
        "func": spider.get_yy_stream_data,
    },
    "bilibili": {
        "url": "https://live.bilibili.com/21593109",
        "func": spider.get_bilibili_stream_data,
    },
    "xhs": {
        "url": "https://www.xiaohongshu.com/user/profile/6330049c000000002303c7ed?appuid=5f3f478a00000000010005b3",
        "func": spider.get_xhs_stream_url,
    },
    "bigo": {
        "url": "https://www.bigo.tv/cn/716418802",
        "func": spider.get_bigo_stream_url,
    },
    "blued": {
        "url": "https://app.blued.cn/live?id=Mp6G2R",
        "func": spider.get_blued_stream_url,
    },
    "sooplive": {
        "url": "https://play.sooplive.co.kr/sw7love",
        "func": spider.get_sooplive_stream_data,
    },
    "netease": {
        "url": "https://cc.163.com/583946984",
        "func": spider.get_netease_stream_data,
    },
    "qiandurebo": {
        "url": "https://qiandurebo.com/web/video.php?roomnumber=33333",
        "func": spider.get_qiandurebo_stream_data,
    },
    "pandatv": {
        "url": "https://www.pandalive.co.kr/live/play/bara0109",
        "func": spider.get_pandatv_stream_data,
    },
    "maoerfm": {
        "url": "https://fm.missevan.com/live/868895007",
        "func": spider.get_maoerfm_stream_url,
    },
    "winktv": {
        "url": "https://www.winktv.co.kr/live/play/anjer1004",
        "func": spider.get_winktv_stream_data,
    },
    "flextv": {
        "url": "https://www.flextv.co.kr/channels/593127/live",
        "func": spider.get_flextv_stream_data,
    },
    "looklive": {
        "url": "https://look.163.com/live?id=65108820&position=3",
        "func": spider.get_looklive_stream_url,
    },
    "popkontv": {
        "url": "https://www.popkontv.com/live/view?castId=wjfal007&partnerCode=P-00117",
        "func": spider.get_popkontv_stream_url,
    },
    "twitcasting": {
        "url": "https://twitcasting.tv/c:uonq",
        "func": spider.get_twitcasting_stream_url,
    },
    "baidu": {
        "url": "https://live.baidu.com/m/media/pclive/pchome/live.html?room_id=9175031377&tab_category",
        "func": spider.get_baidu_stream_data,
    },
    "weibo": {
        "url": "https://weibo.com/u/7849520225",
        "func": spider.get_weibo_stream_data,
    },
    "kugou": {
        "url": "https://fanxing2.kugou.com/50428671?refer=2177&sourceFrom=",
        "func": spider.get_kugou_stream_url,
    },
    "twitchtv": {
        "url": "https://www.twitch.tv/gamerbee",
        "func": spider.get_twitchtv_stream_data,
    },
    "liveme": {
        "url": "https://www.liveme.com/zh/v/17141937295821012854/index.html",
        "func": spider.get_liveme_stream_url,
    },
    "huajiao": {
        "url": "https://www.huajiao.com/user/207446325",
        "func": spider.get_huajiao_stream_url,
    },
    "showroom": {
        "url": "https://www.showroom-live.com/room/profile?room_id=511033",
        "func": spider.get_showroom_stream_data,
    },
    "acfun": {
        "url": "https://live.acfun.cn/live/17912421",
        "func": spider.get_acfun_stream_data,
    },
    "changliao": {
        "url": "https://www.tlclw.com/801044397",
        "func": spider.get_changliao_stream_url,
    },
    "yingke": {
        "url": "https://www.inke.cn/liveroom/index.html?uid=710032101&id=1720857535354099",
        "func": spider.get_yingke_stream_url,
    },
    "yinbo": {
        "url": "https://live.ybw1666.com/800008687",
        "func": spider.get_yinbo_stream_url,
    },
    "zhihu": {
        "url": "https://www.zhihu.com/people/ac3a467005c5d20381a82230101308e9",
        "func": spider.get_zhihu_stream_url,
    },
    "chzzk": {
        "url": "https://chzzk.naver.com/live/458f6ec20b034f49e0fc6d03921646d2",
        "func": spider.get_chzzk_stream_data,
    },
    "haixiu": {
        "url": "https://www.haixiutv.com/6095106",
        "func": spider.get_haixiu_stream_url,
    },
    "vvxqiu": {
        "url": "https://h5webcdnp.vvxqiu.com//activity/videoShare/videoShare.html?h5Server=https://h5p.vvxqiu.com&"
               "roomId=LP115664695&platformId=vvstar",
        "func": spider.get_vvxqiu_stream_url,
    },
    "17live": {
        "url": "https://17.live/en/live/6302408",
        "func": spider.get_17live_stream_url,
    },
    "langlive": {
        "url": "https://www.lang.live/en-US/room/3349463",
        "func": spider.get_langlive_stream_url,
    },
    "pplive": {
        "url": "https://m.pp.weimipopo.com/live/preview.html?uid=91648673&anchorUid=91625862&app=plpl",
        "func": spider.get_pplive_stream_url,
    },
    "6room": {
        "url": "https://v.6.cn/634435",
        "func": spider.get_6room_stream_url,
    },
    "lehai": {
        "url": "https://www.lehaitv.com/8059096",
        "func": spider.get_haixiu_stream_url,
    },
    "huamao": {
        "url": "https://h.catshow168.com/live/preview.html?uid=19066357&anchorUid=18895331",
        "func": spider.get_pplive_stream_url,
    },
    "shopee": {
        "url": "https://sg.shp.ee/GmpXeuf?uid=1006401066&session=802458",
        "func": spider.get_shopee_stream_url,
    },
    "youtube": {
        "url": "https://www.youtube.com/watch?v=cS6zS5hi1w0",
        "func": spider.get_youtube_stream_url,
    },
    "taobao": {
        "url": "https://m.tb.cn/h.TWp0HTd",
        "func": spider.get_taobao_stream_url,
    },
    "jd": {
        "url": "https://3.cn/28MLBy-E",
        "func": spider.get_jd_stream_url,
    },
    "faceit": {
        "url": "https://www.faceit.com/zh/players/Compl1/stream",
        "func": spider.get_faceit_stream_data,
    }
}


def test_live_stream(platform_name: str, proxy_addr=None, cookies=None) -> None:
    if platform_name in LIVE_STREAM_CONFIG:
        config = LIVE_STREAM_CONFIG[platform_name]
        try:
            stream_data = asyncio.run(config['func'](config['url'], proxy_addr=proxy_addr, cookies=cookies))
            logger.debug(f"Stream data for {platform_name}: {stream_data}")
        except Exception as e:
            logger.error(f"Error fetching stream data for {platform_name}: {e}")
    else:
        logger.warning(f"No configuration found for platform: {platform_name}")


if __name__ == "__main__":
    platform = "douyin"
    test_live_stream(platform)
