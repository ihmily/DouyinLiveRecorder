import re

# Test with just \r\n before user.play_url
html1 = "var user = {data}\r\nuser.play_url"
m1 = re.search("var user = (.*?)\r\n\\s+user\\.play_url", html1, re.DOTALL)
print("Test 1 (no indent):", m1)

# Test with 2-space indent
html2 = "var user = {data}\r\n  user.play_url"
m2 = re.search("var user = (.*?)\r\n\\s+user\\.play_url", html2, re.DOTALL)
print("Test 2 (2-space indent):", m2)

# Test with multiline data
html3 = 'var user = {"a": "1",\r\n  "b": "2",\r\nuser.play_url'
m3 = re.search("var user = (.*?)\r\n\\s+user\\.play_url", html3, re.DOTALL)
print("Test 3 (multiline data):", m3)

# Test with multiline data + indent
html4 = 'var user = {"a": "1",\r\n  "b": "2",\r\n  user.play_url'
m4 = re.search("var user = (.*?)\r\n\\s+user\\.play_url", html4, re.DOTALL)
print("Test 4 (multiline + indent):", m4)

# The actual test case
html5 = 'var user = {"zb_nickname": "hot",\r\n  "play_url": "http://cdn.example.com/live.flv",\r\nuser.play_url'
m5 = re.search("var user = (.*?)\r\n\\s+user\\.play_url", html5, re.DOTALL)
print("Test 5 (actual):", m5)
print("Test 5 repr:", repr(html5))
