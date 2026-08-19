# -*- coding: utf-8 -*-
"""视频抓取核心逻辑（Android 版，无桌面依赖）

从桌面版 video_grabber.py 移植而来，去掉了 Playwright / PyQt5 / yt-dlp 依赖：
- fetch_html: 仅用 requests 静态抓取（手机上无法渲染 JS，render_js 配置会被忽略）
- parse_links / parse_video_list / resolve_playable: 与桌面版保持一致的解析规则
- download_file: 用 requests 流式下载 mp4 等直链，支持进度回调
"""

import os
import re
import json
import glob

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 "
                  "Chrome/120.0.0.0 Safari/537.36"
}

MEDIA_EXTS = (".mp4", ".m3u8", ".webm", ".mkv", ".ts", ".flv", ".mov", ".avi")

DEFAULT_RULES = [
    {"type": "video_tag", "src_attrs": ["src", "data-src"]},
    {"type": "href_ext", "extensions": [".mp4", ".m3u8"]},
    # 排除 <> 防止把 HTML 标签吞进 URL
    {"type": "regex", "pattern": r'https?://[^\s"\'<>]+\.(?:mp4|m3u8)[^\s"\'<>]*'},
]

# 内置示例配置（首次运行时会写入手机应用数据目录，方便后续编辑）
BUILTIN_CONFIGS = {
    "example_static_site.json": {
        "name": "Demo 静态站点（示例）",
        "default_url": "https://example.com/videos",
        "render_js": False,
        "menu_rules": [
            {"type": "css_links", "selector": ".video-list a",
             "link_attr": "href", "title_attr": "text"},
            {"type": "href_match", "pattern": "/detail/",
             "title_pattern": "第.{1,4}集|.{2,30}剧"}
        ],
        "detail": {
            "episode_rules": [
                {"type": "css_links", "selector": ".episode-list a",
                 "link_attr": "href", "title_attr": "text"},
                {"type": "href_match", "pattern": "/play/|/video/",
                 "title_pattern": "第.{1,4}集"}
            ],
            "player_rules": [
                {"type": "video_tag", "src_attrs": ["src", "data-src"]},
                {"type": "href_ext", "extensions": [".mp4", ".m3u8"]},
                {"type": "regex",
                 "pattern": r'https?://[^\s"\'<>]+\.(?:mp4|m3u8)[^\s"\'<>]*'},
                {"type": "iframe", "src_attr": "src"}
            ]
        },
        "rules": [
            {"type": "video_tag", "src_attrs": ["src", "data-src"]},
            {"type": "href_ext", "extensions": [".mp4", ".m3u8"]},
            {"type": "regex",
             "pattern": r'https?://[^\s"\'<>]+\.(?:mp4|m3u8)[^\s"\'<>]*'},
            {"type": "css", "selector": "video source", "attr": "src"},
            {"type": "iframe", "src_attr": "src"}
        ]
    }
}


def ensure_config_dir(config_dir):
    """确保配置目录存在，并在为空时写入内置示例配置"""
    os.makedirs(config_dir, exist_ok=True)
    if not glob.glob(os.path.join(config_dir, "*.json")):
        for fname, cfg in BUILTIN_CONFIGS.items():
            with open(os.path.join(config_dir, fname), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_configs(config_dir):
    """读取配置目录下所有 JSON 配置"""
    ensure_config_dir(config_dir)
    configs = []
    for path in sorted(glob.glob(os.path.join(config_dir, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("name", os.path.basename(path))
            cfg.setdefault("render_js", False)
            cfg.setdefault("render_wait_ms", 5000)
            cfg.setdefault("rules", DEFAULT_RULES)
            cfg["_path"] = path
            configs.append(cfg)
        except Exception as e:
            print(f"[配置加载失败] {path}: {e}")
    return configs


def fetch_html(url, config):
    """抓取页面 HTML（仅静态 requests，忽略 render_js）"""
    resp = requests.get(url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_video_list(html, base_url, config):
    """按配置中的媒体解析规则解析页面中的视频链接（播放源）"""
    rules = config.get("rules") or DEFAULT_RULES
    soup = BeautifulSoup(html, "html.parser")
    videos = []
    seen = set()

    def add(url, title):
        full = urljoin(base_url, (url or "").strip())
        if not full.startswith(("http://", "https://")) or full in seen:
            return
        seen.add(full)
        videos.append({
            "title": title or f"video_{len(videos) + 1}",
            "url": full,
        })

    for rule in rules:
        rule_type = rule.get("type")
        try:
            if rule_type == "video_tag":
                for v in soup.find_all("video"):
                    for attr in rule.get("src_attrs", ["src", "data-src"]):
                        src = v.get(attr)
                        if src:
                            add(src, v.get("title") or v.get("aria-label"))
                    for s in v.find_all("source"):
                        if s.get("src"):
                            add(s["src"], v.get("title") or s.get("title"))

            elif rule_type == "href_ext":
                exts = rule.get("extensions", [".mp4", ".m3u8"])
                for a in soup.find_all("a", href=True):
                    href_lower = a["href"].strip().lower()
                    if any(href_lower.endswith(ext) for ext in exts):
                        add(a["href"], a.get_text(strip=True) or os.path.basename(a["href"]))

            elif rule_type == "regex":
                pattern = rule.get("pattern")
                if pattern:
                    for m in re.finditer(pattern, html, re.IGNORECASE):
                        add(m.group(0), None)

            elif rule_type == "css":
                selector = rule.get("selector")
                attr = rule.get("attr", "src")
                for el in soup.select(selector or ""):
                    val = el.get(attr) or el.get("data-src") or el.get("href")
                    if val:
                        add(val, el.get("title") or el.get_text(strip=True) or None)

            elif rule_type == "iframe":
                attr = rule.get("src_attr", "src")
                for f in soup.find_all("iframe"):
                    if f.get(attr):
                        add(f[attr], f.get("title"))
        except Exception as e:
            print(f"[规则解析异常] type={rule_type} error={e}")

    return videos


def _extract_title(el, rule):
    """从元素中按规则提取标题"""
    title_attr = rule.get("title_attr")
    if title_attr and title_attr != "text":
        val = el.get(title_attr)
        if val:
            return val.strip()
    title_selector = rule.get("title_selector")
    if title_selector:
        sub = el.select_one(title_selector)
        if sub:
            return sub.get_text(strip=True)
    if title_attr == "text":
        return el.get_text(strip=True)
    return el.get("title") or el.get_text(strip=True)


def parse_links(html, base_url, link_rules):
    """按链接提取规则（css_links / href_match）解析菜单或剧集列表

    返回 [{title, url}]，自动 urljoin 与去重
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen = set()

    def add(title, url):
        full = urljoin(base_url, (url or "").strip())
        if not full.startswith(("http://", "https://")) or full in seen:
            return
        seen.add(full)
        items.append({"title": (title or "").strip() or f"item_{len(items) + 1}", "url": full})

    for rule in link_rules or []:
        rule_type = rule.get("type")
        try:
            if rule_type == "css_links":
                selector = rule.get("selector") or "a"
                link_attr = rule.get("link_attr", "href")
                for el in soup.select(selector):
                    href = el.get(link_attr) or el.get("href")
                    if href:
                        add(_extract_title(el, rule), href)

            elif rule_type == "href_match":
                pattern = rule.get("pattern") or ""
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if re.search(pattern, href, re.IGNORECASE):
                        title = a.get_text(strip=True)
                        tp = rule.get("title_pattern")
                        if tp:
                            m = re.search(tp, title)
                            if m:
                                title = m.group(0)
                        add(title or os.path.basename(href), href)
        except Exception as e:
            print(f"[链接解析异常] type={rule_type} error={e}")

    return items


def detail_config(config):
    """返回用于抓取详情页的配置（detail 字段可覆盖 render_js / render_wait_ms）"""
    detail = config.get("detail") or {}
    merged = dict(config)
    if "render_js" in detail:
        merged["render_js"] = detail["render_js"]
    if "render_wait_ms" in detail:
        merged["render_wait_ms"] = detail["render_wait_ms"]
    return merged


def resolve_playable(item, config):
    """把条目解析成可播放/可下载的媒体源

    - 本身是媒体文件(.mp4/.m3u8/...) -> 直接返回
    - 是页面 -> 抓取页面用 player_rules 解析，取第一个媒体源
    """
    result = dict(item)
    url = item.get("url", "")
    if url.lower().endswith(MEDIA_EXTS):
        return result

    detail = config.get("detail") or {}
    player_rules = detail.get("player_rules") or config.get("rules") or DEFAULT_RULES
    player_cfg = dict(detail_config(config), rules=player_rules)
    try:
        html = fetch_html(url, player_cfg)
        sources = parse_video_list(html, url, player_cfg)
        if sources:
            result["url"] = sources[0]["url"]
            if sources[0].get("title"):
                result["media_title"] = sources[0]["title"]
            return result
    except Exception as e:
        print(f"[解析播放源失败] {url}: {e}")
    return result


def guess_ext(url, content_type=None):
    """根据 URL 或 Content-Type 推断媒体文件扩展名"""
    lower = url.lower()
    for ext in MEDIA_EXTS:
        if lower.endswith(ext):
            return ext
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        mapping = {
            "video/mp4": ".mp4",
            "video/webm": ".webm",
            "video/x-matroska": ".mkv",
            "application/vnd.apple.mpegurl": ".m3u8",
            "application/x-mpegurl": ".m3u8",
        }
        if ct in mapping:
            return mapping[ct]
    return ".mp4"


def download_file(url, dest, progress_callback=None):
    """流式下载媒体直链到本地，progress_callback(done, total)"""
    resp = requests.get(url, headers=HEADERS, stream=True, timeout=30)
    resp.raise_for_status()
    total = int(resp.headers.get("Content-Length") or 0)
    done = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            f.write(chunk)
            done += len(chunk)
            if progress_callback:
                progress_callback(done, total)
    return dest


def sanitize_filename(name):
    """把标题清洗成安全文件名"""
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", name or "video")
    return name[:80] or "video"
