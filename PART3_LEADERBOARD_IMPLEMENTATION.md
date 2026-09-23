# 第三部分：积分日志与排行榜实现契约

本实现严格位于第一部分 `EngageMessages` 采集链路之后。它不修改 Viva Engage → Power Automate → `EngageMessages`，也不从 Viva Engage 重新取数。

## 事实来源

现有 Python 评分管线产生 `ActivityPoints` 的最终积分。若 `ActivityPoints` 已具备下列字段，则直接从它汇总；否则新增 `PointsLedger` 作为审计日志层：

`MessageKey`、`UserId`/`SenderId`、`UserName`/`SenderName`、`FinalPoints`/`Points`、`ScoringStatus`、`IsDuplicate`、`IsCurrentVersion`、`PostedAt`、`RuleVersion`、`EvaluationVersion`。

Power Apps 不计算积分，Power Automate 不替代 `poc/baseline.py` 中的积分规则。

## SharePoint 建表

### PointsLedger（仅当 ActivityPoints 不完整时创建）

使用单行文本的 `LedgerKey` 作为唯一列，值为 `MessageKey|EvaluationVersion|RuleVersion`。其他列按计划中的字段创建：消息/用户身份、最终积分、评分状态、复核信息、模型/规则版本、`PostedAt`、`WeekKey`、`MonthKey`、`YearKey`、当前版本标记和运行 ID。

索引 `MessageKey`、`UserId`、`ScoringStatus`、`PostedAt`、三个周期键。不要复制正文，原帖通过 `SourceUrl` 回指 `EngageMessages`。

### LeaderboardTotals（始终创建）

`SummaryKey` 唯一，值为 `UserId|PeriodType|PeriodKey`。字段包括周期边界、`TotalPoints`、`AddedPoints`、贡献数、`Rank`、`PreviousRank`、`RankDelta`、最近得分时间、汇总运行 ID、数据状态和 `IsVisible`。索引 `PeriodType`、`PeriodKey`、`UserId`、`Rank`、`IsVisible`。

## 汇总规则

`poc/leaderboard.py` 的 `build_totals()` 接收已计算的最终积分，过滤 `Published`/`Approved`、当前版本且非重复记录，按自然周（周一开始）、自然月和自然年聚合。排序为总分降序、最近得分时间升序、用户名升序；前十名写入 `IsVisible=true`。使用 `previous` 参数计算 `AddedPoints`、`PreviousRank` 和 `RankDelta`。

示例：

```python
from poc.leaderboard import build_totals

totals = build_totals(activity_points_rows, previous=previous_totals, run_id=run_id)
```

## Power Automate 下游流程

1. 监听现有 `ActivityPoints`（或 `EngageEvaluations` 发布状态），通过 `LedgerKey` 幂等写入 `PointsLedger`；不重新评分、不读取 Viva Engage。
2. 定时或发布后触发汇总：读取有效积分，按用户和周期聚合，更新 `LeaderboardTotals`。
3. 若 `EngageSyncRuns`、文本处理或评分批次为 `Partial`/`Failed`，将汇总的 `DataStatus` 设为 `Partial`，并在 Power Apps 显示提示。
4. 人工修订沿用 `EvaluationReviews`/现有复核流程，新增积分版本后重新汇总；不覆盖历史版本。

## Power Apps 企业数据看板

数据源：排行榜首页使用 `LeaderboardTotals`；明细使用 `PointsLedger` 或完整的 `ActivityPoints`；帖子跳转使用 `EngageMessages.SourceUrl`。

页面包含：周榜/月榜/年榜切换、总分/本期新增切换、前三名卡片、4–10 名列表、当前用户排名卡片、个人积分明细、管理员复核页。普通用户只过滤自己的日志；管理员可查看完整榜单。

推荐颜色：主色 `#0F6CBD`，背景 `#F5F7FA`，本期新增/上升 `#107C10`，下降 `#D13438`，卡片白色。状态必须同时使用文字和图标，不能只依赖颜色。

## 验收

- 第一部分采集流程和 `EngageMessages` 字段不变。
- 相同 `LedgerKey`/`SummaryKey` 重跑不产生重复有效记录。
- 只有已发布、当前版本、非重复积分进入榜单。
- 周/月/年周期、排名和本期新增可复算。
- 普通用户只能查看自己的明细；管理员可查看完整数据。
- 上游不完整时显示 `Partial`，不伪装成零分。

