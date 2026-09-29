# -*- coding: utf-8 -*-
"""可行性验证基线：抽取式摘要 + 规则评分 + 积分引擎。

这不是最终模型——它验证的是 PART2 的流水线骨架（§5 上下文、§9 结构、
§9.2 积分规则、§8 质量门禁），并给将来接入 LLM 后提供对比基线。
摘要/评分模型位置已按 §12.3 Protocol 思路留接口，LLM 到位后替换实现即可。
"""
import json
import re
from dataclasses import dataclass, field

import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .preprocess import preprocess_message

SUMMARY_MODEL_VERSION = "baseline-extractive-1.0"
SCORE_MODEL_VERSION = "baseline-rules-1.0"

# ---- §5.2 线程上下文 ----


@dataclass
class Message:
    row: dict
    artifact: dict = field(default_factory=dict)

    @property
    def message_key(self):
        return self.row["MessageKey"]

    @property
    def thread_id(self):
        return self.row["ThreadId"]

    @property
    def text(self):
        return self.artifact.get("normalized_text", self.row.get("ContentText", ""))


@dataclass
class ThreadContext:
    """§5.2：target + thread_starter + parent + context，带角色标注。"""

    target: Message
    starter: Message | None = None
    parent: Message | None = None
    context: list[Message] = field(default_factory=list)

    def render(self, limit=4000):
        """拼装带角色标注的上下文（送模型版本；作者一律用角色名，§6.2）。"""
        parts = [f"[target_message]\n{self.target.text}"]
        if self.parent is not None:
            parts.append(f"[parent_message]\n{self.parent.text}")
        if self.starter is not None and self.starter.message_key != self.target.message_key:
            parts.append(f"[thread_starter]\n{self.starter.text}")
        for i, m in enumerate(self.context, 1):
            if m.message_key != self.target.message_key:
                parts.append(f"[context_message {i}]\n{m.text}")
        return "\n\n".join(parts)[:limit]


def build_contexts(messages: list[Message]) -> dict[str, ThreadContext]:
    by_id = {(m.row.get("NetworkId", ""), m.row["MessageId"]): m for m in messages}
    by_thread: dict[str, list[Message]] = {}
    for m in messages:
        by_thread.setdefault((m.row.get("NetworkId", ""), m.thread_id), []).append(m)

    ctxs = {}
    for m in messages:
        thread = by_thread[(m.row.get("NetworkId", ""), m.thread_id)]
        starter = next((x for x in thread if x.row["IsRootPost"] == "True"), thread[0])
        parent = by_id.get((m.row.get("NetworkId", ""), m.row["ReplyToId"])) if m.row.get("ReplyToId") else None
        if parent is None and starter is not None and starter.message_key != m.message_key:
            parent = starter
        others = [x for x in thread if x.message_key != m.message_key and
                  x is not starter and x is not parent]
        ctxs[m.message_key] = ThreadContext(target=m, starter=starter, parent=parent,
                                            context=others[:3])
    return ctxs


# ---- §7 摘要基线：TF-IDF 抽取式 ----

SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?\.])\s*\n?|\n+")
QUESTION_HINT_RE = re.compile(r"[?？]|怎么|如何|怎么办|求助|请教|有没有|吗\b|能不能|可不可以用")
ANSWER_HINT_RE = re.compile(r"建议|可以试|试试|这样做|方法|步骤|解决|原因是|应该|参考")
PRACTICE_HINT_RE = re.compile(r"我们|实践|落地|项目|测试结果|效果|踩坑|复盘|总结|搭建|部署")


def _sentences(text: str) -> list[str]:
    sents = [s.strip() for s in SENT_SPLIT_RE.split(text) if s and s.strip()]
    return sents or ([text] if text else [])


def _tokenize(text: str) -> list[str]:
    return [t for t in jieba.lcut(text) if t.strip()]


def summarize(message: Message, ctx: ThreadContext) -> dict:
    """抽取式摘要：TF-IDF 句子加权（位置加权），取 top 句作 key_points/证据。

    输出结构对齐 §7.1（intent/key_points/evidence_spans/uncertainties）。
    """
    sents = _sentences(message.text)
    warnings = list(message.artifact["warnings"])

    if not sents or not message.text.strip():
        return {
            "message_key": message.message_key,
            "summary": "",
            "intent": "social",
            "key_points": [],
            "actionable_advice": [],
            "evidence_spans": [],
            "uncertainties": ["EMPTY_CONTENT"],
            "language": message.artifact["language"],
            "summary_quality": "review",
            "model_version": SUMMARY_MODEL_VERSION,
            "prompt_version": "baseline-extractive-1.0",
        }

    if len(sents) == 1:
        ranked = [(0.0, sents[0])]
    else:
        # 上下文并入语料，使摘要偏向"相对线程主题重要"的句子（§5.2）
        corpus = sents + [ctx.render(limit=1500)]
        vec = TfidfVectorizer(tokenizer=_tokenize, token_pattern=None)
        matrix = vec.fit_transform(corpus)
        sim = cosine_similarity(matrix[:-1], matrix[-1]).ravel()
        pos_boost = [0.15 if i == 0 else 0.0 for i in range(len(sents))]  # 首句常为主题句
        ranked = sorted(zip((sim + pos_boost).tolist(), sents), key=lambda x: -x[0])

    top = [s for _, s in ranked[: min(3, len(ranked))]]
    # Preserve qualifications independently of the three selected topic sentences.
    limitation_spans = [s for s in sents if re.search(
        r'尚未|暂不能|不能|不足|不一定|未验证|没有效果|虚构|模拟|not yet|not evidence', s, re.I)]
    if not message.row.get("IsRootPost") == "True" and ctx.parent is not None:
        # 回复：摘要里注明所回应的主题，避免脱离上下文误读
        parent_topic = (_sentences(ctx.parent.text) or [""])[0][:60]
        summary = f"回复「{parent_topic}…」：{top[0]}"
    else:
        summary = top[0]

    stats = message.artifact["text_stats"]
    intent = classify_intent(message, stats)

    return {
        "message_key": message.message_key,
        "summary": summary[:200],
        "intent": intent,
        "key_points": [s[:100] for s in top],
        "limitations": limitation_spans,
        "actionable_advice": [s[:100] for s in top if ANSWER_HINT_RE.search(s)][:2],
        "evidence_spans": [{"quote": s[:80], "reason": "TF-IDF 主题句"} for s in top],
        "uncertainties": warnings or [],
        "language": message.artifact["language"],
        "summary_quality": "pass" if len(top) >= 1 and not warnings else "review",
        "model_version": SUMMARY_MODEL_VERSION,
        "prompt_version": "baseline-extractive-1.0",
    }


def classify_intent(message: Message, stats: dict) -> str:
    text = message.text
    if QUESTION_HINT_RE.search(text[:300]):
        return "question"
    if message.row.get("IsRootPost") != "True":
        return "answer" if (ANSWER_HINT_RE.search(text) or stats["code_blocks"]) else "social"
    if stats["urls"] >= 2 or text.count("[URL]") >= 2:
        return "resource"
    if PRACTICE_HINT_RE.search(text) or stats["code_blocks"]:
        return "practice_share"
    if stats["characters"] < 30:
        return "social"
    return "practice_share"


# ---- §9 评分基线：规则 ----


def score(message: Message, summary: dict, ctx: ThreadContext) -> dict:
    """规则评分：四维度 0-3 级，每级给规则命中证据。基线可解释但粗糙。"""
    stats = message.artifact["text_stats"]
    text = message.text
    ev = summary["evidence_spans"]
    evidence = [e["quote"] for e in ev] or [text[:60]]

    def lvl(cond, evidence_desc):
        return {"level": cond, "evidence": evidence, "reason": evidence_desc}

    # 针对性：回复与父帖的主题重合度；主帖默认"发起新话题"
    if ctx.parent is not None and message.row.get("IsRootPost") != "True":
        overlap = keyword_overlap(text, ctx.parent.text)
        relevance = (
            lvl(3, f"与父帖关键词重合 {overlap:.0%}") if overlap >= 0.25
            else lvl(2, f"处于同一讨论串（重合 {overlap:.0%}）")
        )
    else:
        relevance = lvl(2, "主帖：发起新话题")

    # 贡献价值：信息量分层（长度只作诊断之一，不作直接奖励，§10）
    chars = stats["characters"]
    if chars >= 500 or stats["code_blocks"] >= 1:
        value = lvl(3, f"正文 {chars} 字、{stats['code_blocks']} 个代码块，含可复用内容")
    elif chars >= 100:
        value = lvl(2, f"正文 {chars} 字，有实质信息")
    elif chars >= 30:
        value = lvl(1, f"正文仅 {chars} 字")
    else:
        value = lvl(0, "正文过短，无实质内容")

    # 证据与具体性：数字、步骤词、URL、代码
    specifics = sum([
        bool(re.search(r"\d+(\.\d+)?%?", text)),
        bool(re.search(r"步骤|第一|其次|然后|结果|v\d+\.\d+|版本", text)),
        stats["urls"] > 0,
        stats["code_blocks"] > 0,
    ])
    evidence_dim = lvl(
        min(3, specifics), f"具体性信号 {specifics}/4（数字/步骤/链接/代码）"
    )

    # 推进讨论：答疑或引发回复（POC 无点赞/后续回复数据，退化为启发式）
    if summary["intent"] == "answer" and summary["actionable_advice"]:
        impact = lvl(3, "给出可执行建议的直接回复")
    elif summary["intent"] in ("question", "practice_share", "resource") and chars >= 100:
        impact = lvl(2, "发起了有信息量的讨论内容")
    else:
        impact = lvl(1, "一般互动")

    dims = {"relevance": relevance, "value": value, "evidence": evidence_dim,
            "discussion_impact": impact}
    needs_review = summary["summary_quality"] == "review"
    review_reason = "摘要质量检查未通过" if needs_review else None
    return {
        "message_key": message.message_key,
        "contribution_type": summary["intent"],
        "dimensions": dims,
        "quality_flags": summary["uncertainties"],
        "needs_human_review": needs_review,
        "review_reason": review_reason,
        "score_model_version": SCORE_MODEL_VERSION,
        "prompt_version": "baseline-rules-1.0",
    }


def keyword_overlap(a: str, b: str) -> float:
    ta, tb = set(_tokenize(a)), set(_tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


# ---- §9.2 积分引擎（最终积分只由版本化规则计算） ----

BASE_POINTS = {"question": 2, "answer": 3, "practice_share": 5, "resource": 4,
               "retrospective": 5, "social": 1}
DIMENSION_NAMES = ["relevance", "value", "evidence", "discussion_impact"]
PER_ITEM_CAP = 10
RULES_VERSION = "scoring-rules-0.1"


def calculate_points(evaluation: dict, sender_hash_counts: dict) -> dict:
    dimension_total = sum(evaluation["dimensions"][n]["level"] for n in DIMENSION_NAMES)
    points = BASE_POINTS[evaluation["contribution_type"]]
    points += dimension_total  # 0-12 → 每级 1 分加成
    dup_key = (evaluation["_sender_id"], evaluation["_content_hash"])
    duplicate = sender_hash_counts.get(dup_key, 0) > 1
    if duplicate:
        points = 0
    points = min(max(points, 0), PER_ITEM_CAP)
    return {
        "message_key": evaluation["message_key"],
        "sender_id": evaluation["_sender_id"],
        "contribution_type": evaluation["contribution_type"],
        "dimension_total": dimension_total,
        "raw_points": points,
        "points": points,
        "duplicate_flag": duplicate,
        "rules_version": RULES_VERSION,
        "per_item_cap": PER_ITEM_CAP,
    }


# ---- §8 质量门禁 ----


def quality_gate(message: Message, summary: dict, evaluation: dict) -> list[str]:
    """结构化校验：JSON 可序列化、message_key 一致、证据可回指原文（§8）。"""
    failures = []
    for payload in (summary, evaluation):
        try:
            json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            failures.append(f"JSON_SERIALIZE:{e}")
    if summary.get("message_key") != message.message_key:
        failures.append("MESSAGE_KEY_MISMATCH:summary")
    if evaluation.get("message_key") != message.message_key:
        failures.append("MESSAGE_KEY_MISMATCH:evaluation")
    normalized = message.artifact["normalized_text"]
    for span in summary.get("evidence_spans", []):
        quote = span.get("quote", "").replace("…", "")
        if quote and quote not in normalized:
            failures.append(f"EVIDENCE_NOT_FOUND:{quote[:30]}")
    for quote in summary.get('limitations', []):
        if quote not in normalized:
            failures.append('LIMITATION_NOT_FOUND')
    for dimension in DIMENSION_NAMES:
        value = evaluation.get('dimensions', {}).get(dimension, {}).get('level')
        if type(value) is not int or not 0 <= value <= 3:
            failures.append('INVALID_DIMENSION:' + dimension)
    return failures


def run_pipeline(rows: list[dict], evaluate=None, review_hold=False) -> list[dict]:
    """端到端：预处理 → 上下文 → 摘要 → 评分 → 积分 → 质量门禁。

    evaluate(message, summary, ctx) 是评分后端的可替换接口（规则/ML/LLM 同签名）。
    """
    messages = []
    if len({r['MessageKey'] for r in rows}) != len(rows):
        raise ValueError('Duplicate MessageKey in input; reconcile snapshots before scoring')
    for row in rows:
        art = preprocess_message(row["MessageKey"], row.get("ContentText", ""),
                                 row.get("LanguageCode") or None)
        messages.append(Message(row=row, artifact=art))
    ctxs = build_contexts(messages)

    hash_counts: dict[str, int] = {}
    for m in messages:
        key = (m.row["SenderId"], m.artifact["content_hash"])
        hash_counts[key] = hash_counts.get(key, 0) + 1

    evaluate = evaluate or score
    results = []
    for m in messages:
        ctx = ctxs[m.message_key]
        summary = summarize(m, ctx)
        evaluation = evaluate(m, summary, ctx)
        evaluation["_content_hash"] = m.artifact["content_hash"]
        evaluation["_sender_id"] = m.row["SenderId"]
        gate = quality_gate(m, summary, evaluation)
        points = calculate_points(evaluation, hash_counts)
        if evaluation.get('score_model_version') == 'quantile-scorecard-0.2-alpha':
            # Equal dimension weights; no type bonus to prevent systematic cap saturation.
            candidate = int(points['dimension_total'] * 10 / 12 + .5)
            points['raw_points'] = candidate
            points['points'] = 0 if points['duplicate_flag'] else candidate
            points['rules_version'] = 'scoring-rules-0.2-alpha'
        points['candidate_points'] = points['points']
        points['scoring_status'] = 'Draft'
        if review_hold and evaluation.get('needs_human_review'):
            points['points'] = 0
            points['scoring_status'] = 'PendingReview'
        if gate:
            points["points"] = 0
            points["gate_failures"] = gate
            points['scoring_status'] = 'PendingReview'
        results.append({
            "message_key": m.message_key,
            "sender": m.row["SenderName"],
            "is_root": m.row["IsRootPost"] == "True",
            "posted_at": m.row["PostedAt"],
            "data_origin": m.row.get('DataOrigin', 'unspecified'),
            "is_synthetic": m.row.get('IsSynthetic', 'unknown'),
            "preprocess": m.artifact,
            "summary": summary,
            "evaluation": evaluation,
            "points": points,
        })
    return results
