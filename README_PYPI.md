# StreamGet 

`StreamGet` is a lightweight Python package designed to extract live stream URLs from live room links. 

------

## Features

- **Extract Live Stream URLs**: Get direct video stream URLs by crawling the live room page and extracting the stream source interface.
- **Platform Support**: Works with popular live streaming platforms (e.g. Twitch, YouTube, Douyin, Xiaohongshu, Huya, Douyu, etc.).
- **No Dependencies**: Pure Python implementation with no external dependencies, ensuring lightweight and fast performance.

------

## Installation

Install `StreamGet` via pip:

```bash
pip install streamget
```

------

## Quick Start

```python
import asyncio
from streamget import spider, stream


async def main():
    # Initialize with a live room URL
    url = "https://live.douyin.com/745964462470"

    # Get the live stream URL asynchronously
    room_data = await spider.get_douyin_app_stream_data(url)
    print('room_data:', room_data)
    
    stream_data = await stream.get_douyin_stream_url(room_data, '0')
    print('stream_data :', stream_data)
    stream_url = stream_data.get('record_url')
    print("Live Stream URL:", stream_url)


# Run the async function
asyncio.run(main())

```

------

## Supported Platforms

| Platform    | Support status | HLS support | FLV support |
| :---------- | :------------- | :---------- | :---------- |
| 抖音        | ✅              | ✅           | ✅           |
| TikTok      | ✅              | ✅           | ✅           |
| 快手        | ✅              | ❌           | ✅           |
| 虎牙        | ✅              | ✅           | ✅           |
| 斗鱼        | ✅              | ❌           | ✅           |
| YY          | ✅              | ❌           | ✅           |
| B站         | ✅              | ❌           | ✅           |
| 小红书      | ✅              | ✅           | ✅           |
| Bigo        | ✅              | ✅           | ❌           |
| Blued       | ✅              | ✅           | ❌           |
| SOOP        | ✅              | ✅           | ❌           |
| 网易CC      | ✅              | ✅           | ✅           |
| 千度热播    | ✅              | ❌           | ✅           |
| PandaTV     | ✅              | ✅           | ❌           |
| 猫耳FM      | ✅              | ✅           | ✅           |
| Look直播    | ✅              | ✅           | ✅           |
| WinkTV      | ✅              | ✅           | ❌           |
| FlexTV      | ✅              | ✅           | ❌           |
| PopkonTV    | ✅              | ✅           | ❌           |
| TwitCasting | ✅              | ✅           | ❌           |
| 百度直播    | ✅              | ✅           | ✅           |
| 微博直播    | ✅              | ✅           | ✅           |
| 酷狗直播    | ✅              | ❌           | ✅           |
| TwitchTV    | ✅              | ✅           | ❌           |
| LiveMe      | ✅              | ✅           | ✅           |
| 花椒直播    | ✅              | ❌           | ✅           |
| 流星直播    | ✅              | ❌           | ✅           |
| ShowRoom    | ✅              | ✅           | ❌           |
| Acfun       | ✅              | ✅           | ✅           |
| 映客直播    | ✅              | ✅           | ✅           |
| 音播直播    | ✅              | ✅           | ✅           |
| 知乎直播    | ✅              | ✅           | ✅           |
| CHZZK       | ✅              | ✅           | ❌           |
| 嗨秀直播    | ✅              | ❌           | ✅           |
| vv星球直播  | ✅              | ✅           | ❌           |
| 17Live      | ✅              | ❌           | ✅           |
| 浪Live      | ✅              | ✅           | ✅           |
| 畅聊直播    | ✅              | ✅           | ✅           |
| 飘飘直播    | ✅              | ✅           | ✅           |
| 六间房直播  | ✅              | ❌           | ✅           |
| 乐嗨直播    | ✅              | ✅           | ✅           |
| 花猫直播    | ✅              | ✅           | ❌           |
| Shopee      | ✅              | ❌           | ✅           |
| YouTube     | ✅              | ✅           | ❌           |
| 淘宝        | ✅              | ✅           | ✅           |
| 京东        | ✅              | ✅           | ✅           |
| Faceit      | ✅              | ✅           | ❌           |
| More ...    |                |             |             |

### Notes:

1. **Support Status**: ✅ indicates supported, ❌ indicates unsupported.

------

## Supported Quality

| Chinese clarity | abbreviation | Full Name             | Note                                               |
| :-------------- | :----------- | :-------------------- | :------------------------------------------------- |
| 原画            | `OD`         | Original Definition   | Highest clarity, original picture quality          |
| 蓝光            | `BD`         | Blue-ray Definition   | High definition close to blue light quality        |
| 超清            | `UHD`        | Ultra High Definition | Ultra high definition                              |
| 高清            | `HD`         | High Definition       | High definition, usually referring to 1080p        |
| 标清            | `SD`         | Standard Definition   | Standard clarity, usually referring to 480p        |
| 流畅            | `LD`         | Low Definition        | Low definition, usually referring to 360p or lower |

## Contributing

Contributions are welcome! If you'd like to add support for a new platform or improve the package, please check out the [GitHub repository](https://github.com/ihmily/DouyinLiveRecorder) and submit a pull request.

------

## License

`StreamGet` is released under the MIT License. See the [LICENSE](https://github.com/ihmily/DouyinLiveRecorder/blob/main/LICENSE) file for details.

------

## Documentation

For full documentation and advanced usage, visit the [official documentation](https://streamget.readthedocs.io/).

------

