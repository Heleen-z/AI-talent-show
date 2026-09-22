# -*- coding: utf-8 -*-
"""特征工程：TF-IDF 文本特征 + 数值统计特征。

PART2 §10：长度/格式只作特征，不得直接兑换积分——数值特征进入模型学权重，
与规则基线里"字数=分数"的直通逻辑不同。
"""
import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer

from .baseline import ANSWER_HINT_RE, PRACTICE_HINT_RE, QUESTION_HINT_RE, Message, _tokenize

FEATURES_VERSION = "tfidf+stats-v1"

NUMERIC_NAMES = [
    "characters", "words", "paragraphs", "urls", "mentions", "hashtags",
    "code_blocks", "is_reply", "has_question_hint", "has_answer_hint",
    "has_practice_hint", "chars_per_paragraph",
]


def numeric_features(m: Message) -> list[float]:
    s = m.artifact["text_stats"]
    t = m.artifact["normalized_text"]
    return [
        float(s["characters"]), float(s["words"]), float(s["paragraphs"]),
        float(s["urls"]), float(s["mentions"]), float(s["hashtags"]),
        float(s["code_blocks"]),
        float(m.row.get("IsRootPost") != "True"),
        float(bool(QUESTION_HINT_RE.search(t[:300]))),
        float(bool(ANSWER_HINT_RE.search(t))),
        float(bool(PRACTICE_HINT_RE.search(t))),
        s["characters"] / max(s["paragraphs"], 1),
    ]


class FeatureSpace:
    """训练与推理共用的特征空间（向量化器 + 标准化器一起持久化）。"""

    def __init__(self):
        self.vectorizer = TfidfVectorizer(tokenizer=_tokenize, token_pattern=None,
                                          min_df=1, sublinear_tf=True)
        self.scaler = None  # 训练时拟合

    def fit(self, messages: list[Message]):
        from sklearn.preprocessing import StandardScaler

        X_text = self.vectorizer.fit_transform(self._texts(messages))
        X_num = np.array([numeric_features(m) for m in messages])
        self.scaler = StandardScaler().fit(X_num)
        return self.transform(messages)

    def transform(self, messages: list[Message]):
        X_text = self.vectorizer.transform(self._texts(messages))
        X_num = self.scaler.transform(np.array([numeric_features(m) for m in messages]))
        return hstack([X_text, X_num]).tocsr()

    @staticmethod
    def _texts(messages):
        # 送模型版文本：占位符已替换为 [URL]/[CODE_BLOCK] 等类型标记（§6.1）
        return [m.artifact["model_input_text"] or " " for m in messages]
