# -*- coding: utf-8 -*-
"""ML 推理后端：与规则后端同签名（evaluate(message, summary, ctx)）。

模拟 PART2 §12.3 的可替换模型接口——将来 LLM 到位后写一个
LlmBackend.evaluate 同样替换即可，流水线其余部分不动。
"""
from pathlib import Path

import joblib
import numpy as np

from .baseline import DIMENSION_NAMES, Message, ThreadContext
from .features import NUMERIC_NAMES, FeatureSpace, numeric_features

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "poc_output" / "models" / "model-sklearn-v0.1.joblib"
LOW_CONFIDENCE = 0.45


class SklearnBackend:
    def __init__(self, bundle: dict):
        self.bundle = bundle
        fs = bundle["feature_space"]
        self.feature_space = FeatureSpace.__new__(FeatureSpace)
        self.feature_space.vectorizer = fs["vectorizer"]
        self.feature_space.scaler = fs["scaler"]
        self.clf = bundle["type_classifier"]
        self.ridges = bundle["dimension_ridges"]

    @classmethod
    def load(cls, path: Path | None = None) -> "SklearnBackend":
        return cls(joblib.load(path or DEFAULT_MODEL))

    def evaluate(self, message: Message, summary, ctx: ThreadContext) -> dict:
        X = self.feature_space.transform([message])
        proba = self.clf.predict_proba(X)[0]
        best = int(np.argmax(proba))
        contribution_type = self.clf.classes_[best]
        confidence = float(proba[best])

        stats = dict(zip(NUMERIC_NAMES, numeric_features(message)))
        dims = {}
        for d in DIMENSION_NAMES:
            raw = float(self.ridges[d].predict(X)[0])
            level = int(np.clip(round(raw), 0, 3))
            highlights = ", ".join(
                f"{k}={stats[k]:g}" for k in
                ("characters", "paragraphs", "urls", "code_blocks", "is_reply",
                 "has_question_hint", "has_practice_hint") if stats[k]
            ) or "无明显特征"
            dims[d] = {
                "level": level,
                "evidence": summary["evidence_spans"][:1],
                "reason": f"Ridge 预测 {raw:.1f}→L{level}；特征: {highlights}",
            }

        low_conf = confidence < LOW_CONFIDENCE
        needs_review = bool(summary["summary_quality"] == "review") or low_conf
        reasons = []
        if low_conf:
            reasons.append(f"MODEL_LOW_CONFIDENCE p={confidence:.2f}")
        if summary["summary_quality"] == "review":
            reasons.append("摘要质量检查未通过")
        return {
            "message_key": message.message_key,
            "contribution_type": contribution_type,
            "type_confidence": round(confidence, 3),
            "dimensions": dims,
            "quality_flags": summary["uncertainties"],
            "needs_human_review": needs_review,
            "review_reason": "; ".join(reasons) or None,
            "score_model_version": self.bundle["model_version"],
            "prompt_version": f"weaklabels:{self.bundle['weak_label_source']}",
        }
