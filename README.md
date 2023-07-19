# DouyinLiveRecorder
一个可循环值守的抖音直播录制软件，支持同时录制多个直播间

&emsp;

## 项目结构

```
.
└── DouyinLiveRecorder/
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

&emsp;

## 后续我会在这里不断更新其他直播平台的录制 欢迎给个star

#### 
