# -*- coding: utf-8 -*-
"""通用视频抓取客户端（Android 版）

Kivy 实现，手机本机独立运行：
- 配置驱动的「菜单 -> 剧集 -> 播放/下载」多级抓取
- 静态 requests 抓取（手机上不支持 Playwright JS 渲染）
- 内置 Kivy 播放器（mp4 等直链）
- requests 流式下载到应用私有目录

用法：详见 README.md；本地桌面调试可 `pip install kivy` 后 `python main.py`。
"""

import os
import re
import threading

from kivy.config import Config
Config.set("kivy", "video", "ffpyplayer")

from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock, mainthread
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button
from kivy.properties import StringProperty, NumericProperty, ObjectProperty

import grabber

KV = """
#:import dp kivy.metrics.dp

<ItemButton>:
    size_hint_y: None
    height: dp(56)
    halign: 'left'
    valign: 'middle'
    text_size: self.size[0] - dp(20), None
    on_release: app.on_item_tap(self.screen_type, self.index)

<MenuScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(8)
        spacing: dp(6)

        Label:
            text: '通用视频抓取'
            font_size: '20sp'
            size_hint_y: None
            height: dp(36)

        BoxLayout:
            size_hint_y: None
            height: dp(48)
            spacing: dp(6)
            Spinner:
                id: config_spinner
                text: '选择站点配置'
                size_hint_x: 0.45
                text_autoupdate: True
            TextInput:
                id: url_input
                hint_text: '输入网址'
                multiline: False
                size_hint_x: 0.55
        BoxLayout:
            size_hint_y: None
            height: dp(48)
            spacing: dp(6)
            Button:
                text: '加载视频菜单'
                on_release: app.load_menu()
            Button:
                text: '刷新配置'
                on_release: app.refresh_config_spinner()

        Label:
            text: '视频菜单：'
            size_hint_y: None
            height: dp(28)
            halign: 'left'
            text_size: self.size

        RecycleView:
            id: menu_rv
            viewclass: 'ItemButton'
            RecycleBoxLayout:
                default_size: None, dp(56)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'

        ScrollView:
            size_hint_y: None
            height: dp(96)
            Label:
                id: log_label
                text: '就绪'
                size_hint_y: None
                height: self.texture_size[1]
                text_size: self.width, None
                halign: 'left'
                valign: 'top'
                font_size: '13sp'

<EpisodeScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(8)
        spacing: dp(6)
        BoxLayout:
            size_hint_y: None
            height: dp(48)
            spacing: dp(6)
            Button:
                text: '返回'
                on_release: app.back_to_menu()
            Label:
                id: ep_title
                text: '剧集列表'
                halign: 'center'
                valign: 'middle'
        BoxLayout:
            size_hint_y: None
            height: dp(48)
            spacing: dp(6)
            Button:
                text: '播放选中'
                on_release: app.play_episode()
            Button:
                text: '下载选中'
                on_release: app.download_episode()
        RecycleView:
            id: ep_rv
            viewclass: 'ItemButton'
            RecycleBoxLayout:
                default_size: None, dp(56)
                default_size_hint: 1, None
                size_hint_y: None
                height: self.minimum_height
                orientation: 'vertical'
        ScrollView:
            size_hint_y: None
            height: dp(72)
            Label:
                id: log_label
                text: ''
                size_hint_y: None
                height: self.texture_size[1]
                text_size: self.width, None
                halign: 'left'
                valign: 'top'
                font_size: '13sp'

<PlayerScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(6)
        spacing: dp(6)
        BoxLayout:
            size_hint_y: None
            height: dp(48)
            spacing: dp(6)
            Button:
                text: '返回'
                on_release: app.stop_and_back()
            Label:
                id: player_title
                text: '播放中'
                halign: 'center'
                valign: 'middle'
        Video:
            id: video
            state: 'stop'
            options: {'eos': 'stop'}
            fit_mode: 'contain'

ScreenManager:
    id: sm
    MenuScreen:
        id: menu_screen
        name: 'menu'
    EpisodeScreen:
        id: episode_screen
        name: 'episode'
    PlayerScreen:
        id: player_screen
        name: 'player'
"""


class ItemButton(Button):
    """列表行：text 显示标题，index/screen_type 用于点击回调"""
    index = NumericProperty(0)
    screen_type = StringProperty("menu")


class MenuScreen(Screen):
    pass


class EpisodeScreen(Screen):
    pass


class PlayerScreen(Screen):
    video = ObjectProperty(None)


class GrabberApp(App):
    title = "通用视频抓取"

    def build(self):
        self.config_dir = os.path.join(self.user_data_dir, "grabber_configs")
        self.download_dir = os.path.join(self.user_data_dir, "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

        self.configs = grabber.load_configs(self.config_dir)
        self.menu_items = []
        self.episode_items = []
        self.menu_has_detail = False
        self._current_screen = "menu"
        self._ep_title = ""
        return Builder.load_string(KV)

    # ---------- 配置 ----------
    def refresh_config_spinner(self):
        self.configs = grabber.load_configs(self.config_dir)
        names = [c.get("name", "未命名") for c in self.configs]
        spinner = self.root.ids.menu_screen.ids.config_spinner
        spinner.values = names
        if names:
            spinner.text = names[0]
            self.on_config_changed(names[0])
        self.log(f"已加载 {len(self.configs)} 个站点配置")

    def on_config_changed(self, name):
        for cfg in self.configs:
            if cfg.get("name") == name:
                self.root.ids.menu_screen.ids.url_input.text = cfg.get("default_url", "")
                break

    def current_config(self):
        name = self.root.ids.menu_screen.ids.config_spinner.text
        for cfg in self.configs:
            if cfg.get("name") == name:
                return cfg
        return {}

    # ---------- 日志 / 工具 ----------
    @mainthread
    def log(self, msg, screen="menu"):
        screen_obj = self.root.ids.get(screen + "_screen")
        if screen_obj:
            screen_obj.ids.log_label.text = msg

    # ---------- 菜单抓取 ----------
    def load_menu(self):
        config = self.current_config()
        url = self.root.ids.menu_screen.ids.url_input.text.strip()
        if not config:
            self.log("请先选择站点配置")
            return
        if not url:
            self.log("请输入网址")
            return
        self.log(f"正在抓取菜单: {url} ...")

        def worker():
            try:
                html = grabber.fetch_html(url, config)
                detail = config.get("detail") or {}
                menu_rules = config.get("menu_rules")
                if menu_rules:
                    items = grabber.parse_links(html, url, menu_rules)
                    has_detail = bool(detail.get("episode_rules") or detail.get("player_rules"))
                else:
                    items = grabber.parse_video_list(html, url, config)
                    has_detail = False
                self._on_menu_loaded(items, has_detail, url)
            except Exception as e:
                self.log(f"抓取失败: {e}")

        threading.Thread(target=worker, daemon=True).start()

    @mainthread
    def _on_menu_loaded(self, items, has_detail, url):
        self.menu_items = items
        self.menu_has_detail = has_detail
        rv = self.root.ids.menu_screen.ids.menu_rv
        rv.data = [
            {"text": it["title"], "index": i, "screen_type": "menu"}
            for i, it in enumerate(items)
        ]
        if not items:
            self.log("未找到菜单/视频，请检查 menu_rules 或 rules 配置")
        else:
            hint = "（点按获取剧集）" if has_detail else "（点按直接播放）"
            self.log(f"找到 {len(items)} 个条目 {hint}")

    # ---------- 点击回调 ----------
    def on_item_tap(self, screen_type, index):
        if screen_type == "menu":
            if not (0 <= index < len(self.menu_items)):
                return
            item = self.menu_items[index]
            if self.menu_has_detail:
                self.fetch_episodes(item)
            else:
                self.play_item(item)
        elif screen_type == "episode":
            if 0 <= index < len(self.episode_items):
                self._selected_ep = index
                self.log(f"已选中: {self.episode_items[index]['title']}", "episode")

    # ---------- 剧集抓取 ----------
    def fetch_episodes(self, item):
        config = self.current_config()
        detail = config.get("detail") or {}
        ep_rules = detail.get("episode_rules")
        self._ep_title = item["title"]
        self.log(f"正在获取剧集: {item['title']} ...")

        def worker():
            try:
                if not ep_rules:
                    eps = [grabber.resolve_playable(item, config)]
                else:
                    dcfg = grabber.detail_config(config)
                    html = grabber.fetch_html(item["url"], dcfg)
                    eps = grabber.parse_links(html, item["url"], ep_rules)
                    if not eps:
                        eps = [grabber.resolve_playable(item, config)]
                self._on_episodes_loaded(eps)
            except Exception as e:
                self.log(f"获取剧集失败: {e}", "episode")

        threading.Thread(target=worker, daemon=True).start()

    @mainthread
    def _on_episodes_loaded(self, eps):
        self.episode_items = eps
        self.root.ids.episode_screen.ids.ep_title.text = self._ep_title
        rv = self.root.ids.episode_screen.ids.ep_rv
        rv.data = [
            {"text": it["title"], "index": i, "screen_type": "episode"}
            for i, it in enumerate(eps)
        ]
        self.log(f"获取到 {len(eps)} 个剧集", "episode")
        self.root.current = "episode"

    def back_to_menu(self):
        self.root.current = "menu"

    # ---------- 播放 ----------
    def play_episode(self):
        idx = getattr(self, "_selected_ep", 0)
        if 0 <= idx < len(self.episode_items):
            self.play_item(self.episode_items[idx])
        else:
            self.log("请先选中要播放的剧集", "episode")

    def play_item(self, item):
        config = self.current_config()
        self.log(f"正在解析播放源: {item['title']} ...")

        def worker():
            try:
                playable = grabber.resolve_playable(item, config)
                self._on_play(playable)
            except Exception as e:
                self.log(f"解析播放源失败: {e}")

        threading.Thread(target=worker, daemon=True).start()

    @mainthread
    def _on_play(self, playable):
        url = playable.get("url", "")
        title = playable.get("title", url)
        media_title = playable.get("media_title")
        if not url:
            self.log("未找到可播放的媒体源")
            return
        lower = url.lower()
        if lower.endswith(".m3u8"):
            self.log("m3u8 HLS 流手机端暂不支持内置播放，请下载后使用外部播放器，"
                     "或改用 mp4 直链")
            return
        self.log(f"播放: {title}" + (f" [{media_title}]" if media_title else ""))
        ps = self.root.ids.player_screen
        ps.ids.player_title.text = title
        ps.ids.video.source = url
        ps.ids.video.state = "play"
        self.root.current = "player"

    def stop_and_back(self):
        ps = self.root.ids.player_screen
        ps.ids.video.state = "stop"
        ps.ids.video.source = ""
        self.root.current = "episode"

    # ---------- 下载 ----------
    def download_episode(self):
        idx = getattr(self, "_selected_ep", 0)
        if not (0 <= idx < len(self.episode_items)):
            self.log("请先选中要下载的剧集", "episode")
            return
        item = self.episode_items[idx]
        self.start_download(item)

    def start_download(self, item):
        config = self.current_config()
        self.log(f"正在解析并下载: {item['title']} ...", "episode")

        def worker():
            try:
                playable = grabber.resolve_playable(item, config)
                url = playable.get("url", "")
                if url.lower().endswith(".m3u8"):
                    self.log("m3u8 流无法用简单下载获取，请使用外部工具", "episode")
                    return
                title = playable.get("title") or item.get("title") or "video"
                fname = grabber.sanitize_filename(title)
                ext = grabber.guess_ext(url)
                dest = os.path.join(self.download_dir, fname + ext)
                self.log(f"开始下载: {fname}{ext} ...", "episode")

                def cb(done, total):
                    if total:
                        pct = int(done * 100 / total)
                        self.log(f"下载中 {pct}% ...", "episode")

                grabber.download_file(url, dest, progress_callback=cb)
                self.log(f"下载完成: {dest}", "episode")
            except Exception as e:
                self.log(f"下载失败: {e}", "episode")

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Android 返回键 ----------
    def on_back_request(self):
        sm = self.root
        if sm.current == "player":
            self.stop_and_back()
            return True
        elif sm.current == "episode":
            self.back_to_menu()
            return True
        return False


if __name__ == "__main__":
    GrabberApp().run()
