"""背诵宝 Web —— 浏览器端入口。

输入：中文/英文文章、博客、演讲稿、字幕（粘贴文本 / 网页链接 / 上传文档）
输出：交互式背诵看板（原文意群分块、逐块复习表、每日打卡清单）

用法:
    python app.py
    # 或生产环境:
    gunicorn app:app --bind 0.0.0.0:$PORT
"""

import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

from flask import Flask, render_template_string, request, redirect, url_for, send_file

# 把 article_recite 加入 path
sys.path.insert(0, str(Path(__file__).parent))

from article_recite.analyzer import analyze
from article_recite.downloader import fetch_web_article, domain_of
from article_recite.outputs.recite_book import generate as generate_recite_book
from article_recite.parser import parse_article, parse_file, detect_language
from article_recite.planner import build_schedule

app = Flask(__name__)

OUTPUT_ROOT = Path(__file__).parent / "output"

_LANG_LABELS = {"zh": "中文", "en": "English"}
_SOURCE_LABELS = {"article": "文章", "blog": "博客", "speech": "演讲稿", "subtitle": "字幕"}


# ── 首页 ────────────────────────────────────

HOME_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="背诵宝">
<link rel="icon" type="image/png" href="/static/recite.png">
<link rel="apple-touch-icon" href="/static/recite-180.png">
<link rel="manifest" href="/manifest.json">
<title>背诵宝 — 意群分块 · 艾宾浩斯复习 · 背诵打卡</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family:"PingFang SC","Microsoft YaHei",sans-serif;
    background:#f3faf7; color:#22332f;
    display:flex; justify-content:center; padding:40px 16px;
  }
  .wrap { max-width:520px; width:100%; }
  h1 { text-align:center; font-size:24px; margin-bottom:8px; color:#0a5f52; }
  .sub { text-align:center; color:#86a09a; font-size:13px; margin-bottom:28px; }
  .card {
    background:#fff; border-radius:12px; padding:28px 24px;
    box-shadow:0 2px 8px rgba(14,124,107,.08); margin-bottom:16px;
  }
  .card h2 { font-size:16px; color:#0e7c6b; margin-bottom:14px; }
  label { display:block; font-size:13px; font-weight:600; color:#4a5f59; margin-bottom:4px; }
  input, select, textarea {
    width:100%; padding:10px 12px; font-size:14px; border:1px solid #d8e8e1;
    border-radius:6px; margin-bottom:12px; font-family:inherit; background:#fff;
  }
  textarea { min-height:140px; resize:vertical; }
  input:focus, select:focus, textarea:focus { outline:none; border-color:#0e7c6b; }
  .hint { font-size:11px; color:#a5b9b2; margin-top:-8px; margin-bottom:14px; }
  .divider { text-align:center; color:#c8d9d3; margin:16px 0; font-size:12px; }
  button {
    width:100%; padding:12px; font-size:15px; font-weight:700;
    background:linear-gradient(120deg,#0e7c6b,#0f8f7b); color:#fff; border:none;
    border-radius:8px; cursor:pointer; transition:background 0.2s;
  }
  button:hover { background:#0a6a5b; }
  .msg { padding:12px; border-radius:6px; font-size:13px; margin-top:12px; display:none; }
  .msg.info { background:#e8f4fd; color:#1a6aaa; }
  .msg.done { background:#e6f9e6; color:#2a7a2a; }
  .msg.err { background:#fde8e8; color:#a33; }
  .nav { text-align:center; margin-top:8px; }
  .nav a { font-size:13px; color:#0e7c6b; text-decoration:none; font-weight:600; }
</style>
</head>
<body>
<div class="wrap">
  <h1>📖 背诵宝</h1>
  <p class="sub">文章 / 演讲稿 / 字幕 → 意群分块 + 艾宾浩斯复习计划</p>

  <div class="card">
    <h2>📥 输入材料</h2>
    <form method="POST" action="/process" enctype="multipart/form-data">
      <label>粘贴文本</label>
      <textarea name="text" placeholder="把文章 / 演讲稿 / 字幕正文粘贴到这里…">{{ text or '' }}</textarea>
      <label>网页文章链接（博客等）</label>
      <input name="url" type="url" placeholder="https://…（自动抓取正文）" value="{{ url or '' }}">
      <label>上传文档</label>
      <input name="file" type="file" accept=".srt,.txt,.md,.rtf,.docx,.pdf">
      <label>标题（可选）</label>
      <input name="title" type="text" placeholder="给这份背诵材料取个名字">
      <p class="hint">以上三种方式任选其一：文本、链接、或文档（.srt / .txt / .md / .docx / .pdf）。</p>
      <button type="submit">🚀 生成背诵材料包</button>
    </form>
  </div>

  <div class="nav">
    <a href="/library">📚 查看背诵文库</a>
  </div>

  {% if error %}
  <div class="msg err" style="display:block">{{ error }}</div>
  {% endif %}
</div>
<script>
if ('serviceWorker' in navigator) { window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js').catch(function () {}); }); }
</script>
</body>
</html>"""

WORKING_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>处理中...</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f3faf7; display:flex; justify-content:center; align-items:center; min-height:100vh; }
  .box { text-align:center; padding:40px; }
  .spinner { width:48px; height:48px; border:4px solid #e2efe9; border-top:4px solid #0e7c6b; border-radius:50%; animation:spin 0.8s linear infinite; margin:0 auto 20px; }
  @keyframes spin { to { transform:rotate(360deg); } }
  h2 { font-size:18px; color:#0a5f52; margin-bottom:8px; }
  p { font-size:13px; color:#86a09a; }
  .meta { margin-top:16px; font-size:12px; color:#a5b9b2; }
</style>
</head>
<body>
<div class="box">
  <div class="spinner"></div>
  <h2>AI 正在切分意群、排复习计划...</h2>
  <p>{{ status }}</p>
  <p class="meta">通常需要 10-60 秒，请耐心等候</p>
</div>
</body>
</html>"""


@app.route("/")
def home():
    return render_template_string(HOME_HTML)


@app.route("/manifest.json")
def manifest():
    return send_file(str(Path(__file__).parent / "manifest.json"), mimetype="application/json")


@app.route("/sw.js")
def service_worker():
    """根路径提供 service worker（scope=根，否则 404 导致 PWA 不可安装）。
    Service-Worker-Allowed + no-cache 保证更新能及时生效。"""
    resp = send_file(
        str(Path(__file__).parent / "static" / "sw.js"), mimetype="text/javascript"
    )
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/process", methods=["POST"])
def process():
    url = request.form.get("url", "").strip()
    text = request.form.get("text", "").strip()
    uploaded = request.files.get("file")
    title = request.form.get("title", "").strip()
    api_key = _load_api_key()

    if not api_key:
        return render_template_string(
            HOME_HTML,
            error="未设置 DEEPSEEK_API_KEY。请在 .env 或环境变量中配置。",
            url=url, text=text, title=title,
        )

    try:
        # ── 输入分流 ──
        if url:
            parsed, material_id, source_type, fallback_title = _from_url(url, title)
        elif text:
            parsed, material_id, source_type, fallback_title = _from_text(text, title)
        elif uploaded and uploaded.filename:
            parsed, material_id, source_type, fallback_title = _from_upload(uploaded, title)
        else:
            return render_template_string(
                HOME_HTML,
                error="请粘贴文本、输入链接或上传文件。",
                title=title,
            )

        if parsed.word_count < 20:
            raise ValueError("材料内容过短（不足 20 字/词），无法有效分块，请补充内容。")

        # ── 语言检测 ──
        lang = detect_language(parsed.full_text)

        # ── AI 意群分块 ──
        result = analyze(
            full_text=parsed.full_text,
            title=title or fallback_title,
            language=lang,
            source_type=source_type,
            api_key=api_key,
            model="deepseek-chat",
        )
        material = result.material

        if not material.chunks:
            raise RuntimeError("AI 未能从材料中切分出有效意群块，请更换材料重试。")

        # ── 艾宾浩斯计划 ──
        schedule = build_schedule(len(material.chunks))

        # ── 保存 ──
        final_title = title or material.title_suggested or fallback_title
        meta = {
            "material_id": material_id,
            "title": final_title,
            "language": lang,
            "source_type": source_type,
            "truncated": result.truncated,
            "created": date.today().isoformat(),
        }
        out_dir = OUTPUT_ROOT / material_id
        out_dir.mkdir(parents=True, exist_ok=True)
        from article_recite.analyzer import save_material
        save_material(material, meta, result.usage, out_dir / "material.json")

        # ── 生成看板 ──
        recite_path = out_dir / "recite.html"
        generate_recite_book(material, meta, parsed, schedule, result.usage, recite_path)

        return redirect(url_for("result", material_id=material_id))

    except ValueError as e:
        return render_template_string(HOME_HTML, error=str(e), url=url, text=text, title=title)
    except RuntimeError as e:
        return render_template_string(HOME_HTML, error=str(e), url=url, text=text, title=title)
    except Exception as e:
        return render_template_string(
            HOME_HTML,
            error=f"未知错误: {e}",
            url=url, text=text, title=title,
        )


@app.route("/result/<material_id>")
def result(material_id):
    """直接提供生成的 recite.html。"""
    recite_path = OUTPUT_ROOT / material_id / "recite.html"
    if not recite_path.exists():
        return "背诵材料不存在，可能已被清理。请重新生成。", 404
    return send_file(str(recite_path), mimetype="text/html; charset=utf-8")


@app.route("/library")
def library():
    """文库 —— 列出所有已生成的背诵看板。"""
    items = []
    if OUTPUT_ROOT.exists():
        for subdir in sorted(OUTPUT_ROOT.iterdir(), reverse=True):
            if not subdir.is_dir():
                continue
            material_json = subdir / "material.json"
            if not material_json.exists():
                continue
            try:
                data = json.loads(material_json.read_text(encoding="utf-8"))
                meta = data.get("meta", {})
                mat = data.get("material", {})
                usage = data.get("usage", {})
                chunks = mat.get("chunks", [])
                items.append({
                    "material_id": meta.get("material_id", subdir.name),
                    "title": meta.get("title") or subdir.name,
                    "lang": meta.get("language", "en"),
                    "lang_label": _LANG_LABELS.get(meta.get("language", "en"), meta.get("language", "en")),
                    "source_label": _SOURCE_LABELS.get(meta.get("source_type", "article"), meta.get("source_type", "article")),
                    "chunk_count": len(chunks),
                    "words": sum(len(c.get("text", "")) for c in chunks),
                    "created": meta.get("created", ""),
                    "cost_cny": usage.get("cost_cny", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                })
            except Exception:
                pass

    return render_template_string(LIBRARY_HTML, items=items)


LIBRARY_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="背诵宝">
<link rel="icon" type="image/png" href="/static/recite.png">
<link rel="apple-touch-icon" href="/static/recite-180.png">
<link rel="manifest" href="/manifest.json">
<title>文库 — 背诵宝</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f3faf7; color:#22332f; }
  .wrap { max-width:600px; margin:0 auto; padding:24px 16px; }
  h1 { text-align:center; font-size:20px; color:#0a5f52; margin-bottom:6px; }
  .sub { text-align:center; color:#86a09a; font-size:12px; margin-bottom:24px; }
  .nav { text-align:center; margin-bottom:20px; }
  .nav a { font-size:13px; color:#0e7c6b; text-decoration:none; font-weight:600; }
  .card {
    display:block; background:#fff; border-radius:10px; padding:16px 20px;
    margin-bottom:10px; box-shadow:0 1px 4px rgba(14,124,107,.06);
    text-decoration:none; color:inherit; transition:box-shadow 0.2s;
  }
  .card:hover { box-shadow:0 2px 12px rgba(14,124,107,.14); }
  .card h3 { font-size:15px; color:#0a5f52; margin-bottom:6px; }
  .card .badges { margin-bottom:6px; }
  .card .badge {
    display:inline-block; font-size:11px; padding:1px 10px; border-radius:10px;
    background:#e4f4ef; color:#0a5f52; margin-right:6px;
  }
  .card .badge.lang-en { background:#e8f4fd; color:#1a6aaa; }
  .card .badge.lang-zh { background:#fdf1dd; color:#b45309; }
  .card .meta { font-size:12px; color:#86a09a; }
  .card .meta span { margin-right:14px; }
  .empty { text-align:center; padding:60px 20px; color:#a5b9b2; font-size:14px; }
  .footer { text-align:center; padding:24px; color:#bccfca; font-size:11px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>📚 背诵文库</h1>
  <p class="sub">{{ items|length }} 份背诵材料</p>
  <div class="nav"><a href="/">← 返回首页</a></div>

  {% if items %}
    {% for item in items %}
    <a class="card" href="/result/{{ item.material_id }}">
      <h3>{{ item.title }}</h3>
      <div class="badges">
        <span class="badge lang-{{ item.lang }}">🌐 {{ item.lang_label }}</span>
        <span class="badge">📄 {{ item.source_label }}</span>
        {% if item.created %}<span class="badge">🗓 {{ item.created }}</span>{% endif %}
      </div>
      <div class="meta">
        <span>🧱 {{ item.chunk_count }} 块</span>
        <span>🔤 {{ item.words }} 字</span>
        {% if item.total_tokens > 0 %}
        <span>💰 ¥{{ "%.4f"|format(item.cost_cny) }}</span>
        {% endif %}
      </div>
    </a>
    {% endfor %}
  {% else %}
    <div class="empty">
      <p>还没有生成任何背诵材料</p>
      <p style="margin-top:8px;"><a href="/" style="color:#0e7c6b;">去生成第一个 →</a></p>
    </div>
  {% endif %}

  <div class="footer">背诵宝</div>
</div>
<script>
if ('serviceWorker' in navigator) { window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js').catch(function () {}); }); }
</script>
</body>
</html>"""


# ── 输入源处理 ────────────────────────────────────


def _from_text(text: str, title: str) -> tuple:
    """粘贴文本 → 按文章解析。"""
    parsed = parse_article(text)
    material_id = "text_" + hashlib.md5(text[:200].encode()).hexdigest()[:8]
    return parsed, material_id, "article", title or "粘贴文本"


def _from_url(url: str, title: str) -> tuple:
    """网页链接 → 抓取正文。"""
    text = fetch_web_article(url)
    parsed = parse_article(text)
    material_id = "url_" + hashlib.md5(url.encode()).hexdigest()[:8]
    return parsed, material_id, "article", title or domain_of(url)


def _from_upload(uploaded, title: str) -> tuple:
    """上传文件 → .srt 按字幕、其余按文章解析。"""
    suffix = Path(uploaded.filename).suffix.lower()
    supported = (".srt", ".txt", ".md", ".rtf", ".docx", ".pdf")
    if suffix not in supported:
        raise ValueError(
            f"不支持的文件格式: {suffix}。"
            "请上传 .srt / .txt / .md / .rtf / .docx / .pdf 文件。"
        )

    tmp_dir = Path(tempfile.gettempdir()) / "article_recite"
    tmp_dir.mkdir(exist_ok=True)
    file_path = tmp_dir / uploaded.filename
    uploaded.save(str(file_path))

    parsed = parse_file(file_path)
    stem = Path(uploaded.filename).stem
    safe_id = _slug(stem) or "upload"
    source_type = "subtitle" if suffix == ".srt" else "article"
    return parsed, safe_id, source_type, title or uploaded.filename


# ── 辅助 ────────────────────────────────────


def _slug(text: str) -> str:
    """把文件名/标题转成安全的目录名片段。"""
    s = re.sub(r"[^\w一-鿿-]+", "_", text).strip("_")
    return s[:60]


def _load_api_key() -> str:
    """加载 API Key：环境变量 或 .env 文件。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
