<?php

/**
 * Author: Hmily
 * Github:https://github.com/ihmily
 * Date: 2023-07-20 21:06:20
 * Update: 2023-09-07 23:53:07
 * Copyright (c) 2023 by Hmily, All Rights Reserved.
 * Function:Spider the live stream url
 * Address:https://github.com/ihmily/DouyinLiveRecorder
 */


// 本API代码只有解析抖音、快手和虎牙的，有需要其他的可自己根据源码增加
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
    
    $cookies='ttwid=1%7CIkooT8SJQrpeYtHlSALuhz9BdcHpaaf9tHQRKHuDaYE%7C1687785070%7C6690250483b63b6482128174d0f93bd879614d76f1b6e03ca52e032cf7fbaafd; passport_csrf_token=52bece134ac246c81163cc93b72f86a6; passport_csrf_token_default=52bece134ac246c81163cc93b72f86a6; d_ticket=2b9e3eb3626216c0122f0d980f867deb7b414; n_mh=hvnJEQ4Q5eiH74-84kTFUyv4VK8xtSrpRZG1AhCeFNI; passport_auth_status=a74f300f376940d65914eb148d55ca96%2C9ca487aea255972120d502f736c5dd7b; passport_auth_status_ss=a74f300f376940d65914eb148d55ca96%2C9ca487aea255972120d502f736c5dd7b; sso_auth_status=52ecac30d95890cc7896c880366aa21a; sso_auth_status_ss=52ecac30d95890cc7896c880366aa21a; LOGIN_STATUS=1; store-region=cn-fj; store-region-src=uid; __security_server_data_status=1; __live_version__=%221.1.1.1853%22; live_can_add_dy_2_desktop=%220%22; xgplayer_user_id=528819598596; msToken=ZfXzPPa_KqQDF9wkHigKqgyUMIt33-qgLl1qqthGsAea4L69i9wxWaGH4GaQ9M_Q-eqhLpnD4v8FRGIj9KGJGIyLmjPkR1uepZ0gBaqhCkqK1KaauPXT_VK_uVgW6q4=; home_can_add_dy_2_desktop=%220%22; strategyABtestKey=%221689685952.92%22; FOLLOW_LIVE_POINT_INFO=%22MS4wLjABAAAAf6aekfyBsc4u8jMkeYbgnkFa0ksIWKWpGOywuyHXyo4%2F1689609600000%2F0%2F1689606316434%2F0%22; FOLLOW_NUMBER_YELLOW_POINT_INFO=%22MS4wLjABAAAAf6aekfyBsc4u8jMkeYbgnkFa0ksIWKWpGOywuyHXyo4%2F1689609600000%2F0%2F0%2F1689594083273%22; FORCE_LOGIN=%7B%22videoConsumedRemainSeconds%22%3A180%7D; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Atrue%2C%22volume%22%3A0.6%7D; device_web_cpu_core=8; device_web_memory_size=-1; webcast_local_quality=origin; csrf_session_id=0446f50cc7e08f146ad07351af90f413; __ac_nonce=064be522600a12daa29ff; __ac_signature=_02B4Z6wo00f0145FB4AAAIDCkga5P5okFMuOdAMAAIc3h1Lmbu.WZmNdgawlJBkHRSAf1yndkZFgF.zN2OHlE62.f.4ZFt740eSkTrQW8j3EM2s9s3vtK9LGh-h9jhUkgSbj4UOtYTqpCZZc88; webcast_leading_last_show_time=1690194481638; webcast_leading_total_show_times=1; odin_tt=6ebbe0a3c1b4e5bc6d333c5c7514fc88a288b3b03b1f0cf34826dee5d6d6394620f17fd4eb624b710954233f38fa3c67fd4a5338bffaa792a2cf71d1b51d837f079925497d6b372f47a577d779036a71; msToken=uHqyINCG79-ojuC5cXU6tYm0Av3BqNzqLkFGvbNw5QmSCtFY7xYHJjJ3wu-gk2Evj5QQ7D6UMsz2inlRN-aZf8xTGMAnpmgieOrygPqoK7QboFwCXR7aLi4KKcFXvFu2; tt_scid=BVvDLf3XEG4PZlY2-haad4.kR2BYWdq4X88b6-sPA2Wpg2lsSDI5M7YuZ7H-GPf.6646';
    
    $html_str = get_curl($url,$headers,$cookies);
    // print_r($html_str);
 
    $pattern = '/self\.__pace_f\.push(.*?)<\/script><div hidden id/Us';
    $p_result = preg_match($pattern, $html_str, $matches);
    $pattern2 = '/state\\\":(.*?),\\\"isAsianGames/';
    $p_result2 = preg_match($pattern2, $matches[1], $matches2);
    $cleaned_string = str_replace("\\", "", $matches2[1].'}]}');
    $cleaned_string = preg_replace('/bdp_log=(.*?)&bdpsum=/', '', $cleaned_string);

    $replacements = array(
        '"[' => '[',
        ']"' => ']',
        '"{' => '{', 
        '}"' => '}', 
        'u0026' => '&'
    );
    
    $cleaned_string = strtr($cleaned_string, $replacements);
    $json_str='{"state":'.$cleaned_string;
    // echo $json_str;
    $json_data = json_decode($json_str, true);
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
        'Cookie:clientid=3; did=web_2e5935532808ea57f357c827b45abaf4; didv=1687682547000; client_key=65890b29; kpn=GAME_ZONE; clientid=3; did=web_2e5935532808ea57f357c827b45abaf4; client_key=65890b29; kpn=GAME_ZONE; userId=580178847; kuaishou.live.web_st=ChRrdWFpc2hvdS5saXZlLndlYi5zdBKgAQ-E2wk--dxc2ehil5tQ5PZxSAAy_WocJekwLrvD4yIZxEo4y76RBkXONqX9xSLhyX5WOyhWdsXrwH-Nj0RTgM4csF_UwnsIclnnZT6WNO2tfB3fmNHvZHAIRtqDl6hXsS1x8vwgHCii65me0EiPh1LK855TafkNx9A7wrTma6XPlCPL8L1GNKTjtiQB2L7Y0kuOp-l0zVzIidHhFvGXfFEaEgCrAu8bFEUPixNgRvVq1Nb0ZSIghKUYro_uVYFHrcP3wJ93ACmwb-oSRGVtcLhGUdaI43UoBTAB; kuaishou.live.web_ph=c371edbd1ecfdc90fb87ae8c0c8738ec6f3f; userId=580178847; kuaishou.live.bfb1s=477cb0011daca84b36b3a4676857e5a1'
    );
    $html_str = get_curl($live_url,$headers);
    preg_match('/__INITIAL_STATE__=(.*?);\(function/', $html_str, $matches);
    $json_data = json_decode($matches[1], true);
    $liveroom = $json_data['liveroom'];
    $live_title=$liveroom['liveStream']['caption'];
    $anchor_name = $liveroom['author']['name'];
    # 获取直播间状态
    $status = $liveroom['isLiving'];  # 直播状态True是正在直播.False是未开播
    if (!$status) {
        $data=["live_status"=>'主播未开播或者直播已经结束！'];
    }else{
        $stream_data=$liveroom['liveStream']['playUrls'][0]['adaptationSet']['representation'];
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









