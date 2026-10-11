#!/usr/bin/env python3
"""AI Trend Studio: a local-first hot topic and live session distillation tool."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "db.json"

DEFAULT_KEYWORDS = [
    "AI", "人工智能", "大模型", "LLM", "GPT", "ChatGPT", "OpenAI", "Claude",
    "Gemini", "DeepSeek", "智能体", "Agent", "AIGC", "生成式", "机器学习",
    "深度学习", "神经网络", "自动驾驶", "具身智能", "AI绘画", "AI视频",
    "Sora", "提示词", "多模态", "RAG", "Copilot", "AI应用",
]

DEFAULT_SETTINGS = {
    "keywords": DEFAULT_KEYWORDS,
    "llm": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
        "timeout": 30,
    },
}

SUPPORTED_PLATFORMS = ["douyin", "xiaohongshu", "bilibili", "weibo", "zhihu", "other"]
PLATFORM_LABELS = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "weibo": "微博",
    "zhihu": "知乎",
    "other": "其他",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def compact_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.data: dict[str, Any] = {
            "version": 1,
            "settings": json.loads(json.dumps(DEFAULT_SETTINGS)),
            "trends": {"items": [], "updated_at": None, "sources": []},
            "imports": [],
            "sessions": [],
            "last_refresh": None,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self) -> None:
        with self.lock:
            if not self.path.exists():
                self.save()
                return
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                backup = self.path.with_suffix(".corrupt.json")
                if self.path.exists():
                    backup.write_bytes(self.path.read_bytes())
                loaded = {}
            for key in ("settings", "trends", "imports", "sessions"):
                if key not in loaded:
                    loaded[key] = json.loads(json.dumps(self.data[key]))
            merged_settings = json.loads(json.dumps(DEFAULT_SETTINGS))
            merged_settings.update(loaded.get("settings", {}))
            merged_settings["llm"].update(loaded.get("settings", {}).get("llm", {}))
            loaded["settings"] = merged_settings
            self.data = loaded

    def save(self) -> None:
        with self.lock:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp, self.path)

    def update(self, mutate) -> None:
        with self.lock:
            mutate(self.data)
            self.save()


STORE = Store(DB_PATH)


class FetchError(Exception):
    pass


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    base_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }
    if headers:
        base_headers.update(headers)
    request = urllib.request.Request(url, headers=base_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise FetchError(str(exc)) from exc


def item(
    platform: str,
    kind: str,
    title: str,
    url: str,
    rank: int,
    heat: int | None = None,
    description: str = "",
    author: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": short_id("tr"),
        "platform": platform,
        "kind": kind,
        "title": compact_space(title),
        "description": compact_space(description)[:1200],
        "url": url,
        "rank": rank,
        "heat": heat,
        "author": author,
        "matched_keywords": [],
        "fetched_at": utc_now(),
        "extra": extra or {},
    }


def douyin_trends() -> list[dict[str, Any]]:
    url = "https://www.douyin.com/aweme/v1/web/hot/search/list/"
    payload = fetch_json(url, {"Referer": "https://www.douyin.com/"})
    words = payload.get("data", {}).get("word_list", [])
    result = []
    for rank, row in enumerate(words, 1):
        word = compact_space(str(row.get("word", "")))
        if not word:
            continue
        result.append(item(
            "douyin", "hot_search", word,
            "https://www.douyin.com/search/" + urllib.parse.quote(word),
            rank,
            int(row.get("hot_value") or 0),
            str(row.get("word_title") or ""),
        ))
    return result


def bilibili_popular() -> list[dict[str, Any]]:
    url = "https://api.bilibili.com/x/web-interface/popular?ps=50&pn=1"
    payload = fetch_json(url, {"Referer": "https://www.bilibili.com/"})
    rows = payload.get("data", {}).get("list", [])
    result = []
    for rank, row in enumerate(rows, 1):
        title = compact_space(str(row.get("title", "")))
        bvid = row.get("bvid", "")
        result.append(item(
            "bilibili", "video", title,
            f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            rank,
            int(row.get("stat", {}).get("view") or 0),
            str(row.get("desc") or ""),
            str(row.get("owner", {}).get("name") or ""),
            {"bvid": bvid, "cid": row.get("cid")},
        ))
    return result


def weibo_hot() -> list[dict[str, Any]]:
    payload = fetch_json(
        "https://weibo.com/ajax/side/hotSearch",
        {"Referer": "https://weibo.com/"},
    )
    rows = payload.get("data", {}).get("realtime", [])
    result = []
    for rank, row in enumerate(rows, 1):
        word = compact_space(str(row.get("word", "")))
        if not word:
            continue
        result.append(item(
            "weibo", "hot_search", word,
            "https://s.weibo.com/weibo?q=" + urllib.parse.quote("#" + word + "#"),
            rank,
            int(row.get("num") or 0),
            str(row.get("note") or ""),
        ))
    return result


def zhihu_hot() -> list[dict[str, Any]]:
    payload = fetch_json(
        "https://api.zhihu.com/topstory/hot-list?limit=50",
        {"Referer": "https://www.zhihu.com/hot"},
    )
    rows = payload.get("data", [])
    result = []
    for rank, row in enumerate(rows, 1):
        target = row.get("target", {})
        title = compact_space(str(target.get("title", "")))
        if not title:
            continue
        result.append(item(
            "zhihu", "hot_question", title,
            str(target.get("url", "")).replace("api.zhihu.com/questions", "www.zhihu.com/question"),
            rank,
            parse_cn_number(row.get("detail_text", "")),
            compact_space(str(target.get("excerpt", ""))),
        ))
    return result


def parse_cn_number(value: Any) -> int:
    match = re.search(r"([\d.]+)\s*(万)?", str(value or ""))
    if not match:
        return 0
    try:
        number = float(match.group(1))
    except ValueError:
        return 0
    return int(number * 10000 if match.group(2) else number)


SOURCE_ADAPTERS = {
    "douyin": ("抖音热榜", douyin_trends),
    "bilibili": ("B站热门视频", bilibili_popular),
    "weibo": ("微博热搜", weibo_hot),
    "zhihu": ("知乎热榜", zhihu_hot),
}


def is_ai_relevant(row: dict[str, Any], keywords: list[str]) -> tuple[bool, list[str]]:
    haystack = " ".join([
        str(row.get("title", "")),
        str(row.get("description", "")),
        str(row.get("author", "")),
        json.dumps(row.get("extra", {}), ensure_ascii=False),
    ]).lower()
    matched = []
    for keyword in keywords:
        needle = keyword.lower().strip()
        if not needle or keyword in matched:
            continue
        pattern = (
            r"\b" + re.escape(needle) + r"\b"
            if re.fullmatch(r"[a-z0-9_-]+", needle)
            else re.escape(needle)
        )
        if re.search(pattern, haystack, flags=re.IGNORECASE):
            matched.append(keyword)
    return bool(matched), matched


def refresh_trends(include_unrelated: bool = False) -> dict[str, Any]:
    keywords = STORE.data["settings"].get("keywords", DEFAULT_KEYWORDS)
    sources: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fn): (source_id, label)
            for source_id, (label, fn) in SOURCE_ADAPTERS.items()
        }
        for future in as_completed(futures):
            source_id, label = futures[future]
            started = time.time()
            try:
                rows = future.result(timeout=25)
            except Exception as exc:
                sources.append({
                    "id": source_id, "label": label, "ok": False,
                    "error": str(exc)[:300], "elapsed_ms": int((time.time() - started) * 1000),
                })
                continue
            kept = 0
            for row in rows:
                relevant, matched = is_ai_relevant(row, keywords)
                if relevant:
                    row["matched_keywords"] = matched
                if relevant or include_unrelated:
                    items.append(row)
                    kept += 1
            sources.append({
                "id": source_id, "label": label, "ok": True,
                "count": len(rows), "kept": kept,
                "elapsed_ms": int((time.time() - started) * 1000),
            })

    items.sort(key=lambda row: (row["platform"], row["rank"]))
    result = {
        "items": items,
        "updated_at": utc_now(),
        "sources": sources,
    }

    def mutate(data: dict[str, Any]) -> None:
        data["trends"] = result
        data["last_refresh"] = result["updated_at"]

    STORE.update(mutate)
    return result


def parse_srt_vtt(text: str) -> str:
    text = re.sub(r"^WEBVTT.*?$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(
        r"^\d+\s*$",
        "",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}.*?$",
        "",
        text,
        flags=re.MULTILINE,
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return compact_space(" ".join(lines))


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\r\n?", "\n", text or "")
    chunks = re.split(r"(?<=[。！？!?；;])\s*|\n+", normalized)
    return [compact_space(chunk) for chunk in chunks if len(compact_space(chunk)) >= 8]


STOPWORDS = set("""
我们 你们 他们 这个 那个 这些 那些 然后 就是 可以 可能 因为 所以 但是 如果
一个 大家 其实 现在的时候 你们 我自己 什么 没有 应该 这样 那样 还是 通过 对于
""".split())

CUE_WORDS = [
    "结论", "重点", "关键", "建议", "核心", "价值", "落地", "应用", "场景", "成本",
    "风险", "问题", "机会", "流程", "方法", "工具", "模型", "训练", "推理", "数据",
    "产品", "商业化", "增长", "趋势", "注意", "首先", "其次", "最后", "下一步",
]


def tokenize(text: str) -> list[str]:
    value = text.lower()
    words: list[str] = re.findall(r"[a-z][a-z0-9_-]{1,30}", value)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", value):
        if len(run) == 2:
            words.append(run)
        else:
            words.extend(run[index:index + 2] for index in range(len(run) - 1))
    return [word for word in words if word not in STOPWORDS]


def local_summary(title: str, content: str) -> dict[str, Any]:
    text = compact_space(content)
    sentences = split_sentences(text)
    frequencies: dict[str, int] = {}
    for token in tokenize(text):
        frequencies[token] = frequencies.get(token, 0) + 1
    ranked_words = sorted(frequencies.items(), key=lambda pair: (-pair[1], pair[0]))
    keywords: list[str] = []
    for word, _ in ranked_words:
        if len(word) < 2:
            continue
        if word.upper() not in [keyword.upper() for keyword in keywords]:
            keywords.append(word.upper() if word.isascii() else word)
        if len(keywords) >= 10:
            break

    title_tokens = set(tokenize(title))
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        tokens = tokenize(sentence)
        score = sum(frequencies.get(token, 0) for token in tokens)
        score += sum(4 for cue in CUE_WORDS if cue in sentence)
        score += sum(3 for token in tokens if token in title_tokens)
        score += max(3 - index, 0) * 0.4
        if len(sentence) > 220:
            score *= 0.75
        scored.append((score, index, sentence))

    action_items = [
        sentence for sentence in sentences
        if re.search(r"(建议|需要|应该|下一步|可以尝试|落地|执行|注意)", sentence)
    ][:5]
    risks = [
        sentence for sentence in sentences
        if re.search(r"(风险|限制|缺点|问题|版权|合规|隐私|成本)", sentence)
    ][:4]
    support_sentences = set(action_items + risks)
    selected = sorted(
        sorted([row for row in scored if row[2] not in support_sentences], reverse=True)[:7],
        key=lambda row: row[1],
    )
    key_points = [row[2] for row in selected if row[0] > 0][:6]
    if not key_points and text:
        key_points = [text[:240]]
    return {
        "engine": "local",
        "headline": compact_space(title) or (key_points[0][:80] if key_points else "暂无可提炼内容"),
        "key_points": key_points,
        "keywords": keywords,
        "action_items": action_items,
        "risks": risks,
        "stats": {"characters": len(text), "sentences": len(sentences)},
    }


def normalize_llm_json(raw: str, fallback: dict[str, Any]) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return {
        "engine": "llm",
        "headline": compact_space(str(parsed.get("headline") or fallback["headline"])),
        "key_points": [compact_space(str(point)) for point in parsed.get("key_points", []) if point][:10],
        "keywords": [compact_space(str(word)) for word in parsed.get("keywords", []) if word][:15],
        "action_items": [compact_space(str(action)) for action in parsed.get("action_items", []) if action][:8],
        "risks": [compact_space(str(risk)) for risk in parsed.get("risks", []) if risk][:8],
        "stats": fallback["stats"],
    }


def summarize(title: str, content: str, context: str = "") -> dict[str, Any]:
    fallback = local_summary(title, content)
    llm = STORE.data["settings"].get("llm", {})
    api_key = llm.get("api_key", "")
    if not api_key or not compact_space(content):
        return fallback
    endpoint = llm.get("base_url", "").rstrip("/") + "/chat/completions"
    prompt = (
        "你是中文内容策略分析助手。请从下列平台内容或直播记录中提炼信息，只返回 JSON，"
        "字段为 headline, key_points, keywords, action_items, risks。"
        "key_points 不超过 7 条，保留可执行洞察，不要编造。\n\n"
        f"标题：{title}\n上下文：{context}\n内容：\n{content[:60000]}"
    )
    body = json.dumps({
        "model": llm.get("model", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": "You are a rigorous Chinese content analyst. Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ai-trend-studio/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=int(llm.get("timeout", 30))) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw = payload["choices"][0]["message"]["content"]
        return normalize_llm_json(raw, fallback)
    except Exception as exc:
        fallback = dict(fallback)
        fallback["llm_error"] = str(exc)[:300]
        return fallback


def enrich_bilibili_import(row: dict[str, Any]) -> None:
    if row["platform"] != "bilibili" or not row["url"]:
        return
    match = re.search(r"(BV[0-9A-Za-z]{8,})", row["url"])
    if not match:
        return
    bvid = match.group(1)
    try:
        payload = fetch_json(
            "https://api.bilibili.com/x/web-interface/view?bvid=" + bvid,
            {"Referer": "https://www.bilibili.com/"},
        )
        data = payload.get("data", {})
        row["title"] = row["title"] or compact_space(str(data.get("title", "")))
        row["author"] = row["author"] or compact_space(str(data.get("owner", {}).get("name", "")))
        desc = compact_space(str(data.get("desc", "")))
        if desc and desc not in row["raw_text"]:
            row["raw_text"] = compact_space(desc + "\n" + row["raw_text"])
        cid = data.get("cid")
        if cid:
            player = fetch_json(
                f"https://api.bilibili.com/x/player/wbi/v2?bvid={bvid}&cid={cid}",
                {"Referer": f"https://www.bilibili.com/video/{bvid}/"},
            )
            subtitles = player.get("data", {}).get("subtitle", {}).get("subtitles", [])
            if subtitles:
                subtitle_url = subtitles[0].get("subtitle_url", "")
                if subtitle_url.startswith("//"):
                    subtitle_url = "https:" + subtitle_url
                if subtitle_url:
                    subtitle_payload = fetch_json(subtitle_url, {"Referer": "https://www.bilibili.com/"})
                    text = compact_space(" ".join(
                        str(line.get("content", "")) for line in subtitle_payload.get("body", [])
                    ))
                    if text:
                        row["raw_text"] = compact_space(row["raw_text"] + "\n公开字幕：" + text)
                        row["content_source"] = "public_subtitle"
    except Exception:
        return


def public_state() -> dict[str, Any]:
    with STORE.lock:
        data = json.loads(json.dumps(STORE.data, ensure_ascii=False))
    settings = data.get("settings", {})
    if settings.get("llm", {}).get("api_key"):
        settings["llm"]["api_key"] = "********"
    data["settings"] = settings
    data["platforms"] = PLATFORM_LABELS
    data["source_adapters"] = [
        {"id": source_id, "label": label, "automatic": True}
        for source_id, (label, _) in SOURCE_ADAPTERS.items()
    ]
    data["manual_platforms"] = [
        {"id": "xiaohongshu", "label": "小红书", "reason": "无稳定公开列表接口；用搜索链接和内容导入"},
        {"id": "douyin", "label": "抖音", "reason": "热榜自动抓取；视频正文/字幕和直播间需登录或签名，改为导入"},
    ]
    return data


def sanitize_session(session: dict[str, Any]) -> dict[str, Any]:
    safe = json.loads(json.dumps(session))
    speaker_counts: dict[str, int] = {}
    for event in safe.get("events", []):
        speaker_counts[event.get("speaker") or "未标记"] = speaker_counts.get(event.get("speaker") or "未标记", 0) + 1
    safe["stats"] = {
        "events": len(safe.get("events", [])),
        "speakers": speaker_counts,
        "speech_events": sum(1 for event in safe.get("events", []) if event.get("kind") == "speech"),
        "caption_events": sum(1 for event in safe.get("events", []) if event.get("kind") == "caption"),
    }
    return safe


class Handler(BaseHTTPRequestHandler):
    server_version = "AITrendStudio/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{utc_now()}] {self.address_string()} {fmt % args}")

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_json({"error": "not_found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 5_000_000:
            raise ValueError("invalid_body_size")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self.send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/app.js":
            self.send_file(STATIC_DIR / "app.js", "text/javascript; charset=utf-8")
        elif path == "/styles.css":
            self.send_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
        elif path == "/vendor/lucide.min.js":
            self.send_file(STATIC_DIR / "vendor" / "lucide.min.js", "text/javascript; charset=utf-8")
        elif path == "/favicon.svg":
            self.send_file(STATIC_DIR / "favicon.svg", "image/svg+xml")
        elif path == "/api/health":
            self.send_json({"ok": True, "time": utc_now()})
        elif path == "/api/state":
            self.send_json(public_state())
        elif path == "/api/export":
            attachment = "attachment; filename=ai-trend-studio-export.json"
            body = json.dumps(public_state(), ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", attachment)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_json({"error": "not_found"}, 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = self.body_json()
            if path == "/api/refresh":
                include_unrelated = bool(payload.get("include_unrelated"))
                result = refresh_trends(include_unrelated)
                self.send_json({"ok": True, "trends": result})
            elif path == "/api/settings":
                current = STORE.data["settings"]
                incoming = payload.get("settings", {})
                keywords = [
                    compact_space(str(word)) for word in incoming.get("keywords", [])
                    if compact_space(str(word))
                ]
                incoming_llm = incoming.get("llm", {})
                llm = current["llm"]
                if incoming_llm.get("api_key") not in (None, "", "********"):
                    llm["api_key"] = str(incoming_llm["api_key"]).strip()
                for key in ("base_url", "model"):
                    if incoming_llm.get(key):
                        llm[key] = str(incoming_llm[key]).strip()
                if incoming_llm.get("timeout"):
                    try:
                        llm["timeout"] = max(5, min(120, int(incoming_llm["timeout"])))
                    except ValueError:
                        pass

                def mutate(data: dict[str, Any]) -> None:
                    data["settings"]["keywords"] = keywords or DEFAULT_KEYWORDS

                STORE.update(mutate)
                self.send_json({"ok": True, "state": public_state()})
            elif path == "/api/imports":
                row = {
                    "id": short_id("imp"),
                    "platform": str(payload.get("platform") or "other"),
                    "kind": str(payload.get("kind") or "video"),
                    "title": compact_space(str(payload.get("title") or "")),
                    "url": compact_space(str(payload.get("url") or "")),
                    "author": compact_space(str(payload.get("author") or "")),
                    "raw_text": compact_space(str(payload.get("raw_text") or "")),
                    "content_source": "manual",
                    "summary": None,
                    "created_at": utc_now(),
                }
                if row["platform"] not in SUPPORTED_PLATFORMS:
                    row["platform"] = "other"
                raw_text = row["raw_text"]
                if re.search(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->", raw_text, re.MULTILINE):
                    row["raw_text"] = parse_srt_vtt(raw_text)
                    row["content_source"] = "subtitle_file"
                enrich_bilibili_import(row)
                row["summary"] = summarize(row["title"] or "未命名内容", row["raw_text"], row["url"])
                STORE.update(lambda data: data["imports"].insert(0, row))
                self.send_json({"ok": True, "import": row}, 201)
            elif path == "/api/live/sessions":
                speakers = [
                    compact_space(str(speaker)) for speaker in payload.get("speakers", [])
                    if compact_space(str(speaker))
                ]
                session = {
                    "id": short_id("live"),
                    "title": compact_space(str(payload.get("title") or "未命名直播间")),
                    "platform": str(payload.get("platform") or "other"),
                    "url": compact_space(str(payload.get("url") or "")),
                    "mode": "multi" if payload.get("mode") == "multi" else "single",
                    "status": "live",
                    "speakers": speakers or ["主讲人"],
                    "created_at": utc_now(),
                    "ended_at": None,
                    "events": [],
                    "summary": None,
                }
                STORE.update(lambda data: data["sessions"].insert(0, session))
                self.send_json({"ok": True, "session": sanitize_session(session)}, 201)
            elif re.fullmatch(r"/api/live/sessions/[^/]+/events", path):
                session_id = path.split("/")[4]
                created: dict[str, Any] | None = None

                def add_event(data: dict[str, Any]) -> None:
                    nonlocal created
                    session = next((row for row in data["sessions"] if row["id"] == session_id), None)
                    if not session or session["status"] != "live":
                        raise ValueError("live_session_not_found")
                    speaker = compact_space(str(payload.get("speaker") or session["speakers"][0]))
                    if speaker not in session["speakers"]:
                        session["speakers"].append(speaker)
                    event = {
                        "id": short_id("ev"),
                        "ts": utc_now(),
                        "speaker": speaker,
                        "kind": str(payload.get("kind") or "speech"),
                        "content": compact_space(str(payload.get("content") or "")),
                    }
                    if not event["content"]:
                        raise ValueError("empty_content")
                    session["events"].append(event)
                    created = event

                STORE.update(add_event)
                if not created:
                    raise ValueError("live_session_not_found")
                session = next(row for row in STORE.data["sessions"] if row["id"] == session_id)
                self.send_json({"ok": True, "event": created, "session": sanitize_session(session)}, 201)
            elif re.fullmatch(r"/api/live/sessions/[^/]+/finish", path):
                session_id = path.split("/")[4]
                summary: dict[str, Any] | None = None

                def finish(data: dict[str, Any]) -> None:
                    nonlocal summary
                    session = next((row for row in data["sessions"] if row["id"] == session_id), None)
                    if not session:
                        raise ValueError("session_not_found")
                    transcript = "\n".join(
                        f"{event['speaker']}（{event['kind']}）：{event['content']}"
                        for event in session["events"]
                    )
                    summary = summarize(session["title"], transcript, session["url"])
                    session["status"] = "finished"
                    session["ended_at"] = utc_now()
                    session["summary"] = summary

                STORE.update(finish)
                if not summary:
                    raise ValueError("session_not_found")
                session = next(row for row in STORE.data["sessions"] if row["id"] == session_id)
                self.send_json({"ok": True, "session": sanitize_session(session)})
            else:
                self.send_json({"error": "not_found"}, 404)
        except json.JSONDecodeError:
            self.send_json({"error": "invalid_json"}, 400)
        except (ValueError, KeyError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": "server_error", "detail": str(exc)[:400]}, 500)


def main() -> None:
    host = os.environ.get("AITREND_HOST", "127.0.0.1")
    port = int(os.environ.get("AITREND_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"AI Trend Studio running at http://{host}:{port}")
    print("Data file:", DB_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
