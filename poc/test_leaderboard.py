from poc.leaderboard import build_totals, periods_for


def test_periods_use_iso_week_and_calendar_boundaries():
    week, month, year = periods_for("2026-09-22T10:00:00+08:00")
    assert week.key == "2026-W39"
    assert month.key == "2026-09"
    assert year.key == "2026"
    assert week.start.hour == 0


def test_build_totals_filters_invalid_rows_and_marks_top_ten():
    rows = [
        {"UserId": "u1", "UserName": "A", "FinalPoints": 5, "PostedAt": "2026-09-22T00:00:00Z", "ScoringStatus": "Published"},
        {"UserId": "u2", "UserName": "B", "FinalPoints": 3, "PostedAt": "2026-09-22T01:00:00Z", "ScoringStatus": "Published"},
        {"UserId": "u3", "UserName": "C", "FinalPoints": 99, "PostedAt": "2026-09-22T02:00:00Z", "ScoringStatus": "Rejected"},
    ]
    totals = build_totals(rows, run_id="run-1")
    week = [x for x in totals if x["PeriodType"] == "Week"]
    assert [x["UserId"] for x in week] == ["u1", "u2"]
    assert week[0]["Rank"] == 1 and week[0]["IsVisible"] is True
    assert week[0]["CalculationRunId"] == "run-1"


def test_added_points_and_rank_delta_use_previous_snapshot():
    rows = [{"UserId": "u1", "UserName": "A", "FinalPoints": 8, "PostedAt": "2026-09-22T00:00:00Z", "ScoringStatus": "Published"}]
    previous = {("u1", "Week", "2026-W39"): {"TotalPoints": 5, "Rank": 2}}
    week = next(x for x in build_totals(rows, previous=previous) if x["PeriodType"] == "Week")
    assert week["AddedPoints"] == 3
    assert week["PreviousRank"] == 2
    assert week["RankDelta"] == 1

