"""共享工具函数"""
import os, re, time


# ── 日志 ─────────────────────────────────────────────────────────
_log_path = os.path.join(os.path.dirname(__file__), "widget.log")
_log_file = open(_log_path, "a", encoding="utf-8")


def _flog(prefix, msg):
    ts = time.strftime("%H:%M:%S")
    ms = int(time.time() * 1000) % 1000
    line = f"{ts}.{ms:03d} {prefix} {msg}"
    _log_file.write(line + "\n")
    _log_file.flush()


# ── Markdown 清理 ────────────────────────────────────────────────
def _strip_md(text):
    """去掉 markdown 格式符号，保留纯文本内容供 TTS 朗读"""
    if not text:
        return text
    s = text
    s = re.sub(r'```[\s\S]*?```', '', s)
    s = re.sub(r'`([^`]*)`', r'\1', s)
    s = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)
    s = re.sub(r'^#{1,6}\s+', '', s, flags=re.MULTILINE)
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'__(.+?)__', r'\1', s)
    s = re.sub(r'\*(.+?)\*', r'\1', s)
    s = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', s)
    s = re.sub(r'~~(.+?)~~', r'\1', s)
    s = re.sub(r'^>\s?', '', s, flags=re.MULTILINE)
    s = re.sub(r'^[\s]*[-*+]\s+', '', s, flags=re.MULTILINE)
    s = re.sub(r'^[\s]*\d+\.\s+', '', s, flags=re.MULTILINE)
    s = re.sub(r'^[-*_]{3,}\s*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'\|[\s\-:]+\|', '', s)
    s = re.sub(r'\|', ' ', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    s = re.sub(r'[，。！？；：、""''【】（）《》\-—…·「」『』〈〉〔〕｛｝‖｜\n]', ' ', s)
    s = re.sub(r'[,.!?;:\'"()\[\]{}<>/\\@#$%^&*+=_~`|]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s
