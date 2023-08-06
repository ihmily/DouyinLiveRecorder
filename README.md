![video_spider](https://socialify.git.ci/ihmily/DouyinLiveRecorder/image?description=1&descriptionEditable=%E6%94%AF%E6%8C%81%E5%A4%9A%E4%B8%AA%E7%9B%B4%E6%92%AD%E5%B9%B3%E5%8F%B0%E5%BD%95%E5%88%B6&font=Inter&forks=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

## 💡简介

一款可循环值守的直播录制工具，基于FFmpeg实现多平台直播源录制，支持自定义配置录制参数

</div>

## 😺已支持平台

- [x] 抖音
- [x] Tiktok
- [x] 快手
- [x] 虎牙
- [x] 斗鱼
- [ ] 更多平台正在更新中

</div>

## 🎈项目结构

```
.
└── DouyinLiveRecorder/
	├── /api -> (get live stream api )
    ├── /config -> (config record)
    ├── /log -> (save runing log file)
    ├── /backup_config -> (backup file)
    ├── main.py -> (main file)
    ├── spider.py-> (get live url)
    ├── web_rid.py -> (get web_rid)
    ├── cookies.py -> (get douyin cookies)
    ├── x-bogus.js -> (get douyin xbogus token)
    ├── ffmpeg.exe -> (record video)
```

</div>

## 🌱使用说明

- 运行主文件main.py启动程序
- 在config文件夹内的配置文件中对录制进行配置以及添加录制直播间地址
- 抖音录制需要使用到PC网页端直播间页面的Cookie，请先在config.ini配置文件中添加后再进行抖音录制
- 注意事项① 录制使用到了ffmpeg，如果没有则无法进行录制，请将ffmpeg.exe放置运行文件同个文件夹
- 注意事项② 录制Tiktok时需要使用vpn代理，请先在配置文件中设置开启代理并添加proxy_addr
- 注意事项③ 如果电脑开启了`全局或者规则代理`，可不用添加proxy_addr参数值但仍需在config.ini配置文件中设置开启代理
- 注意事项④ 可以在URL_config.ini中的链接开头加上#，此时将不会录制该条链接对应的直播
- 注意事项⑤ 测试时有可能会出现在IDE如Pycharm中运行代码进行直播录制，录制出来的视频却无法正常播放的现象，如果遇到这个问题 最好在命令控制台DOS界面运行代码，录制出来的视频即可正常播放。
- 可使用 `pyinstaller -F或-D` 将代码打包成exe可执行文件 ，前提是已经安装`pyinstaller`库

&emsp;

Tiktok目前只支持PC网页端地址（没下app），其他平台 app端直播间分享地址和网页端长地址都能正常进行录制（抖音尽量用长链接，避免因短链接转换失效导致不能正常录制）。

直播间链接示例：

```
抖音：
https://live.douyin.com/745964462470
https://v.douyin.com/iQFeBnt/

Tiktok：
https://www.tiktok.com/@pearlgaga88/live

快手：
https://live.kuaishou.com/u/yall1102

虎牙：
https://www.huya.com/52333

斗鱼：
https://www.douyu.com/3637778?dyshid=
https://www.douyu.com/topic/wzDBLS6?rid=4921614&dyshid=

```

</div>

测试API（[源码](https://github.com/ihmily/DouyinLiveRecorder/tree/main/api)）：https://hmily.vip/api/jx/live/?url=

请求示例：https://hmily.vip/api/jx/live/?url=https://live.douyin.com/573716250978

抖音地址转换：https://hmily.vip/api/jx/live/convert.php?url=https://v.douyin.com/iQLgKSj/

&emsp;

## ❤️贡献者

&ensp;&ensp; [![Hmily](https://github.com/ihmily.png?size=50)](https://github.com/ihmily)

</div>

## ⏳提交日志

- 20230807
  - 新增了斗鱼直播录制
  
  - 修复显示录制完成之后会重新开始录制的问题
  
- 20230805
  - 新增了虎牙直播录制，其暂时只能用flv视频流进行录制

  - Web API 新增了快手和虎牙这两个平台的直播流解析（Tiktok要代理）

- 20230804
  - 新增了快手直播录制，优化了部分代码
  - 上传了一个自动化获取抖音直播间页面Cookie的代码，可以用于录制

- 20230803
  - 通宵更新 
  - 新增了国际版抖音Tiktok的直播录制，去除冗余 简化了部分代码

- 20230724	
  - 新增了一个通过抖音直播间地址获取直播视频流链接的API接口，使用php写的 上传即可用


&emsp;

## 有问题可以提issue ，后续我会在这里不断更新其他直播平台的录制  欢迎给个Star

#### 
