# -*- coding: utf-8 -*-
"""生成匿名化示例数据集 examples/EngageMessages_sample.csv。

数据来源：data/EngageMessages_20260922.csv（2026-09-22 EngageMessages 列表导出，12 条）。
按 PART2_POC_REPORT.md §5.2 的匿名化约定处理后入库（agent.md 治理：员工数据不进 Git）：

- SenderName：真实姓名 → 服务账号 / 员工B（与报告 §5.2 一致）；
- SenderId：→ 900000000000x（同一发送者固定映射）；
- NetworkId / GroupId：→ 固定占位值；
- MessageId / ThreadId / ReplyToId / MessageKey：按首次出现顺序 → 400000000000x（引用关系保持不变）；
- SourceUrl：→ https://engage.example.invalid/threads/<新MessageId>（原 URL 含租户与真实线程令牌，不入库）；
- LastRunId：→ example-run-20260922。

Title / ContentText 原样保留：正文内容不指向个人，作者已匿名化（同报告口径）。
生成后自带校验：输出中不得再出现任何原始姓名 / 原始 ID / 租户 URL，ThreadId / ReplyToId 必须全部可解析。

用法（项目根目录）：PYTHONUTF8=1 python tools/make_example_dataset.py
"""

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "EngageMessages_20260922.csv"
DST = ROOT / "examples" / "EngageMessages_sample.csv"

# 姓名与账号映射（与 PART2_POC_REPORT.md §5.2 的匿名化口径一致）
SENDER_NAME_MAP = {
    "FCM China AI Office": "服务账号",
    "YAN Ying": "员工B",
}
SENDER_ID_MAP = {
    "1149035372545": "9000000000001",  # FCM China AI Office → 服务账号
    "1238904135681": "9000000000002",  # YAN Ying → 员工B
}
NETWORK_ID_NEW = "70000000001"
GROUP_ID_NEW = "70000000002"
LAST_RUN_ID_NEW = "example-run-20260922"
URL_TEMPLATE = "https://engage.example.invalid/threads/{mid}"
NEW_MID_BASE = 4_000_000_000_000  # 新 MessageId 从 4000000000001 递增


def main() -> None:
    with open(SRC, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not rows:
        sys.exit("源 CSV 为空")

    # MessageId / ThreadId / ReplyToId 统一按首现顺序编号
    id_map: dict[str, str] = {}

    def remap_id(old: str) -> str:
        old = old.strip()
        if old not in id_map:
            id_map[old] = str(NEW_MID_BASE + len(id_map) + 1)
        return id_map[old]

    out_rows = []
    for r in rows:
        mid = remap_id(r["MessageId"])
        new = dict(r)
        new["MessageId"] = mid
        new["MessageKey"] = f"{NETWORK_ID_NEW}:{mid}"
        new["NetworkId"] = NETWORK_ID_NEW
        new["GroupId"] = GROUP_ID_NEW
        new["ThreadId"] = remap_id(r["ThreadId"])
        if r.get("ReplyToId", "").strip():
            new["ReplyToId"] = remap_id(r["ReplyToId"])
        new["SenderName"] = SENDER_NAME_MAP.get(r["SenderName"], r["SenderName"])
        new["SenderId"] = SENDER_ID_MAP.get(r["SenderId"], r["SenderId"])
        new["SourceUrl"] = URL_TEMPLATE.format(mid=mid)
        new["LastRunId"] = LAST_RUN_ID_NEW
        out_rows.append(new)

    DST.parent.mkdir(exist_ok=True)
    with open(DST, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    # ---- 校验：输出中不得残留任何原始标识 ----
    banned = set(SENDER_NAME_MAP) | set(SENDER_ID_MAP) | set(id_map)
    banned |= {SRC.name, "engage.cloud.microsoft", "faurecia.onmicrosoft.com"}
    # 整列替换的值不在 id_map 里，需单独禁用
    banned |= {rows[0]["NetworkId"], rows[0]["GroupId"], rows[0]["LastRunId"]}
    banned |= {r["SourceUrl"] for r in rows}
    text = DST.read_text(encoding="utf-8-sig")
    leaked = sorted(p for p in banned if p in text)
    if leaked:
        DST.unlink(missing_ok=True)
        sys.exit(f"校验失败，输出仍含原始标识: {leaked}")
    # ThreadId / ReplyToId 必须全部可解析到新 ID 集
    new_ids = set(id_map.values())
    for r in out_rows:
        assert r["ThreadId"] in new_ids, r["ThreadId"]
        if r.get("ReplyToId", "").strip():
            assert r["ReplyToId"] in new_ids, r["ReplyToId"]
    assert len({r["MessageId"] for r in out_rows}) == len(out_rows), "MessageId 重复"
    assert re.fullmatch(r"\d+", NETWORK_ID_NEW) and all(
        re.fullmatch(r"\d+:\d+", r["MessageKey"]) for r in out_rows
    ), "MessageKey 结构被破坏"

    print(f"OK: {len(out_rows)} 条 → {DST.relative_to(ROOT)}")
    print(f"消息 ID 映射 {len(id_map)} 个；发送者 {len(SENDER_NAME_MAP)} 名已匿名化")


if __name__ == "__main__":
    main()
