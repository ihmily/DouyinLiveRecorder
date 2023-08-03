# DouyinLiveRecorder
一个可循环值守的抖音|国际版抖音Tiktok直播录制软件，支持同时录制多个直播间以及自定义配置

&emsp;

## 项目结构

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
    ├── ffmpeg.exe -> (record video)
```

&emsp;

## 使用说明

- 运行主文件main.py启动程序
- 在config文件夹内的配置文件中对录制进行配置以及添加录制直播间地址
- 录制需要使用到PC端直播间页面的Cookie，请先在config.ini配置文件中添加后再进行录制
- 注意事项① 录制使用到了ffmpeg，如果没有则无法进行录制，请将ffmpeg.exe放置运行文件同个文件夹
- 注意事项② 录制Tiktok时需要使用vpn代理，请先在配置文件中设置开启代理并添加proxy_addr
- 注意事项③ 如果电脑开启了全局或者规则代理，可不用添加proxy_addr参数值但仍需在config.ini配置文件中设置开启代理
- 注意事项④，不知道是不是ffmpeg的原因，测试时在Pycharm中运行进行直播录制，录制出来的视频无法正常播放，而在命令控制台DOS界面运行代码，录制出来的视频可正常播放，这点请注意，别误认为不能录制。

&emsp;

抖音app端直播间分享地址和网页端长地址都能正常进行录制（尽量用长链接，避免因短链接转换失效导致不能正常录制），Tiktok和快手直播间地址目前只支持一种。

抖音直播间链接示例：

```
https://live.douyin.com/745964462470
https://live.douyin.com/326500301367
https://v.douyin.com/iQFeBnt/
```

&emsp;

Tiktok直播间链接示例：

```
https://www.tiktok.com/@pearlgaga88/live
https://www.tiktok.com/@bougiebulliesandbirds/live
```

&emsp;

测试API：https://hmily.vip/api/dy/live/?url=

请求示例：https://hmily.vip/api/dy/live/?url=https://live.douyin.com/573716250978

短地址转换长地址：https://hmily.vip/api/dy/live/convert?url=https://v.douyin.com/iQLgKSj/

注：本测试API只写了抖音的

&emsp;

## ❤️贡献者

&ensp;&ensp; [![Hmily](https://github.com/ihmily.png?size=50)](https://github.com/ihmily)

&emsp;

## 提交日志

- 20230804
  - 新增了快手直播录制，优化了部分代码

- 20230803
  - 通宵更新 
  - 新增了国际版抖音Tiktok的直播录制，去除冗余 简化了部分代码

- 20230724	
  - 新增了一个通过抖音直播间地址获取直播视频流链接的API接口，使用php写的 上传即可用


&emsp;

## 有问题可以提issue 或 参与pr，后续我会在这里不断更新其他直播平台的录制  欢迎给个Star

#### 
