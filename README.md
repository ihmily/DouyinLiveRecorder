![video_spider](https://socialify.git.ci/ihmily/DouyinLiveRecorder/image?font=Inter&forks=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

## 💡简介
[![Python Version](https://img.shields.io/badge/python-3.11.6-blue.svg)](https://www.python.org/downloads/release/python-3116/)
[![Supported Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux-blue.svg)](https://github.com/ihmily/DouyinLiveRecorder)
[![Docker Pulls](https://img.shields.io/docker/pulls/ihmily/douyin-live-recorder?label=Docker%20Pulls&color=blue&logo=docker)](https://hub.docker.com/r/ihmily/douyin-live-recorder/tags)
![GitHub issues](https://img.shields.io/github/issues/ihmily/DouyinLiveRecorder.svg)
![Downloads](https://img.shields.io/github/downloads/ihmily/DouyinLiveRecorder/total)

一款简易的可循环值守的直播录制工具，基于FFmpeg实现多平台直播源录制，支持自定义配置录制以及直播状态推送。

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
- [x] pandaTV
- [x] 猫耳FM
- [ ] 更多平台正在更新中

</div>

## 🎈项目结构

```
.
└── DouyinLiveRecorder/
    ├── /api -> (get live stream api )
    ├── /config -> (config record)
    ├── /logs -> (save runing log file)
    ├── /backup_config -> (backup file)
    ├── /libs -> (dll file)
    ├── main.py -> (main file)
    ├── spider.py-> (get live url)
    ├── utils.py -> (contains utility functions)
    ├── logger.py -> (logger handdle)
    ├── web_rid.py -> (get web_rid)
    ├── msg_push.py -> (send live status update message)
    ├── cookies.py -> (get douyin cookies)
    ├── x-bogus.js -> (get douyin xbogus token)
    ├── ffmpeg.exe -> (record video)
    ├── index.html -> (play m3u8 and flv video)
    ├── requirements.txt -> (library dependencies)
    ├── docker-compose.yaml -> (Container Orchestration File)
    ├── Dockerfile -> (Application Build Recipe)
```

</div>

## 🌱使用说明

- 对于只想使用录制软件的小白用户，进入[Releases](https://github.com/ihmily/DouyinLiveRecorder/releases) 中下载最新发布的 zip压缩包即可，里面有打包好的录制软件。（有些电脑可能会报毒，直接忽略即可，如果下载时被浏览器屏蔽，请更换浏览器下载）

- 压缩包解压后，在 `config` 文件夹内的 `URL_config.ini` 中添加录制直播间地址，一行一个直播间地址。如果要自定义配置录制，可以修改`config.ini` 文件，推荐将录制格式修改为`ts`。
- 以上步骤都做好后，就可以运行`DouyinLiveRecorder.exe` 程序进行录制了。录制的视频文件保存在同目录下的 `downloads` 文件夹内。

- 另外，如果需要录制TikTok、AfreecaTV等海外平台，请在配置文件中设置开启代理并添加proxy_addr链接 如：`http://127.0.0.1:7890` （这只是示例地址，具体根据实际填写）。

- 假如`URL_config.ini`文件中添加的直播间地址，有个别直播间暂时不想录制又不想移除链接，可以在对应直播间的链接开头加上`#`，那么下次启动软件录制时将跳过该直播间。

- 软件默认录制清晰度为 `原画` ，如果要单独设置某个直播间的录制画质，可以在添加直播间地址时前面加上画质即可，如`超清，https://live.douyin.com/745964462470` 记得中间要有`,` 分隔。

- 如果要长时间挂着软件循环监测直播，最好循环时间设置长一点（咱也不差没录制到的那几分钟），避免因请求频繁导致被官方封禁IP 。

- 要停止直播录制，使用`Ctrl+C ` 或直接关闭程序即可。
- 最后，欢迎右上角给本项目一个star，同时也非常乐意大家提交pr（请先询问我，避免做无用功）。

&emsp;

直播间链接示例：

```
抖音：
https://live.douyin.com/745964462470
https://v.douyin.com/iQFeBnt/

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
https://www.xiaohongshu.com/hina/livestream/568980065082002402?appuid=5f3f478a00000000010005b3&apptime=

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

pandaTV：
https://www.pandalive.co.kr/live/play/bara0109

猫耳FM：
https://fm.missevan.com/live/868895007
```

直播间分享地址和网页端长地址都能正常进行录制（抖音尽量用长链接，避免因短链接转换失效导致不能正常录制，而且需要有nodejs环境，否则无法转换）。

&emsp;

解析接口：

该解析接口 ~~仅供演示~~(演示接口暂时停止，后续再开放)，并且只包含抖音、快手、虎牙直播的解析，其他平台如有需要请自行添加，源码在这里 [DouyinLiveRecorder/api](https://github.com/ihmily/DouyinLiveRecorder/tree/main/api)

```HTTP
GET https://hmily.vip/api/jx/live/?url=
```

请求示例：

```HTTP
GET https://hmily.vip/api/jx/live/?url=https://live.douyin.com/573716250978
```

若需要将抖音直播间短链接转换为长链接，使用以下接口：

```HTTP
GET https://hmily.vip/api/jx/live/convert.php?url=https://v.douyin.com/iQLgKSj/
```

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

对于Mac系统，访问 https://evermeet.cx/ffmpeg/ 安装FFmpeg。

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

可选 `-d` 在后台运行。第一次运行之后都可用 `docker-compose start`  启动已创建的容器。



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

**如果想避免手动中断或者异常中断导致文件损坏的情况，请使用 `ts` 格式录制并且不要开启自动转成mp4设置**。

&emsp;

## ❤️贡献者

&ensp;&ensp; [![Hmily](https://github.com/ihmily.png?size=50)](https://github.com/ihmily)
[![iridescentGray](https://github.com/iridescentGray.png?size=50)](https://github.com/iridescentGray)
[![annidy](https://github.com/annidy.png?size=50)](https://github.com/annidy)
[![wwkk2580](https://github.com/wwkk2580.png?size=50)](https://github.com/wwkk2580)
&emsp;

## ⏳提交日志

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
