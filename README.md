# DouyinLiveRecorder
一个简易的可循环值守的抖音直播录制软件，支持同时录制多个直播间

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
- 注意事项① 录制使用到了ffmpeg，如果没有则无法进行录制
- 注意事项② 录制时不能使用vpn代理，会被抖音禁止访问
- 抖音app端直播间分享地址和网页端长地址都能正常进行录制（尽量用长链接，避免因短链接转换失效导致不能正常录制）

&emsp;

```
测试API：https://hmily.vip/api/dy/live/?url=

参数url：抖音直播间地址

例：https://hmily.vip/api/dy/live/?url=https://live.douyin.com/573716250978
```

&emsp;

## 提交日志

- 20230724	
  - 新增了一个通过抖音直播间地址获取直播视频流链接的API接口，使用php写的 上传即可用


&emsp;

## 有人感兴趣的话，后续我会在这里不断更新其他直播平台的录制 欢迎给个star

#### 
