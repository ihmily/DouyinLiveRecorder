<?php

/**
 * Author: Hmily
 * Github:https://github.com/ihmily
 * Date: 2023-07-20 21:06:20
 * Update: 2023-09-17 20:23:00
 * Copyright (c) 2023 by Hmily, All Rights Reserved.
 * Function:Spider the live stream url
 * Address:https://github.com/ihmily/DouyinLiveRecorder
 */


// 本API代码只有解析抖音、快手和虎牙的，有需要其他的可自己根据源码增加
// 注意：抖音和快手的 要添加上自己的cookie才能用 
header('Content-type: application/json; charset=utf-8');

if(empty($_GET['url'])){
    exit(json_encode(['code'=>-2,'msg'=>'请输入抖音/快手/虎牙等平台的直播间地址'],448));
}
$live_url=$_GET['url'];

if (strpos($live_url, 'douyin') !== false) {
    $pattern = "/^https:\/\/v\.douyin\.com\/\w+\/$/";
    if (preg_match($pattern, $live_url)) {
        // 判断是否是app端分享链接，如果是则转为PC网页端地址，否则无法解析
        // 示例链接：
        // $live_url="https://live.douyin.com/187615265444";
        $json_str=get_curl("https://hmily.vip/api/jx/live/convert.php?url=".$live_url);
        $json_data=json_decode($json_str,true);
        $live_url = $json_data['long_url'];
    }
    $json_data2=get_douyin_json_data($live_url);
    $return=get_douyin_stream_url2($json_data2,$live_url);  // 选用第二种方式
    
} else if(strpos($live_url, 'kuaishou') !== false) {
    $return=get_kuaishou_stream_url($live_url);  // 选用第二种方式
}else if(strpos($live_url, 'huya') !== false) {
    $return=get_huya_stream_url($live_url);  // 选用第二种方式
}else{
    $return=['code'=>-1,'msg'=>'暂不支持该平台，请检查链接是否正确'];
}


exit(json_encode($return,448));


function get_douyin_json_data($url) {
    $headers = array(
    'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
    'Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    'Referer: https://live.douyin.com/',
    );
    
    $cookies='your cookie';  # 任意抖音直播间页面的Cookie
    
    $html_str = get_curl($url,$headers,$cookies);
    $pattern = '/\{\\\"state(.*?)\"\]\)\<\/script\>\<div hidden/';
    preg_match($pattern, $html_str, $matches);
    $json_string = '{\"state' . explode(']\n', $matches[1])[0];
    $cleaned_string = str_replace("\\", "", $json_string);
    $cleaned_string = preg_replace('/bdp_log=(.*?)&bdpsum=/', '', $cleaned_string);
    $replacements = array(
        '"[' => '[',
        ']"' => ']',
        '"{' => '{',
        '}"' => '}',
        'u0026' => '&'
    );
    $cleaned_string = strtr($cleaned_string, $replacements);
    $json_data = json_decode($cleaned_string, true);
    return $json_data;

}


# 第一种数据
function get_douyin_stream_url($json_data) {
    $initialState = $json_data['state'];
    $streamStore = $initialState['streamStore'];
    $roomStore = $initialState['roomStore'];
    $streamData = $streamStore['streamData']['H265_streamData']['options'];
    $stream = $streamStore['streamData']['H265_streamData']['stream'];
    $stream2 = $streamStore['streamData']['H264_streamData']['stream'];
    $anchor_name = $roomStore['roomInfo']['anchor']['nickname'];
    $data=array();
    if ($stream === null) {
        $data=["live_status"=>'主播未开播或者直播已经结束！'];
    } else {
        
        $m3u8_url = $stream['origin']['main']['hls'];
        $m3u8_url2 = $stream2['origin']['main']['hls'];
        $data=["title"=>$live_title,'stream'=>['m3u8_url_265'=>$m3u8_url,'m3u8_url_264'=>$m3u8_url2]];
    }
    $return=[
    'code'=>0,
    'status'=>'解析成功',
    'anchor_name'=>$anchor_name,
    'live_url'=>$live_url,
    'data'=>$data,
    'source'=>'源码地址：https://github.com/ihmily/DouyinLiveRecorder'
    ];
    return $return;
}


# 第二种数据（更好）
function get_douyin_stream_url2($json_data,$live_url) {
    $roomStore = $json_data['state']['roomStore'];
    $roomInfo = $roomStore['roomInfo'];
    $anchor_name = $roomInfo['anchor']['nickname'];
    $live_title = $roomInfo['room']['title'] ;
    // 获取直播间状态
    $status = $roomInfo["room"]["status"]; // 直播状态2是正在直播.4是未开播
    $data=array();
    if ($status == 4) {
        $data=["live_status"=>'主播未开播或者直播已经结束！'];
    } else {
        $stream_url = $roomInfo['room']['stream_url'];
        // flv视频流链接
        $flv_url_list = $stream_url['flv_pull_url'];
        // m3u8视频流链接
        $m3u8_url_list = $stream_url['hls_pull_url_map'];
        $data=["title"=>$live_title,'stream'=>['flv_url_list'=>$flv_url_list,'m3u8_url_list'=>$m3u8_url_list]];

    }
    $return=[
    'code'=>0,
    'status'=>'解析成功',
    'platform'=>'抖音直播',
    'anchor_name'=>$anchor_name,
    'live_url'=>$live_url,
    'data'=>$data,
    'source'=>'源码地址：https://github.com/ihmily/DouyinLiveRecorder'
    ];
    return $return;
}


function get_kuaishou_stream_url($live_url){
    $headers = array(
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        
    );
    
    $cookies = 'your cookie';  # 任意快手直播间页面的cookie

    $html_str = get_curl($live_url,$headers,$cookies);
    preg_match('/__INITIAL_STATE__=(.*?);\(function/', $html_str, $matches);
    $json_data = json_decode($matches[1], true);
    
    $play_list= $json_data['liveroom']['playList'][0];
    $live_title=$play_list['liveStream']['caption'];
    $anchor_name = $play_list['author']['name'];
    # 获取直播间状态
    $status = $play_list['isLiving'];  # 直播状态True是正在直播.False是未开播
    if (!$status) {
        $data=["live_status"=>'主播未开播或者直播已经结束！'];
    }else{
        $stream_data=$play_list['liveStream']['playUrls'][0]['adaptationSet']['representation'];
        $data=["title"=>$live_title,'stream'=>$stream_data];
    }
    
    $return=[
    'code'=>0,
    'platform'=>'快手直播',
    'status'=>'解析成功',
    'anchor_name'=>$anchor_name,
    'live_url'=>$live_url,
    'data'=>$data,
    'source'=>'源码地址：https://github.com/ihmily/DouyinLiveRecorder'
    ];
    return $return;
}


function get_huya_stream_url($live_url){
    $headers = array(
        'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
        'Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2'
    );
    $html_str = get_curl($live_url,$headers);
    
    preg_match('/stream: (\{"data".*?),"iWebDefaultBitRate"/', $html_str, $matches);
    $json_data = json_decode($matches[1].'}', true);
    $gameLiveInfo = $json_data['data'][0]['gameLiveInfo'];
    $live_title=$gameLiveInfo['introduction'];
    $gameStreamInfoList = $json_data['data'][0]['gameStreamInfoList'];

    $anchor_name = $gameLiveInfo['nick'];
    if (count($gameStreamInfoList)==0) {
        $data=["live_status"=>'主播未开播或者直播已经结束！'];
    }else{
        # gameStreamInfoList 索引从小到大 分别是'al', 'tx', 'hw', 'hs'四种cdn线路
        # 默认使用第二种 即host链接开头为tx的cdn
        $sFlvUrl = $gameStreamInfoList[1]['sFlvUrl'];
        $sStreamName = $gameStreamInfoList[1]['sStreamName'];
        $sFlvUrlSuffix = $gameStreamInfoList[1]['sFlvUrlSuffix'];
        $sHlsUrl = $gameStreamInfoList[1]['sHlsUrl'];
        $sHlsUrlSuffix = $gameStreamInfoList[1]['sHlsUrlSuffix'];
        $sFlvAntiCode = $gameStreamInfoList[1]['sFlvAntiCode'];
        $quality_list = explode('&exsphd=', $sFlvAntiCode)[1];
        $pattern = "/(?<=264_)\d+/";
        $matches = [];
        preg_match_all($pattern, $quality_list, $matches);
        $quality_list = $matches[0];
        $quality_list = array_reverse($quality_list);
        $m3u8_list=[];
        $flv_list=[];
        foreach ($quality_list as $quality){
            $flv_url = "{$sFlvUrl}/{$sStreamName}.{$sFlvUrlSuffix}?{$sFlvAntiCode}&ratio={$quality}";
            $m3u8_url = "{$sHlsUrl}/{$sStreamName}.{$sHlsUrlSuffix}?{$sFlvAntiCode}&ratio={$quality}";
            array_push($m3u8_list,$m3u8_url);
            array_push($flv_list,$flv_url);
        }
        $data=["title"=>$live_title,'stream'=>['flv_url'=>$flv_list,'m3u8_url'=>$m3u8_list]];
    }
    $return=[
    'code'=>0,
    'platform'=>'虎牙直播',
    'status'=>'解析成功',
    'anchor_name'=>$anchor_name,
    'live_url'=>$live_url,
    'data'=>$data,
    'source'=>'源码地址：https://github.com/ihmily/DouyinLiveRecorder'
    ];
    return $return;
}


// 封装的CURL函数
function get_curl($url,$headers=array(),$cookies=''){
        $curl=curl_init((string)$url);
        curl_setopt($curl,CURLOPT_HEADER,false);
        curl_setopt($curl, CURLOPT_FOLLOWLOCATION, true);
        curl_setopt($curl,CURLOPT_SSL_VERIFYPEER,false);
        curl_setopt($curl, CURLOPT_ENCODING, "");
        curl_setopt($curl,CURLOPT_RETURNTRANSFER,true);
        curl_setopt($curl,CURLOPT_HTTPHEADER,$headers);
        curl_setopt($curl, CURLOPT_COOKIE, $cookies);
        curl_setopt($curl,CURLOPT_TIMEOUT,20);
        $data = curl_exec($curl);
        // var_dump($data);
        curl_close($curl);
        return $data;
    }





