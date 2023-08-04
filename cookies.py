# -*- encoding: utf-8 -*-

"""
Author: Hmily
Github: https://github.com/ihmily
Date: 2023-08-04 17:37:00
Copyright (c) 2023 by Hmily, All Rights Reserved.
Function: 本代码用于自动获取 抖音直播间页面cookies ，可用于录制
请确保电脑有对应浏览器并以及其驱动文件
"""

"""
驱动下载地址：
https://registry.npmmirror.com/binary.html?path=chromedriver/  # 谷歌
https://registry.npmmirror.com/binary.html?path=geckodriver/  # 火狐

"""
import time
from selenium import webdriver

# 下面演示谷歌浏览器获取
from selenium.webdriver.chrome.options import Options

# 请下载自己浏览器对应版本的驱动exe，并注意其路径或者配置环境变量
# 谷歌浏览器版本 108.0.5359.95
# chromedriver版本 108.0.5359.71

# 需要安装对应浏览器的驱动
driver_path = "path/to/your/chromedriver.exe"

def get_cookies(url):
    chrome_options = Options()
    chrome_options.add_argument('-headless')  # Chrome的无头模式，即不用显示打开浏览器的界面
    chrome_options.add_argument('--disable-gpu')
    # driver = webdriver.Chrome(options=chrome_options,executable_path=driver_path)
    driver = webdriver.Chrome(options=chrome_options)  # 这里我是直接将驱动配置了环境变量
    driver.get(url)
    # 先清除浏览器中的所有 Cookie
    driver.delete_all_cookies()
    driver.get(url)  # 再次打开页面
    time.sleep(10)  # 等待页面加载
    # 获取 Cookie
    cookies = driver.get_cookies()
    # print(cookies)
    return cookies


# 将包含 Cookie 信息的列表转换为字典
def cookies_to_dict(cookies_list):
    cookies_dict = {}
    for cookie in cookies_list:
        cookies_dict[cookie['name']] = cookie['value']
    return cookies_dict


# 将字典转换为适用于 requests 请求头的字符串
def dict_to_cookie_str(cookies_dict):
    cookie_str = '; '.join([f"{key}={value}" for key, value in cookies_dict.items()])
    return cookie_str


if __name__ == '__main__':
    url = 'https://live.douyin.com/745964462470'  # 任意直播间页面地址
    cookies_list = get_cookies(url)
    cookies_dict = cookies_to_dict(cookies_list)
    cookie_str = dict_to_cookie_str(cookies_dict)
    print(cookie_str)
    # headers = {
    #     'Cookie': cookie_str,
    #     # 其他请求头
    # }
