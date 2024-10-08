![video_spider](https://socialify.git.ci/ihmily/DouyinLiveRecorder/image?font=Inter&forks=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

## 💡简介
[![Python Version](https://img.shields.io/badge/python-3.11.6-blue.svg)](https://www.python.org/downloads/release/python-3116/)
[![Supported Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux-blue.svg)](https://github.com/ihmily/DouyinLiveRecorder)
[![Docker Pulls](https://img.shields.io/docker/pulls/ihmily/douyin-live-recorder?label=Docker%20Pulls&color=blue&logo=docker)](https://hub.docker.com/r/ihmily/douyin-live-recorder/tags)
![GitHub issues](https://img.shields.io/github/issues/ihmily/DouyinLiveRecorder.svg)
[![Latest Release](https://img.shields.io/github/v/release/ihmily/DouyinLiveRecorder)](https://github.com/ihmily/DouyinLiveRecorder/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/ihmily/DouyinLiveRecorder/total)](https://github.com/ihmily/DouyinLiveRecorder/releases/latest)

一款**简易**的可循环值守的直播录制工具，基于FFmpeg实现多平台直播源录制，支持自定义配置录制以及直播状态推送。

</div>

## 😺已支持平台

- [x] 抖音
- [x] TikTok
- [x] 快手
- [x] 虎牙
- [x] 斗鱼
- [x] YY
- [x] B站
- [x] 小红书
- [x] bigo 
- [x] blued
- [x] AfreecaTV
- [x] 网易cc
- [x] 千度热播
- [x] PandaTV
- [x] 猫耳FM
- [x] Look直播
- [x] WinkTV
- [x] FlexTV
- [x] PopkonTV
- [x] TwitCasting
- [x] 百度直播
- [x] 微博直播
- [x] 酷狗直播
- [x] TwitchTV
- [x] LiveMe
- [x] 花椒直播
- [x] 流星直播
- [x] ShowRoom
- [x] Acfun
- [x] 时光直播
- [x] 映客直播
- [x] 音播直播
- [x] 知乎直播
- [x] CHZZK
- [ ] 更多平台正在更新中

</div>

## 🎈项目结构

```
.
└── DouyinLiveRecorder/
    ├── /config -> (config record)
    ├── /logs -> (save runing log file)
    ├── /backup_config -> (backup file)
    ├── /libs -> (dll file)
    ├── /douyinliverecorder -> (package)
    	├── spider.py-> (get live data)
    	├── stream.py-> (get live stream address)
    	├── utils.py -> (contains utility functions)
    	├── logger.py -> (logger handdle)
    	├── room.py -> (get room info)
    	├── msg_push.py -> (send live status update message)
    	├── x-bogus.js -> (get douyin xbogus token)
    ├── main.py -> (main file)
    ├── demo.py -> (call package test demo)
    ├── ffmpeg.exe -> (record video)
    ├── index.html -> (play m3u8 and flv video)
    ├── requirements.txt -> (library dependencies)
    ├── docker-compose.yaml -> (Container Orchestration File)
    ├── Dockerfile -> (Application Build Recipe)
    ...
```

</div>

## 🌱使用说明

- 对于只想使用录制软件的小白用户，进入[Releases](https://github.com/ihmily/DouyinLiveRecorder/releases) 中下载最新发布的 zip压缩包即可，里面有打包好的录制软件。（有些电脑可能会报毒，直接忽略即可，如果下载时被浏览器屏蔽，请更换浏览器下载）

- 压缩包解压后，在 `config` 文件夹内的 `URL_config.ini` 中添加录制直播间地址，一行一个直播间地址。如果要自定义配置录制，可以修改`config.ini` 文件，推荐将录制格式修改为`ts`。
- 以上步骤都做好后，就可以运行`DouyinLiveRecorder.exe` 程序进行录制了。录制的视频文件保存在同目录下的 `downloads` 文件夹内。

- 另外，如果需要录制TikTok、AfreecaTV等海外平台，请在配置文件中设置开启代理并添加proxy_addr链接 如：`127.0.0.1:7890` （这只是示例地址，具体根据实际填写）。

- 假如`URL_config.ini`文件中添加的直播间地址，有个别直播间暂时不想录制又不想移除链接，可以在对应直播间的链接开头加上`#`，那么将停止该直播间的监测以及录制。

- 软件默认录制清晰度为 `原画` ，如果要单独设置某个直播间的录制画质，可以在添加直播间地址时前面加上画质即可，如`超清，https://live.douyin.com/745964462470` 记得中间要有`,` 分隔。

- 如果要长时间挂着软件循环监测直播，最好循环时间设置长一点（咱也不差没录制到的那几分钟），避免因请求频繁导致被官方封禁IP 。

- 要停止直播录制，在录制界面使用 `Ctrl+C ` 组合键中断录制，若要停止其中某个直播间的录制，可在`URL_config.ini`文件中的地址前加#，会自动停止对应直播间的录制并正常保存视频。
- 最后，欢迎右上角给本项目一个star，同时也非常乐意大家提交pr。

&emsp;

直播间链接示例：

```
抖音：
https://live.douyin.com/745964462470
https://v.douyin.com/iQFeBnt/
https://live.douyin.com/yall1102  （链接+抖音号）
https://v.douyin.com/CeiU5cbX  （作者主页地址）

TikTok：
https://www.tiktok.com/@pearlgaga88/live

快手：
https://live.kuaishou.com/u/yall1102

虎牙：
https://www.huya.com/52333

斗鱼：
https://www.douyu.com/3637778?dyshid=
https://www.douyu.com/topic/wzDBLS6?rid=4921614&dyshid=

YY:
https://www.yy.com/22490906/22490906

B站：
https://live.bilibili.com/320

小红书：
http://xhslink.com/xpJpfM
https://www.xiaohongshu.com/hina/livestream/569077534207413574/1707413727088?appuid=5f3f478a00000000010005b3&

bigo直播：
https://www.bigo.tv/cn/716418802

buled直播：
https://app.blued.cn/live?id=Mp6G2R

AfreecaTV：
https://play.afreecatv.com/sw7love

网易cc：
https://cc.163.com/583946984

千度热播：
https://qiandurebo.com/web/video.php?roomnumber=33333

PandaTV：
https://www.pandalive.co.kr/live/play/bara0109

猫耳FM：
https://fm.missevan.com/live/868895007

Look直播:
https://look.163.com/live?id=65108820&position=3

WinkTV:
https://www.winktv.co.kr/live/play/anjer1004

FlexTV:
https://www.flextv.co.kr/channels/593127/live

PopkonTV:
https://www.popkontv.com/live/view?castId=wjfal007&partnerCode=P-00117
https://www.popkontv.com/channel/notices?mcid=wjfal007&mcPartnerCode=P-00117

TwitCasting:
https://twitcasting.tv/c:uonq

百度直播:
https://live.baidu.com/m/media/pclive/pchome/live.html?room_id=9175031377&tab_category

微博直播:
https://weibo.com/u/7676267963 （主页地址）
https://weibo.com/l/wblive/p/show/1022:2321325026370190442592

酷狗直播:
https://fanxing2.kugou.com/50428671?refer=2177&sourceFrom=

TwitchTV:
https://www.twitch.tv/gamerbee

LiveMe:
https://www.liveme.com/zh/v/17141543493018047815/index.html

花椒直播:
https://www.huajiao.com/user/223184650  （主页地址）

流星直播:
https://www.7u66.com/100960

ShowRoom:
https://www.showroom-live.com/room/profile?room_id=480206  （主页地址）

Acfun:
https://live.acfun.cn/live/179922

时光直播：
https://www.rengzu.com/180778

映客直播：
https://www.inke.cn/liveroom/index.html?uid=22954469&id=1720860391070904

音播直播：
https://live.ybw1666.com/800002949

知乎直播:
https://www.zhihu.com/theater/114453

CHZZK：
https://chzzk.naver.com/live/458f6ec20b034f49e0fc6d03921646d2
```

&emsp;

在线播放m3u8和flv视频网站：[M3U8 在线视频播放器 ](https://jx.hmily.vip/play/)

&emsp;

## 🎃源码运行
使用源码运行，前提要有Python环境，如果没有请先安装Python，再执行下面步骤。

1.首先拉取或手动下载本仓库项目代码

```bash
git clone https://github.com/ihmily/DouyinLiveRecorder.git
```

2.进入项目文件夹，安装依赖

```bash
cd DouyinLiveRecorder
pip3 install -r requirements.txt
```

3.安装[FFmpeg](https://ffmpeg.org/download.html#build-linux)，如果是Windows系统，这一步可跳过。对于Linux系统，执行以下命令安装

CentOS执行

```bash
yum install epel-release
yum install ffmpeg
```

Ubuntu则执行

```bash
apt update
apt install ffmpeg
```

macOS 执行

**如果已经安装 Homebrew 请跳过这一步**

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

```bash
brew install ffmpeg
```

4.运行程序

```python
python main.py
```

其中Linux系统请使用`python3 main.py` 运行。

&emsp;
## 🐋容器运行

在运行命令之前，请确保您的机器上安装了 [Docker](https://docs.docker.com/get-docker/) 和 [Docker Compose](https://docs.docker.com/compose/install/) 

1.快速启动

最简单方法是运行项目中的 [docker-compose.yaml](https://github.com/ihmily/DouyinLiveRecorder/blob/main/docker-compose.yaml) 文件，只需简单执行以下命令：

```bash
docker-compose up
```

可选 `-d` 在后台运行。



2.构建镜像(可选)

如果你只想简单的运行程序，则不需要做这一步。要自定义本地构建，可以修改 [docker-compose.yaml](https://github.com/ihmily/DouyinLiveRecorder/blob/main/docker-compose.yaml) 文件，如将镜像名修改为 `douyin-live-recorder:latest`，并取消 `# build: .` 注释，然后再执行

```bash
docker build -t douyin-live-recorder:latest .
docker-compose up
```

或者直接使用下面命令进行构建并启动

```bash
docker-compose -f docker-compose.yaml up
```



3.停止容器实例

```bash
docker-compose stop
```



4.注意事项

①在docker容器内运行本程序之前，请先在配置文件中添加要录制的直播间地址。

②在容器内时，如果手动中断容器运行停止录制，会导致正在录制的视频文件损坏！

**无论哪种运行方式，为避免手动中断或者异常中断导致录制的视频文件损坏的情况，推荐使用 `ts` 格式保存**。

&emsp;

## ❤️贡献者

&ensp;&ensp; [![Hmily](https://github.com/ihmily.png?size=50)](https://github.com/ihmily)
[![iridescentGray](https://github.com/iridescentGray.png?size=50)](https://github.com/iridescentGray)
[![annidy](https://github.com/annidy.png?size=50)](https://github.com/annidy)
[![wwkk2580](https://github.com/wwkk2580.png?size=50)](https://github.com/wwkk2580)
[![missuo](https://github.com/missuo.png?size=50)](https://github.com/missuo)
<a href="https://github.com/xueli12" target="_blank"><img src="https://github.com/xueli12.png?size=50" alt="xueli12" style="width:53px; height:51px;" /></a>
<a href="https://github.com/kaine1973" target="_blank"><img src="https://github.com/kaine1973.png?size=50" alt="kaine1973" style="width:53px; height:51px;" /></a>
<a href="https://github.com/yinruiqing" target="_blank"><img src="https://github.com/yinruiqing.png?size=50" alt="yinruiqing" style="width:53px; height:51px;" /></a>
<a href="https://github.com/Max-Tortoise" target="_blank"><img src="https://github.com/Max-Tortoise.png?size=50" alt="Max-Tortoise" style="width:53px; height:51px;" /></a>
[![justdoiting](https://github.com/justdoiting.png?size=50)](https://github.com/justdoiting)
[![dhbxs](https://github.com/dhbxs.png?size=50)](https://github.com/dhbxs)
[![wujiyu115](https://github.com/wujiyu115.png?size=50)](https://github.com/wujiyu115)
&emsp;

## ⏳提交日志

- 20241005
  - 新增邮箱和Bark推送
  - 新增直播注释停止录制
  - 优化分段录制
  - 重构部分代码
  
- 20240928
  - 新增知乎直播、CHZZK直播录制
  - 修复音播直播录制
- 20240903
  - 新增抖音双屏录制、音播直播录制
  - 修复PandaTV、bigo直播录制
- 20240713
  - 新增映客直播录制
- 20240705
  - 新增时光直播录制
- 20240701
  - 修复虎牙直播录制2分钟断流问题

  - 新增自定义直播推送内容
- 20240621
  - 新增Acfun、ShowRoom直播录制
  - 修复微博录制、新增直播源线路
  - 修复斗鱼直播60帧录制
  - 修复酷狗直播录制
  - 修复TikTok部分无法解析直播源
  - 修复抖音无法录制连麦直播
- 20240510
  - 修复部分虎牙直播间录制错误
- 20240508
  - 修复花椒直播录制

  - 更改文件路径解析方式 [@kaine1973](https://github.com/kaine1973)
- 20240506
  - 修复抖音录制画质解析bug

  - 修复虎牙录制 60帧最高画质问题

  - 新增流星直播录制
- 20240427
  - 新增LiveMe、花椒直播录制
- 20240425
  - 新增TwitchTV直播录制
- 20240424
  - 新增酷狗直播录制、优化PopkonTV直播录制
- 20240423
  - 新增百度直播录制、微博直播录制

  - 修复斗鱼录制直播回放的问题

  - 新增直播源地址显示以及输出到日志文件设置
- 20240311
  - 修复海外平台录制bug，增加画质选择，增强录制稳定性

  - 修复虎牙录制bug (虎牙`一起看`频道 有特殊限制，有时无法录制)
- 20240309
  - 修复虎牙直播、小红书直播和B站直播录制
  - 新增5个直播平台录制，包括winktv、flextv、look、popkontv、twitcasting
  - 新增部分海外平台账号密码配置，实现自动登录并更新配置文件中的cookie
  - 新增自定义配置需要使用代理录制的平台
  - 新增只推送开播消息不进行录制设置
  - 修复了一些bug
- 20240209
  - 优化AfreecaTV录制，新增账号密码登录获取cookie以及持久保存
  - 修复了小红书直播因官方更新直播域名，导致无法录制直播的问题
  - 修复了更新URL配置文件的bug
  - 最后，祝大家新年快乐！
- 20240129
  - 新增猫耳FM直播录制
- 20240127
  - 新增千度热播直播录制、新增pandaTV(韩国)直播录制

  - 新增telegram直播状态消息推送，修复了某些bug

  - 新增自定义设置不同直播间的录制画质(即每个直播间录制画质可不同)

  - 修改录制视频保存路径为 `downloads` 文件夹，并且分平台进行保存。
- 20240114
  - 新增网易cc直播录制，优化ffmpeg参数，修改AfreecaTV输入直播地址格式

  - 修改日志记录器 @[iridescentGray](https://github.com/iridescentGray)
- 20240102
  - 修复Linux上运行，新增docker配置文件
- 20231210

  - 修复录制分段bug，修复bigo录制检测bug

  - 新增自定义修改录制主播名


  - 新增AfreecaTV直播录制，修复某些可能会发生的bug

- 20231207
  - 新增blued直播录制，修复YY直播录制，新增直播结束消息推送
  
- 20231206
  - 新增bigo直播录制

- 20231203
  - 新增小红书直播录制（全网首发），目前小红书官方没有切换清晰度功能，因此直播录制也只有默认画质
  - 小红书录制暂时无法循环监测，每次主播开启直播，都要重新获取一次链接
  - 获取链接的方式为 将直播间转发到微信，在微信中打开后，复制页面的链接。
- 20231030
  - 本次更新只是进行修复，没时间新增功能。
  - 欢迎各位大佬提pr 帮忙更新维护
- 20230930
  - 新增抖音从接口获取直播流，增强稳定性

  - 修改快手获取直播流的方式，改用从官方接口获取

  - 祝大家中秋节快乐！
- 20230919
  - 修复了快手版本更新后录制出错的问题，增加了其自动获取cookie(~~稳定性未知~~)
  - 修复了TikTok显示正在直播但不进行录制的问题
- 20230907
  - 修复了因抖音官方更新了版本导致的录制出错以及短链接转换出错

  - 修复B站无法录制原画视频的bug

  - 修改了配置文件字段，新增各平台自定义设置Cookie
- 20230903
  - 修复了TikTok录制时报644无法录制的问题
  - 新增直播状态推送到钉钉和微信的功能，如有需要请看 [设置推送教程](https://d04vqdiqwr3.feishu.cn/docx/XFPwdDDvfobbzlxhmMYcvouynDh?from=from_copylink)
  - 最近比较忙，其他问题有时间再更新
- 20230816
  - 修复斗鱼直播（官方更新了字段）和快手直播录制出错的问题
- 20230814
  - 新增B站直播录制
  - 写了一个在线播放M3U8和FLV视频的网页源码，打开即可食用
- 20230812
  - 新增YY直播录制
- 20230808
  - 修复主播重新开播无法再次录制的问题
- 20230807
  - 新增了斗鱼直播录制

  - 修复显示录制完成之后会重新开始录制的问题
- 20230805
  - 新增了虎牙直播录制，其暂时只能用flv视频流进行录制

  - Web API 新增了快手和虎牙这两个平台的直播流解析（TikTok要代理）
- 20230804
  - 新增了快手直播录制，优化了部分代码
  - 上传了一个自动化获取抖音直播间页面Cookie的代码，可以用于录制
- 20230803
  - 通宵更新 
  - 新增了国际版抖音TikTok的直播录制，去除冗余 简化了部分代码
- 20230724	
  - 新增了一个通过抖音直播间地址获取直播视频流链接的API接口，上传即可用


&emsp;

## 有问题可以提issue ，后续我会在这里不断更新其他直播平台的录制  欢迎Star

#### 
