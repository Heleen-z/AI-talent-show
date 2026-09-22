# -*- coding: utf-8 -*-
"""可行性验证 POC 入口。

用法（项目根目录下）：
    PYTHONUTF8=1 python -m poc.run_poc [--model rules|ml] [csv路径]

--model ml 需要先跑 python -m poc.train。默认 rules（零依赖可跑）。
输出：poc_output/ 下逐条 JSON 产物 + summary_table.csv + 控制台可行性报告。
只读本地 CSV，不碰 SharePoint，不发布任何积分。
"""
import argparse
import csv
import json
from pathlib import Path

from .baseline import run_pipeline

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "data" / "EngageMessages_20260922.csv"
OUT_DIR = ROOT / "poc_output"


def load_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # MessageId 等一律保持字符串（PART2 §2.1），CSV 来源已是字符串
    for r in rows:
        r["MessageId"] = str(r.get("MessageId", "")).strip()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default=str(DEFAULT_CSV))
    parser.add_argument("--model", choices=["rules", "ml"], default="rules")
    args = parser.parse_args()

    rows = load_rows(Path(args.csv))
    print(f"输入 {Path(args.csv).name}：{len(rows)} 条消息，评分后端 = {args.model}")

    evaluate = None
    if args.model == "ml":
        from .ml_model import SklearnBackend

        backend = SklearnBackend.load()
        print(f"已加载模型 {backend.bundle['model_version']} "
              f"(弱标签源: {backend.bundle['weak_label_source']}, "
              f"训练时间: {backend.bundle['trained_at']})")
        evaluate = backend.evaluate

    results = run_pipeline(rows, evaluate=evaluate)

    OUT_DIR.mkdir(exist_ok=True)
    table_path = OUT_DIR / f"summary_table_{args.model}.csv"
    with open(table_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["MessageKey", "Sender", "IsRoot", "PostedAt", "Intent", "Conf",
                    "维度分(relevance/value/evidence/impact)", "总分", "积分",
                    "重复", "需复核", "门禁"])
        for r in results:
            d = r["evaluation"]["dimensions"]
            w.writerow([
                r["message_key"], r["sender"], r["is_root"], r["posted_at"],
                r["evaluation"]["contribution_type"],
                r["evaluation"].get("type_confidence", ""),
                "/".join(str(d[k]["level"]) for k in
                         ("relevance", "value", "evidence", "discussion_impact")),
                r["points"]["dimension_total"], r["points"]["points"],
                "Y" if r["points"]["duplicate_flag"] else "",
                "Y" if r["evaluation"]["needs_human_review"] else "",
                "PASS" if not r["points"].get("gate_failures")
                else ";".join(r["points"]["gate_failures"]),
            ])

    suffix = "" if args.model == "rules" else f"_{args.model}"
    for r in results:
        safe = r["message_key"].replace(":", "_")
        with open(OUT_DIR / f"artifact_{safe}{suffix}.json", "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)

    # ---- 控制台报告 ----
    print(f"\n逐条结果（完整产物在 {OUT_DIR}\\）")
    print(f"{'MessageKey':<28}{'类型':<16}{'维r/v/e/i':<10}{'积分':<5}{'备注'}")
    for r in results:
        d = r["evaluation"]["dimensions"]
        dims = "/".join(str(d[k]["level"]) for k in
                        ("relevance", "value", "evidence", "discussion_impact"))
        notes = []
        if r["points"]["duplicate_flag"]:
            notes.append("疑似重复")
        if r["evaluation"]["needs_human_review"]:
            notes.append("需复核")
        if r["points"].get("gate_failures"):
            notes.append("门禁:" + ";".join(r["points"]["gate_failures"])[:40])
        conf = r["evaluation"].get("type_confidence")
        conf_note = f" (p={conf:.2f})" if conf is not None and conf < 0.6 else ""
        print(f"{r['message_key']:<28}{r['evaluation']['contribution_type'] + conf_note:<16}"
              f"{dims:<10}{r['points']['points']:<5}{','.join(notes)}")

    by_sender: dict[str, int] = {}
    for r in results:
        by_sender[r["sender"]] = by_sender.get(r["sender"], 0) + r["points"]["points"]

    gate_pass = sum(1 for r in results if not r["points"].get("gate_failures"))
    dups = sum(1 for r in results if r["points"]["duplicate_flag"])
    reviews = sum(1 for r in results if r["evaluation"]["needs_human_review"])

    print("\n===== 可行性验证检查单 =====")
    checks = [
        ("F1 端到端流水线跑通（预处理→摘要→评分→积分→门禁）", f"{len(results)}/{len(rows)}"),
        ("F2 证据可回指原文（§8 质量门禁）", f"{gate_pass}/{len(results)} 通过"),
        ("F3 幂等键与重复检测（§11.1）", f"{dups} 条被标记疑似重复、积分清零"),
        ("F4 NeedsReview 通道（§4）", f"{reviews} 条进入复核"),
        ("F5 积分封顶（§9.2 per_item_cap=10）",
         "已生效" if all(r["points"]["points"] <= 10 for r in results) else "失败"),
        ("F6 员工聚合（SenderId 维度）", "; ".join(f"{k}={v}" for k, v in by_sender.items())),
    ]
    if args.model == "ml":
        rules_results = run_pipeline(rows)
        type_agree = sum(
            1 for a, b in zip(results, rules_results)
            if a["evaluation"]["contribution_type"] == b["evaluation"]["contribution_type"])
        pts_diff = [abs(a["points"]["points"] - b["points"]["points"])
                    for a, b in zip(results, rules_results)]
        checks.append((
            "F7 ML 后端 vs 规则基线一致性",
            f"类型 {type_agree}/{len(results)}，积分平均差 {sum(pts_diff)/len(pts_diff):.1f}"))
    for name, status in checks:
        print(f"  [{'x' if '失败' not in str(status) else ' '}] {name}: {status}")

    total = sum(r["points"]["points"] for r in results)
    print(f"\n总积分（示例，不发布）：{total}    明细表：{table_path}")


if __name__ == "__main__":
    main()
