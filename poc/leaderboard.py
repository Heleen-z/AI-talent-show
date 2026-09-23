"""第三部分：从 ActivityPoints/PointsLedger 生成排行榜汇总。

本模块只处理已经由现有评分管线生成的最终积分，不读取 Viva Engage，
也不重新计算评分。输入可来自 ActivityPoints 或 PointsLedger 的 Graph
字段字典；输出是可直接映射到 LeaderboardTotals 的记录。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping


PUBLISHED = {"Published", "Approved"}


@dataclass(frozen=True)
class Period:
    kind: str
    key: str
    start: datetime
    end: datetime


def _dt(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value or "").replace("Z", "+00:00")
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def periods_for(value: object) -> tuple[Period, Period, Period]:
    """Return ISO week, calendar month and calendar year containing ``value``."""
    dt = _dt(value)
    monday = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    sunday_end = monday + timedelta(days=7)
    month_start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    year_start = dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    year_end = year_start.replace(year=year_start.year + 1)
    iso = dt.isocalendar()
    return (
        Period("Week", f"{iso.year}-W{iso.week:02d}", monday, sunday_end),
        Period("Month", f"{dt.year:04d}-{dt.month:02d}", month_start, next_month),
        Period("Year", f"{dt.year:04d}", year_start, year_end),
    )


def _valid(row: Mapping[str, object]) -> bool:
    status = str(row.get("ScoringStatus", row.get("Status", "Published")))
    return (
        status in PUBLISHED
        and bool(row.get("IsCurrentVersion", True))
        and not bool(row.get("IsDuplicate", row.get("DuplicateFlag", False)))
    )


def build_totals(rows: Iterable[Mapping[str, object]], *, previous: Mapping[tuple[str, str, str], Mapping[str, object]] | None = None,
                 run_id: str = "") -> list[dict[str, object]]:
    """Aggregate published points into ``LeaderboardTotals`` rows.

    ``rows`` must already contain final points from ActivityPoints or PointsLedger.
    ``previous`` is keyed by ``(UserId, PeriodType, PeriodKey)`` and is used only
    for AddedPoints and PreviousRank; it never changes the source points.
    """
    buckets: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        if not _valid(row):
            continue
        user_id = str(row.get("UserId") or row.get("SenderId") or "").strip()
        if not user_id:
            raise ValueError("published point row is missing UserId/SenderId")
        posted = row.get("PostedAt")
        if not posted:
            raise ValueError(f"published point row for {user_id} is missing PostedAt")
        points = float(row.get("FinalPoints", row.get("Points", 0)) or 0)
        username = str(row.get("UserName") or row.get("SenderName") or user_id)
        for period in periods_for(posted):
            key = (user_id, period.kind, period.key)
            bucket = buckets.setdefault(key, {
                "UserId": user_id, "UserName": username,
                "PeriodType": period.kind, "PeriodKey": period.key,
                "PeriodStart": period.start.isoformat(), "PeriodEnd": period.end.isoformat(),
                "TotalPoints": 0, "PostCount": 0, "ContributionCount": 0,
                "LastPointAt": None,
            })
            bucket["TotalPoints"] += points
            bucket["PostCount"] += 1
            bucket["ContributionCount"] += 1
            posted_dt = _dt(posted)
            if not bucket["LastPointAt"] or posted_dt.isoformat() > str(bucket["LastPointAt"]):
                bucket["LastPointAt"] = posted_dt.isoformat()

    result: list[dict[str, object]] = []
    for period_key in sorted({(v["PeriodType"], v["PeriodKey"]) for v in buckets.values()}):
        period_rows = [v for v in buckets.values() if (v["PeriodType"], v["PeriodKey"]) == period_key]
        period_rows.sort(key=lambda v: (-float(v["TotalPoints"]), str(v["LastPointAt"]), str(v["UserName"])))
        for rank, item in enumerate(period_rows, 1):
            identity = (str(item["UserId"]), str(item["PeriodType"]), str(item["PeriodKey"]))
            old = (previous or {}).get(identity, {})
            total = float(item["TotalPoints"])
            old_total = float(old.get("TotalPoints", 0) or 0)
            previous_rank = old.get("Rank")
            item.update({
                "SummaryKey": f"{item['UserId']}|{item['PeriodType']}|{item['PeriodKey']}",
                "TotalPoints": total,
                "AddedPoints": total - old_total,
                "Rank": rank,
                "PreviousRank": previous_rank,
                "RankDelta": (int(previous_rank) - rank) if previous_rank is not None else None,
                "CalculationRunId": run_id,
                "LastCalculatedAt": datetime.now(timezone.utc).isoformat(),
                "DataStatus": "Current",
                "IsVisible": rank <= 10,
            })
            result.append(item)
    return result

