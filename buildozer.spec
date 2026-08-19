[app]

# 应用显示名与包名
title = 视频抓取
package.name = videograbber
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt
source.exclude_dirs = tests,bin,.git,__pycache__

version = 0.1.0

# 依赖：kivy 界面 + requests/beautifulsoup4 抓取 + certifi HTTPS 证书 + ffpyplayer 视频解码
requirements = python3,kivy,requests,beautifulsoup4,certifi,ffpyplayer

# 竖屏；fullscreen=0 保留状态栏
orientation = portrait
fullscreen = 0

# 权限：联网
android.permissions = INTERNET

# 新版 Android 允许访问 http 明文流量（很多视频源是 http）
android.uses_cleartext_traffic = True

# 打包后保留 Python 日志，便于排错
android.logcat_filters = *:S python:D

# SDK / NDK 版本（首次打包会自动下载）
android.api = 34
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

[buildozer]

log_level = 2
warn_on_root = 1
