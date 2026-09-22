# -*- coding: utf-8 -*-
"""PART2 §6 预处理基线实现。

只生成派生字段，不修改原始 ContentText。输出结构对应 PART2 §6.3。
"""
import hashlib
import re
import unicodedata

PREPROCESS_VERSION = "preprocess-1.0"

CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
URL_RE = re.compile(r"https?://\S+|www\.\S+")
MENTION_RE = re.compile(r"@[\w.\-]+")
HASHTAG_RE = re.compile(r"#[^\s#]+")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|#39|nbsp);")
ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "#39": "'", "nbsp": " "}
# 段内连续空白压成一个空格；保留 \n 作为段落边界
INLINE_SPACE_RE = re.compile(r"[^\S\n]+")


def normalize(text: str) -> str:
    """§6.1 步骤 2-5：Unicode NFC、统一换行、清控制字符、还原残留 HTML 实体。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = CONTROL_RE.sub("", text)
    text = ENTITY_RE.sub(lambda m: ENTITIES[m.group(1)], text)
    return INLINE_SPACE_RE.sub(" ", text).strip()


def to_placeholders(text: str) -> tuple[str, dict]:
    """§6.1 步骤 6：URL/@mention/hashtag/代码块替换为有类型占位标记。

    返回 (带占位符文本, 计数)。原始正文里占位符只影响送模型版本，证据校验用占位前文本。
    """
    counts = {"urls": 0, "mentions": 0, "hashtags": 0, "code_blocks": 0}
    text = CODE_FENCE_RE.sub(
        lambda m: (counts.__setitem__("code_blocks", counts["code_blocks"] + 1) or "[CODE_BLOCK]"),
        text,
    )
    text = URL_RE.sub(
        lambda m: (counts.__setitem__("urls", counts["urls"] + 1) or "[URL]"), text
    )
    text = MENTION_RE.sub(
        lambda m: (counts.__setitem__("mentions", counts["mentions"] + 1) or "[MENTION]"),
        text,
    )
    text = HASHTAG_RE.sub(
        lambda m: (counts.__setitem__("hashtags", counts["hashtags"] + 1) or "[HASHTAG]"),
        text,
    )
    return text, counts


def detect_language(text: str, hint: str | None = None) -> tuple[str, list[str]]:
    """§6.1 步骤 7：粗粒度语言检测（CJK 占比），与上游 LanguageCode 冲突时给警告。"""
    warnings = []
    if not text:
        return (hint or "unknown"), warnings + ["EMPTY_CONTENT"]
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    detected = "zh-Hans" if cjk > latin else "en"
    if hint and hint != detected and min(cjk, latin) > 10:
        # 双语内容比例接近时不视为冲突，只在明显不一致时警告
        if (cjk > latin * 3) != (hint == "zh-Hans"):
            warnings.append(f"LANGUAGE_CONFLICT detected={detected} hint={hint}")
    return detected, warnings


def text_stats(text: str, placeholder_counts: dict) -> dict:
    """§6.1 步骤 8：诊断特征。长度是诊断信息，不是评分依据（§10）。"""
    paragraphs = [p for p in text.split("\n") if p.strip()]
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    words = len(re.findall(r"[A-Za-z0-9]+", text)) + cjk  # 拉丁词数 + 汉字数
    return {
        "characters": len(text),
        "words": words,
        "paragraphs": len(paragraphs),
        "urls": placeholder_counts["urls"],
        "mentions": placeholder_counts["mentions"],
        "hashtags": placeholder_counts["hashtags"],
        "code_blocks": placeholder_counts["code_blocks"],
    }


def content_hash(text: str) -> str:
    """§6.1 步骤 9：幂等与变更检测。"""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def preprocess_message(message_key: str, content_text: str, hint_lang: str | None) -> dict:
    normalized = normalize(content_text)
    with_placeholders, counts = to_placeholders(normalized)
    lang, lang_warnings = detect_language(normalized, hint_lang)
    return {
        "message_key": message_key,
        "content_hash": content_hash(normalized),
        "normalized_text": normalized,
        "model_input_text": with_placeholders,
        "language": lang,
        "text_stats": text_stats(normalized, counts),
        "redaction": {"applied": False, "items": []},
        "warnings": lang_warnings,
        "preprocess_version": PREPROCESS_VERSION,
    }
