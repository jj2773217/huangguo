# 通用视频抓取客户端 · Android 版

由桌面版 `video_grabber.py` 移植而来，用 **Kivy** 打包成 Android APK，手机本机独立运行（不依赖电脑）。

## 功能与能力边界

| 能力 | 桌面版 | Android 版 |
|------|--------|-----------|
| 静态抓取（requests） | ✅ | ✅ |
| JS 渲染（Playwright） | ✅ | ❌ 手机端不支持，`render_js` 配置会被忽略（走静态抓取） |
| 播放 mp4 直链 | ✅ | ✅ Kivy 播放器 |
| 播放 m3u8（HLS） | ✅ (VLC) | ❌ 内置播放器不支持，需外部播放器 |
| 下载 mp4 直链 | ✅ yt-dlp | ✅ requests 流式下载 |
| 下载 m3u8 流 | ✅ yt-dlp | ❌ 暂不支持 |

> 因此 Android 版更适合**有 mp4 直链**的站点。若站点依赖 JS 渲染或仅提供 m3u8，建议仍用桌面版。

## 目录结构

```
android_app/
├── main.py            # Kivy 界面 + 交互逻辑
├── grabber.py         # 抓取核心逻辑（纯 Python，无 UI 依赖）
├── buildozer.spec     # APK 打包配置
└── README.md
```

站点配置不需要打包文件，首次运行时程序会自动在手机应用数据目录生成示例配置
（路径：`/data/data/org.example.videograbber/files/grabber_configs/`）。

## 本地桌面调试（Windows）

无需 Android 也能先验证抓取逻辑和界面：

```powershell
cd android_app
py -m pip install kivy requests beautifulsoup4
py main.py
```

- 验证抓取逻辑：`py -c "import grabber; print(grabber.parse_video_list('<video src=\"https://x.com/a.mp4\"></video>', 'https://x.com', {}))"`
- 桌面调试时视频播放需额外安装 `ffpyplayer`（`py -m pip install ffpyplayer`），无它也能测试抓取/列表。

## 打包成 APK

Buildozer **只能在 Linux 环境**打包。任选下面一种：

### 方式一：WSL2（推荐，本机即可）

```bash
# 在 WSL Ubuntu 中
sudo apt update
sudo apt install -y python3 python3-pip git zip unzip openjdk-17-jdk \
    autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
    libtinfo5 cmake libffi-dev libssl-dev
pip3 install --user buildozer cython
cd /mnt/c/Users/LEGION/CodeBuddy/20260819143148/android_app
buildozer android debug
```

产物在 `android_app/bin/videograbber-0.1.0-arm64-v8a-debug.apk`。

### 方式二：GitHub Actions 自动打包（最省心，Windows 首选）

本项目已内置 `.github/workflows/build-apk.yml`，把 `android_app` 目录推到 GitHub 仓库后会自动出 APK，无需本地装 Linux。

步骤：

```bash
cd android_app
git init
git add .
git commit -m "init android app"
# 在 GitHub 网页上新建一个空仓库（不要勾选初始化 README）
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

推送后：
1. 打开仓库的 **Actions** 页，能看到 `Build Android APK` 任务自动运行。
2. 约 10~20 分钟后变绿，进入该次运行 → 底部 **Artifacts** → 下载 `videograbber-apk`（解压得到 `.apk`）。
3. 以后每次 `git push` 都会自动重新打包；也能在 Actions 页点 **Run workflow** 手动打包。

### 方式二补充：发布到 Releases（打 tag 自动出下载页）

已内置 `.github/workflows/release.yml`，打一个版本 tag 推送，会自动打包并发布到 **Releases** 页，比下载 artifact 更直观：

```bash
git tag v0.1.0
git push origin v0.1.0
```

完成后打开仓库 **Releases** 页，就能看到 `v0.1.0`，直接点 `.apk` 下载安装。

> 说明：目前发布的是 **debug 签名包**，可正常安装运行（个人使用完全够用），但不能上架应用商店。若要正式签名的 release 包（可上架），需要配置 keystore 并存入 GitHub Secrets，可后续再加。

### 方式三：Google Colab（免费 Linux，一次性打包）

在 Colab 中执行同样的 buildozer 命令，把 `bin/*.apk` 下载到本地。

## 安装到手机

1. 把 `.apk` 传到手机（微信/QQ 文件传输、数据线均可）。
2. 点开安装，允许「未知来源」。
3. 打开应用，选择内置的「Demo 静态站点」即可测试流程。

## 添加自己的站点配置

站点配置格式与桌面版**完全一致**（`menu_rules` / `detail.episode_rules` / `player_rules`），只是忽略 `render_js`。

三种方式：
1. **连电脑**：`adb shell` 后把 JSON 放进 `/data/data/org.example.videograbber/files/grabber_configs/`。
2. **改代码**：编辑 `grabber.py` 里的 `BUILTIN_CONFIGS`，重新打包（卸载重装后生效）。
3. **将来扩展**：在 App 内加「配置编辑器」。

## 常见问题

- **抓取失败**：确认站点是静态 HTML（手机无法渲染 JS）；换「Demo 静态站点」或自建 `render_js: false` 配置测试。
- **不能播放**：确认是 `.mp4` 直链；`.m3u8` 请下载后用支持 HLS 的外部播放器。
- **下载的文件在哪**：应用私有目录 `.../files/downloads/`（第一版不开放系统相册/下载目录写入，后续可加）。
