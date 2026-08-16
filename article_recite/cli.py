"""背诵宝 CLI —— 从文章、演讲稿、字幕生成背诵材料包。

用法:
    # 从网页文章 URL
    python -m article_recite "https://example.com/blog/post"

    # 从本地文件（.srt / .txt / .md / .docx / .pdf）
    python -m article_recite --file subtitles.srt -t "演讲稿标题"

    # 从 stdin 粘贴文本
    cat article.txt | python -m article_recite -t "文章标题"
"""

import hashlib
import os
import sys
from datetime import date
from pathlib import Path

import click

from . import __version__
from .analyzer import analyze, save_material
from .downloader import fetch_web_article, domain_of
from .outputs.recite_book import generate as generate_recite_book
from .parser import parse_article, parse_file, detect_language
from .planner import build_schedule

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _echo_ok(t): click.secho(t, fg="green")
def _echo_step(t): click.secho(t, fg="cyan", bold=True)
def _echo_err(t): click.secho(t, fg="red")
def _echo_warn(t): click.secho(t, fg="yellow")


@click.command(name="article-recite", help="从文章/演讲稿/字幕生成背诵材料包。")
@click.argument("url", required=False, default=None)
@click.option("--file", "-f", type=click.Path(exists=True, path_type=Path), default=None,
              help="本地文件路径（.srt/.txt/.md/.docx/.pdf）")
@click.option("--title", "-t", default=None, help="材料标题")
@click.option("--language", "-l", type=click.Choice(["zh", "en", "auto"]), default="auto",
              help="材料语言（默认 auto 自动检测）")
@click.option("--model", "-m", default="deepseek-chat", help="模型名称")
@click.option("--api-key", default=None, help="DeepSeek API Key（默认读 .env / 环境变量）")
@click.option("--output-dir", "-d", default=str(DEFAULT_OUTPUT_DIR), help=f"输出根目录 (默认: {DEFAULT_OUTPUT_DIR})")
@click.version_option(version=__version__)
def main(url, file, title, language, model, api_key, output_dir):
    """主入口。"""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    api_key = _load_api_key(api_key)
    out_dir = Path(output_dir)

    # Step 1: 获取材料
    if file is not None:
        _echo_step("[1/3] 读取本地文件...")
        parsed = parse_file(file)
        material_id = _safe_id(file.stem)
        source_type = "subtitle" if file.suffix.lower() == ".srt" else "article"
        fallback_title = title or file.stem
    elif url is not None:
        _echo_step("[1/3] 抓取网页文章...")
        text = fetch_web_article(url)
        parsed = parse_article(text)
        material_id = "url_" + hashlib.md5(url.encode()).hexdigest()[:8]
        source_type = "article"
        fallback_title = title or domain_of(url)
    else:
        _echo_step("[1/3] 从 stdin 读取...")
        text = sys.stdin.read()
        if not text.strip():
            _echo_err("没有从 stdin 收到输入。")
            sys.exit(1)
        parsed = parse_article(text)
        material_id = "stdin_" + hashlib.md5(text[:200].encode()).hexdigest()[:8]
        source_type = "article"
        fallback_title = title or "粘贴文本"

    lang = language if language != "auto" else detect_language(parsed.full_text)
    click.echo(f"   语言: {'中文' if lang == 'zh' else 'English'}  ·  来源: {source_type}  ·  字数: {parsed.word_count}")

    if parsed.word_count < 20:
        _echo_warn("内容过短，分块可能不理想。")

    # Step 2: AI 意群分块
    _echo_step("[2/3] AI 意群分块 (DeepSeek API)...")
    result = analyze(
        full_text=parsed.full_text,
        title=fallback_title,
        language=lang,
        source_type=source_type,
        api_key=api_key,
        model=model,
    )
    material = result.material
    click.echo(f"   分块完成: {len(material.chunks)} 块")
    if result.usage and result.usage.total_tokens > 0:
        click.echo(f"   API 费用: ¥{result.usage.cost_cny:.4f} ({result.usage.total_tokens} tokens)")

    if not material.chunks:
        _echo_err("未能切分出有效意群块。")
        sys.exit(1)

    # Step 3: 计划 + 输出
    _echo_step("[3/3] 生成背诵看板...")
    schedule = build_schedule(len(material.chunks))
    final_title = title or material.title_suggested or fallback_title
    meta = {
        "material_id": material_id,
        "title": final_title,
        "language": lang,
        "source_type": source_type,
        "truncated": result.truncated,
        "created": date.today().isoformat(),
    }
    out_dir = out_dir / material_id
    out_dir.mkdir(parents=True, exist_ok=True)
    save_material(material, meta, result.usage, out_dir / "material.json")
    recite_path = generate_recite_book(material, meta, parsed, schedule, result.usage, out_dir / "recite.html")

    click.echo()
    _echo_ok(f"  [OK] 背诵看板: {recite_path}")
    _echo_ok(f"计划: {schedule.total_days} 天 · 每天 {schedule.chunks_per_day} 块 · 间隔 {','.join(map(str, schedule.intervals))} 天")


def _safe_id(name: str) -> str:
    import re
    s = re.sub(r"[^\w一-鿿-]+", "_", name).strip("_")
    return s[:60] or "material"


def _load_api_key(explicit_key: str | None) -> str | None:
    if explicit_key:
        return explicit_key
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


if __name__ == "__main__":
    main()
