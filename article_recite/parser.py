"""文本解析与清洗模块。

支持：
  - 纯文本/网页文章/演讲稿解析（保留段落结构）
  - SRT 字幕解析（合并为段落）
  - 中英文语言检测
  - 字数统计
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedMaterial:
    """解析后的背诵材料文本。"""

    paragraphs: list[str] = field(default_factory=list)
    full_text: str = ""  # 段落以 \n\n 连接，供 AI 分块

    @property
    def word_count(self) -> int:
        return count_words(self.full_text)


# ── 非语言内容的清理模式 ──────────────────────────────

CLEANUP_PATTERNS: list[tuple[str, str]] = [
    # HTML 标签
    (r"<[^>]+>", ""),
    # 音乐/掌声/笑声标记
    (r"♪+.*?♪+", ""),
    (r"\[Music\]|\[music\]|\(music\)", ""),
    (r"\(upbeat music\)|\(instrumental\)", ""),
    (r"\[Applause\]|\[applause\]|\(applause\)", ""),
    (r"\[Laughter\]|\[laughter\]|\(laughter\)", ""),
    (r"\(crowd cheering\)", ""),
    # 听不清/停顿
    (r"\[inaudible\]", ""),
    (r"\(silence\)|\(pause\)", ""),
    # 字幕噪声
    (r"\[ ?__ ?\]|\[__\]", ""),
    # 多余空白
    (r"\n{3,}", "\n\n"),
    (r" {2,}", " "),
]


def clean_text(text: str) -> str:
    """清洗非语言噪声与多余空白。"""
    for pattern, replacement in CLEANUP_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text.strip()


# ── 字数统计与语言检测 ──────────────────────────────

_CJK_RANGES = [
    (0x4E00, 0x9FFF),  # CJK 统一表意文字
    (0x3400, 0x4DBF),  # 扩展 A
    (0xF900, 0xFAFF),  # 兼容表意文字
    (0x3000, 0x303F),  # CJK 标点
]


def count_words(text: str) -> int:
    """统计字数：中文按字计数，英文按空格分词。"""
    cjk_count = 0
    latin_tokens = 0
    token: list[str] = []
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _CJK_RANGES):
            cjk_count += 1
        elif ch.isalnum():
            token.append(ch)
        else:
            if token:
                latin_tokens += 1
                token = []
    if token:
        latin_tokens += 1
    return cjk_count + latin_tokens


def detect_language(text: str) -> str:
    """粗略判断材料语言: "zh" | "en"。

    按 CJK 字符在有效字符（CJK + 拉丁字母）中的占比判断，
    占比 > 0.3 判定为中文材料，否则为英文材料。
    """
    cjk = 0
    latin = 0
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _CJK_RANGES):
            cjk += 1
        elif ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
            latin += 1
    total = cjk + latin
    if total == 0:
        return "en"
    return "zh" if (cjk / total) > 0.3 else "en"


# ── 文本解析 ──────────────────────────────────────


def parse_article(text: str) -> ParsedMaterial:
    """从纯文本解析文章/演讲稿，保留段落结构。"""
    text = clean_text(text)
    if not text:
        return ParsedMaterial()

    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [re.sub(r"\s*\n\s*", " ", p).strip() for p in paragraphs]
    paragraphs = [p for p in paragraphs if p]

    if not paragraphs:
        return ParsedMaterial()

    return ParsedMaterial(
        paragraphs=paragraphs,
        full_text="\n\n".join(paragraphs),
    )


def parse_srt(srt_path: Path) -> ParsedMaterial:
    """解析 SRT 字幕文件，按时间合并后组成段落文本。"""
    raw = srt_path.read_text(encoding="utf-8")

    # SRT 块由空行分隔
    blocks = re.split(r"\n\s*\n", raw.strip())
    time_re = re.compile(
        r"\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->\s*"
        r"\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}"
    )

    lines: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = time_re.search(block)
        if not m:
            continue
        text = block[m.end():].strip()
        text = " ".join(text.splitlines())
        if text:
            lines.append(text)

    # 字幕按顺序合并成段落（每 6 条左右一段，避免过碎）
    paragraphs = ["\n".join(lines[i:i + 6]) for i in range(0, len(lines), 6)]
    paragraphs = [clean_text(p) for p in paragraphs if clean_text(p)]

    return ParsedMaterial(
        paragraphs=paragraphs,
        full_text="\n\n".join(paragraphs),
    )


def parse_file(file_path: Path) -> ParsedMaterial:
    """自动检测文件格式并解析。

    Args:
        file_path: .srt / .txt / .md / .rtf / .docx / .pdf 文件路径。

    Raises:
        ValueError: 文件中没有可解析的文本时。
        RuntimeError: 缺少解析 .docx/.pdf 所需的依赖时。
    """
    suffix = file_path.suffix.lower()

    if suffix == ".srt":
        return parse_srt(file_path)
    elif suffix == ".docx":
        text = parse_docx(file_path)
    elif suffix == ".pdf":
        text = parse_pdf(file_path)
    elif suffix == ".rtf":
        text = _strip_rtf(_read_text(file_path))
    else:  # .txt / .md 等纯文本
        text = _read_text(file_path)

    if not text or not text.strip():
        raise ValueError(f"文件 {file_path.name} 中没有可解析的文本内容。")
    return parse_article(text)


def _read_text(path: Path) -> str:
    """读取文本文件，自动尝试 UTF-8，失败则回退到 GBK。"""
    for enc in ("utf-8", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def parse_docx(path: Path) -> str:
    """用 python-docx 提取 Word 文档的段落文本。"""
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError(
            "缺少 python-docx 依赖，无法解析 .docx。\n"
            "请先执行: pip install python-docx"
        )

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def parse_pdf(path: Path) -> str:
    """用 pypdf 提取 PDF 文档的文本（按页，页间以空行分隔）。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(
            "缺少 pypdf 依赖，无法解析 .pdf。\n"
            "请先执行: pip install pypdf"
        )

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _strip_rtf(text: str) -> str:
    """简易 RTF → 纯文本。"""
    text = re.sub(r"\\(?:par|line|sect|tab)\b", "\n", text)
    text = re.sub(r"\\(?:'[0-9a-fA-F]{2}|[a-zA-Z]+(?:-?\d+)?)", "", text)
    text = text.replace("{", "").replace("}", "")
    return text
