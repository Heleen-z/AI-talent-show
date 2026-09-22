# -*- coding: utf-8 -*-
"""训练简单 ML 模型（弱监督）。

没有人工标注 → 用规则基线的输出当弱标签。验证的是「训练→持久化→加载推理」
整条工程链路是否成立；分数只反映与弱标签的一致性，不代表真实质量。

用法：PYTHONUTF8=1 python -m poc.train [csv路径]
"""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import LeaveOneOut, cross_val_predict

from .baseline import DIMENSION_NAMES, RULES_VERSION, Message, build_contexts, score, summarize
from .features import FEATURES_VERSION, FeatureSpace
from .preprocess import preprocess_message

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data" / "EngageMessages_20260922.csv"
MODEL_DIR = ROOT / "poc_output" / "models"
MODEL_VERSION = "sklearn-v0.1"


def load_messages(csv_path: Path) -> tuple[list[Message], dict]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    messages = [Message(row=r, artifact=preprocess_message(
        r["MessageKey"], r.get("ContentText", ""), r.get("LanguageCode") or None))
        for r in rows]
    return messages, build_contexts(messages)


def weak_labels(messages, ctxs):
    """用规则基线给每条消息打弱标签（类型 + 四维度等级）。"""
    y_type, y_dims = [], {d: [] for d in DIMENSION_NAMES}
    for m in messages:
        summary = summarize(m, ctxs[m.message_key])
        ev = score(m, summary, ctxs[m.message_key])
        y_type.append(ev["contribution_type"])
        for d in DIMENSION_NAMES:
            y_dims[d].append(ev["dimensions"][d]["level"])
    return y_type, y_dims


def main():
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    messages, ctxs = load_messages(csv_path)
    y_type, y_dims = weak_labels(messages, ctxs)
    print(f"训练样本 {len(messages)} 条，弱标签分布：")
    from collections import Counter
    print("  类型:", dict(Counter(y_type)))
    for d in DIMENSION_NAMES:
        print(f"  {d}:", dict(sorted(Counter(y_dims[d]).items())))

    fs = FeatureSpace()
    X = fs.fit(messages)

    clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(X, y_type)
    ridges = {d: Ridge(alpha=1.0).fit(X, y_dims[d]) for d in DIMENSION_NAMES}

    # 留一交叉验证：12 条样本下唯一说得过去的评估方式（仍然只是与弱标签的一致性）
    loo_pred_type = cross_val_predict(
        LogisticRegression(max_iter=2000, class_weight="balanced"), X, y_type,
        cv=LeaveOneOut())
    type_acc = float((loo_pred_type == __import__("numpy").asarray(y_type)).mean())
    print(f"\nLOOCV 类型准确率（vs 弱标签）: {type_acc:.0%}")

    import numpy as np
    for d in DIMENSION_NAMES:
        pred = cross_val_predict(Ridge(alpha=1.0), X, y_dims[d], cv=LeaveOneOut())
        mae = float(np.abs(np.clip(np.round(pred), 0, 3) - np.array(y_dims[d])).mean())
        print(f"LOOCV {d} 维度 MAE（取整后）: {mae:.2f} 级")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / f"model-{MODEL_VERSION}.joblib"
    joblib.dump({
        "model_version": MODEL_VERSION,
        "features_version": FEATURES_VERSION,
        "weak_label_source": f"rules:{RULES_VERSION}",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_samples": len(messages),
        "classes": list(clf.classes_),
        "feature_space": {"vectorizer": fs.vectorizer, "scaler": fs.scaler},
        "type_classifier": clf,
        "dimension_ridges": ridges,
        "metrics": {"loocv_type_accuracy": type_acc},
    }, path)
    meta = json.dumps({"model_version": MODEL_VERSION, "weak_labels": True,
                       "trained_at": datetime.now(timezone.utc).date().isoformat()},
                      ensure_ascii=False)
    (MODEL_DIR / f"model-{MODEL_VERSION}.meta.json").write_text(meta, encoding="utf-8")
    print(f"\n模型已保存：{path}")
    print("注意：弱监督 + 12 条样本，此模型只用于可行性链路演示，不可用于发布评分。")


if __name__ == "__main__":
    main()
