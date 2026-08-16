"""内容抓取模块 —— 网页文章正文提取（博客 / 演讲稿页面）。

使用 trafilatura 提取正文，requests 控制请求头以提高成功率。
"""

import re
from urllib.parse import urlparse

import requests


def fetch_web_article(url: str) -> str:
    """抓取网页文章正文，返回纯文本（保留段落）。

    Args:
        url: 网页文章链接。

    Returns:
        提取到的正文纯文本（段落间以空行分隔）。

    Raises:
        ValueError: 无法访问或无法提取有效正文时。
        RuntimeError: 缺少 trafilatura 依赖时。
    """
    try:
        import trafilatura
    except ImportError:
        raise RuntimeError(
            "缺少 trafilatura 依赖，无法抓取网页文章。\n"
            "请先执行: pip install trafilatura"
        )

    try:
        resp = requests.get(url, timeout=20, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
        })
        resp.raise_for_status()
        downloaded = resp.text
    except Exception as e:
        raise ValueError(f"无法访问网页: {url}\n原因: {e}")

    if not downloaded:
        raise ValueError(
            f"无法抓取网页内容: {url}\n"
            "请确认链接可访问、是文章页面，或改用「粘贴文本」输入。"
        )

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not text or len(text.strip()) < 30:
        raise ValueError(
            f"未能从该网页提取到有效正文: {url}\n"
            "该页面可能没有正文，请改用「粘贴文本」输入。"
        )

    # 规范段落：确保段落间用空行分隔
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n\n".join(ln for ln in lines if ln)


def domain_of(url: str) -> str:
    """粗略提取 URL 的域名作为来源名。"""
    try:
        return (urlparse(url).netloc or "网页文章").removeprefix("www.")
    except Exception:
        return "网页文章"
