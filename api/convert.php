<?php

/**
 * Author: Hmily
 * Github:https://github.com/ihmily
 * Date: 2023-07-20 21:06:20
 * Update: 2023-09-07 22:34:57
 * Copyright (c) 2023 by Hmily, All Rights Reserved.
 * Function:convert short url to long url
 * Address:https://github.com/ihmily/DouyinLiveRecorder
 */


// 该代码主要是用来转换地址，将短app端直播分享链接转为PC网页端长链接
header('Content-type: application/json; charset=utf-8');


if(empty($_GET['url'])){
    exit(json_encode(['code'=>-2,'msg'=>'请输入app端直播间分享地址'],448));
}
$share_url=$_GET['url'];

$get_id=get_redirect_url($share_url);
preg_match('/reflow\/(.*?)\?/', $get_id, $room_id);
preg_match('/sec_user_id=([\w\d_\-]+)&/', $get_id, $sec_user_id);
$room_data=get_live_web_rid($room_id[1],$sec_user_id[1]);
$title=$room_data[0];
$web_rid=$room_data[1];


if(empty($web_rid)){
    exit(json_encode(['code'=>-1,'status'=>'解析失败','msg'=>'请检测链接是否正确，多次失败请联系作者修复！https://github.com/ihmily/DouyinLiveRecorder'],448));
}
$long_url="https://live.douyin.com/".$web_rid;
$return=
    [
        'code'=>0,
        'status'=>'解析成功',
        'title'=>$title,
        'room_id'=>$room_id[1],
        'share_url'=>$share_url,
        'long_url'=>$long_url,
        'source'=>'源码地址：https://github.com/ihmily/DouyinLiveRecorder'
    ];
exit(json_encode($return,448));


// 抖音X-bogus算法，直接调用我封装的接口
function get_xbogus($url) {
    $query = parse_url($url, PHP_URL_QUERY);
    $url = "http://43.138.133.177:8890/xbogus";
    $data = array(
        'url' => $query,
        'ua' => "Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36",
    );
    $params = http_build_query($data);
    $url = $url . '?' . $params;
    $response = file_get_contents($url);
    $response_json = json_decode($response, true);
    $xbogus = $response_json['result'];
    // echo "生成的X-Bogus签名为: " . $xbogus;
    return $xbogus;
}


function get_live_web_rid($room_id, $sec_user_id) {

    $url = 'https://webcast.amemv.com/webcast/room/reflow/info/?verifyFp=verify_lk07kv74_QZYCUApD_xhiB_405x_Ax51_GYO9bUIyZQVf&type_id=0&live_id=1&room_id='.$room_id.'&sec_user_id='.$sec_user_id.'&app_id=1128&msToken=wrqzbEaTlsxt52-vxyZo_mIoL0RjNi1ZdDe7gzEGMUTVh_HvmbLLkQrA_1HKVOa2C6gkxb6IiY6TY2z8enAkPEwGq--gM-me3Yudck2ailla5Q4osnYIHxd9dI4WtQ==';
    $xbogus = get_xbogus($url);  // 获取X-Bogus算法
    
    $url = $url . "&X-Bogus=" . $xbogus;
    $headers = array(
        'User-Agent: Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36',
        'Accept:application/json, text/plain, */*',
        'Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    );
    $cookies='s_v_web_id=verify_lk07kv74_QZYCUApD_xhiB_405x_Ax51_GYO9bUIyZQVf';
    $json_data = get_curl($url,$headers,$cookies);
    $json_data = json_decode($json_data, true);
    $web_rid = $json_data['data']['room']['owner']['web_rid'];
    $title=$json_data["data"]['room']['title'];
    return [$title,$web_rid];
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
    
    
function get_redirect_url($url) {
    $curl = curl_init();
    curl_setopt($curl, CURLOPT_URL, $url);
    curl_setopt($curl, CURLOPT_SSL_VERIFYPEER, false);
    curl_setopt($curl, CURLOPT_SSL_VERIFYHOST, false);
    curl_setopt($curl, CURLOPT_HTTPHEADER, array( "User-Agent:Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 Mobile/15A372 Safari/604.1"));
    curl_setopt($curl, CURLOPT_HEADER, true);
    curl_setopt($curl, CURLOPT_NOBODY, 1);
    curl_setopt($curl, CURLOPT_FOLLOWLOCATION, 1);
    curl_setopt($curl, CURLOPT_RETURNTRANSFER, 1);
    curl_setopt($curl,CURLOPT_TIMEOUT,20);
    $ret = curl_exec($curl);
    curl_close($curl);
    preg_match("/Location: (.*?)\r\n/iU",$ret,$location);
    return $location[1];
}


