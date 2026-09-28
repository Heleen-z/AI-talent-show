# 第三部分：SharePoint Lists 手把手建表指南

本指南只搭建积分结果和排行榜所需的 SharePoint List。第一部分已经完成的 `EngageMessages`、`EngageSyncRuns` 和 Viva Engage 采集流程保持原样。

## 0. 先判断要建哪些表

本项目第二部分把 `ActivityPoints` 定义为最终积分结果，但目前项目文件没有证明该 List 已经在 SharePoint 建立，也没有确认其实际列。因此先登录目标站点核对；不要先盲目新建同名列表。

目标站点：`https://faurecia.sharepoint.com/sites/AIPortal`

1. 打开站点。
2. 左侧选择 **站点内容（Site contents）**。
3. 在列表中查找 `EngageMessages`、`EngageSyncRuns`、`ActivityPoints`、`EngageTextArtifacts`、`EngageEvaluations`、`EvaluationReviews`、`PointsLedger`、`LeaderboardTotals`。
4. 记下每个列表是否存在；如果 `ActivityPoints` 存在，打开它，进入齿轮 → **列表设置（List settings）**，记录列的英文内部名称、类型、必填、唯一值和索引。
5. `EngageMessages`、`EngageSyncRuns` 已属于上游，勿修改其列或流程。

### `ActivityPoints` 是否足够？

若已有 `ActivityPoints`，确认它每条积分记录至少能提供：

| 必需业务值 | 可接受的源列名 |
|---|---|
| 消息关联键 | `MessageKey` |
| 稳定用户键 | `UserId` 或 `SenderId` |
| 榜单显示名 | `UserName` 或 `SenderName` |
| 最终分数 | `FinalPoints` 或 `Points` |
| 消息发布时间 | `PostedAt` |
| 是否可计入榜单 | `ScoringStatus`/`Status`，或清楚定义的等价发布状态 |
| 重复标记 | `IsDuplicate`/`DuplicateFlag`，或已保证重复结果分值为零 |
| 版本依据 | `RuleVersion` 与评分/评估版本，或确认不会重跑覆盖历史的版本策略 |

若这些字段已齐全且可追溯版本，直接以 `ActivityPoints` 为积分事实来源，**跳过 `PointsLedger`**。若缺少审计/版本/发布状态能力，再建 `PointsLedger`。无论哪种情况，都要新建 `LeaderboardTotals`。不要把同一事实同时维护在两个列表中。

> 重要：当前 Python 聚合器默认缺省 `ScoringStatus` 为 `Published`、`IsCurrentVersion` 为真、重复标记为假。生产数据源必须提供这些字段，或在进入聚合器前明确映射并校验；不可因缺字段而意外发布待复核积分。

## 1. 创建列表的通用点击步骤

以下步骤对 `LeaderboardTotals` 和条件创建的 `PointsLedger` 相同：

1. 在 AIPortal 站点点 **站点内容** → **新建** → **列表**。
2. 选择 **空白列表（Blank list）**。
3. 输入英文名称，例如 `LeaderboardTotals`。描述填写用途，建议“Power Apps 排行榜周期汇总缓存”。
4. 选择显示在站点导航栏与否：建议暂不显示在导航栏，仅供应用和管理员使用。
5. 点 **创建**。
6. 新列表通常有默认的 `Title` 列。进入 **设置（齿轮）** → **列表设置** → 点击 Title 列：将显示名称改为 `SummaryTitle`（或保留显示名“标题”），保留单行文本类型，不把它当业务键。后续流程给它写可读值。
7. 回到列表，使用 **+ 添加列** 逐列建立下表中的业务字段。首次创建时直接使用表中的英文名称，以免显示名与内部名不一致。
8. 每列创建后再次进入列表设置确认内部名称、类型和必填选项。SharePoint 改显示名称不会改内部名称。
9. 全部列建完后建立唯一键和索引（本指南第 4 节）。
10. 建好默认视图（第 5 节），再配置权限（第 6 节）。

列类型对照：**单行文本** = Single line of text；**多行纯文本** = Multiple lines of text（Plain text）；**数字** = Number；**日期和时间** = Date and Time；**是/否** = Yes/No；**选择** = Choice。

## 2. 建 `LeaderboardTotals`（必建）

### 2.1 添加列

创建列表后，按下表逐项选择 **+ 添加列**。Title 是 SharePoint 默认列，不要再新建一个同名 Title。

| 内部名称 | 中文显示名 | 类型与设置 | 必填 | 示例/说明 |
|---|---|---|---|---|
| `SummaryKey` | 汇总唯一键 | 单行文本；稍后启用唯一值 | 是 | `1149035372545|Week|2026-W39` |
| `UserId` | 用户 ID | 单行文本 | 是 | 优先映射 EngageMessages.SenderId；不要存成数字 |
| `UserName` | 用户名 | 单行文本 | 是 | 排行榜展示名 |
| `PeriodType` | 周期类型 | 选择；选项 `Week`、`Month`、`Year`；禁止填充选项 | 是 | 值必须使用英文键，Power Apps 再显示中文 |
| `PeriodKey` | 周期键 | 单行文本 | 是 | `2026-W39`、`2026-09`、`2026` |
| `PeriodStart` | 周期开始 | 日期和时间；包含时间 | 是 | UTC 周期起点 |
| `PeriodEnd` | 周期结束 | 日期和时间；包含时间 | 是 | 使用半开区间的结束点：下周期起点 |
| `TotalPoints` | 周期总分 | 数字；0 位小数 | 是 | 当前周期有效积分之和 |
| `AddedPoints` | 本期新增 | 数字；0 位小数 | 是 | 本周期相对上次汇总新增的分数 |
| `PostCount` | 有效帖子数 | 数字；0 位小数 | 是 | 进入榜单的有效消息数 |
| `ContributionCount` | 贡献次数 | 数字；0 位小数 | 是 | 当前按有效积分记录逐条计数 |
| `Rank` | 当前排名 | 数字；0 位小数 | 是 | 1 为第一名 |
| `PreviousRank` | 上次排名 | 数字；0 位小数 | 否 | 新上榜时留空 |
| `RankDelta` | 排名变化 | 数字；0 位小数 | 否 | 正数代表名次上升；新上榜留空 |
| `LastPointAt` | 最近得分时间 | 日期和时间；包含时间 | 否 | 最近一条计分消息的 PostedAt |
| `LastCalculatedAt` | 最近计算时间 | 日期和时间；包含时间 | 是 | 汇总运行完成时刻 |
| `CalculationRunId` | 汇总运行 ID | 单行文本 | 是 | 汇总批次标识 |
| `DataStatus` | 数据状态 | 选择；`Current`、`Partial`、`Frozen`；禁止填充选项 | 是 | 上游不完整时写 `Partial` |
| `IsVisible` | 是否公开显示 | 是/否；默认否 | 是 | 普通用户列表只展示公开前十 |

### 2.2 处理默认 Title 列

保留默认 Title 列作为可读标题，不作为主键。建议显示名改为“汇总标题”，流程写入例如：

```text
张三 - Week - 2026-W39
```

`SummaryKey` 才是跨流程幂等键。

## 3. 条件建 `PointsLedger`（仅 ActivityPoints 不够时）

按第 1 节建空白列表，列表名 `PointsLedger`，描述填写“已计算积分的版本化审计日志，来源于 ActivityPoints/现有评分流程”。默认 Title 显示名改为“积分日志标题”。

### 3.1 添加列

| 内部名称 | 中文显示名 | 类型与设置 | 必填 | 示例/说明 |
|---|---|---|---|---|
| `LedgerKey` | 积分日志唯一键 | 单行文本；稍后启用唯一值 | 是 | `MessageKey|EvaluationVersion|RuleVersion` |
| `MessageKey` | 消息唯一键 | 单行文本 | 是 | 源自 EngageMessages.MessageKey |
| `MessageId` | Viva Engage 消息 ID | 单行文本 | 是 | 源消息业务 ID，不是 SharePoint ID |
| `ThreadId` | 讨论串 ID | 单行文本 | 否 | 源自 EngageMessages.ThreadId |
| `SourceUrl` | 原帖链接 | 多行纯文本；纯文本 | 否 | 源自 EngageMessages.SourceUrl；不复制正文 |
| `UserId` | 用户 ID | 单行文本 | 是 | 源自 SenderId 或稳定用户标识 |
| `UserName` | 用户名 | 单行文本 | 是 | 榜单显示名 |
| `ContributionType` | 贡献类型 | 单行文本 | 是 | 沿用评分管线枚举，例如 question、answer |
| `BasePoints` | 基础分 | 数字；0 位小数 | 是 | 已有积分结果中的基础分 |
| `DimensionPoints` | 维度分 | 数字；0 位小数 | 是 | 已有积分结果中的维度加分 |
| `RawPoints` | 原始积分 | 数字；0 位小数 | 是 | 规则引擎输出的积分值；与 FinalPoints 的区别按现有契约映射 |
| `FinalPoints` | 最终积分 | 数字；0 位小数 | 是 | 排行榜唯一计分值 |
| `IsCapped` | 是否封顶 | 是/否；默认否 | 是 | 沿用积分规则计算结果 |
| `IsDuplicate` | 是否重复 | 是/否；默认否 | 是 | 重复记录不应进入排行榜 |
| `ScoringStatus` | 积分状态 | 选择；`PendingReview`、`Approved`、`Published`、`Rejected`、`Cancelled`；禁止填充 | 是 | 只统计已发布状态 |
| `ReviewRequired` | 是否需要复核 | 是/否；默认否 | 是 | 沿用现有质量门禁结果 |
| `Reviewer` | 复核人 | 人员或组；单选 | 否 | 管理员复核人 |
| `ReviewAt` | 复核时间 | 日期和时间；包含时间 | 否 | UTC 时间 |
| `ReviewComment` | 复核意见 | 多行纯文本；纯文本 | 否 | 不写入不必要的隐私信息 |
| `ScoreModelVersion` | 评分模型版本 | 单行文本 | 否 | 沿用 EngageEvaluations/模型输出 |
| `RuleVersion` | 积分规则版本 | 单行文本 | 是 | 沿用 Python 积分引擎的版本 |
| `EvaluationVersion` | 评分版本 | 单行文本 | 是 | 标识评分输出版本或内容版本 |
| `PostedAt` | 发帖时间 | 日期和时间；包含时间 | 是 | 源自 EngageMessages.PostedAt |
| `WeekKey` | 周键 | 单行文本 | 是 | ISO 周，如 `2026-W39` |
| `MonthKey` | 月键 | 单行文本 | 是 | `2026-09` |
| `YearKey` | 年键 | 单行文本 | 是 | `2026` |
| `IsCurrentVersion` | 是否当前版本 | 是/否；默认是 | 是 | 每个消息只有一个版本为真 |
| `SourceRunId` | 来源运行 ID | 单行文本 | 否 | Python/评分流程运行 ID |
| `CreatedAt` | 创建时间 | 日期和时间；包含时间 | 是 | 写入积分日志的 UTC 时间 |
| `UpdatedAt` | 更新时间 | 日期和时间；包含时间 | 是 | 最后一次修改的 UTC 时间 |

`PointsLedger` 不新增 `ContentText`、摘要或证据正文。原帖通过 `SourceUrl` 打开；评分理由和证据仍保存在现有 `EngageEvaluations`/复核列表中。

## 4. 设置唯一值和索引

每个业务唯一键单独建立唯一索引：

### `LeaderboardTotals`

1. 列表设置 → **索引列（Indexed columns）** → **创建新索引**。
2. 主列选择 `SummaryKey`，启用该列设置中的 **强制唯一值（Enforce unique values）= Yes**。
3. 确认唯一索引创建成功。
4. 为查询列分别建立普通索引：`PeriodType`、`PeriodKey`、`UserId`、`Rank`、`IsVisible`。如界面支持复合索引，可按实际 Power Apps 过滤方式选择；不要假设 SharePoint 会自动创建复合索引。

### `PointsLedger`

1. `LedgerKey` 启用 **强制唯一值 = Yes** 并确认为索引。
2. 为 `MessageKey`、`UserId`、`ScoringStatus`、`PostedAt`、`WeekKey`、`MonthKey`、`YearKey` 建普通索引。

唯一键列设置为必填、单行文本。创建唯一值前检查没有空值或重复值。SharePoint 可能自动要求唯一列必须索引；保留该索引。

## 5. 建议视图

### `LeaderboardTotals` 默认视图：管理员汇总视图

显示列：`PeriodType`、`PeriodKey`、`Rank`、`UserName`、`TotalPoints`、`AddedPoints`、`RankDelta`、`DataStatus`、`LastCalculatedAt`。

排序：`PeriodType` 升序、`PeriodKey` 降序、`Rank` 升序。应用端仍需按已选周期筛选，不要把 SharePoint 默认视图当作安全边界。

### `PointsLedger` 默认视图：最近积分日志

显示列：`PostedAt`、`UserName`、`ContributionType`、`FinalPoints`、`ScoringStatus`、`ReviewRequired`、`MessageKey`、`RuleVersion`、`IsCurrentVersion`。

排序：`PostedAt` 降序。管理员另建 `待复核` 视图，筛选 `ScoringStatus = PendingReview`。

## 6. 权限与隐私

排行榜表含有员工积分数据。创建后进入 **列表设置 → 此列表的权限**：

1. `LeaderboardTotals` 普通成员只给读取权限，积分写入/汇总账号给编辑权限，站点管理员保留管理权限。
2. `PointsLedger` 含审计和复核信息，普通用户不要直接获得整表访问；管理员和自动化服务账号按职责授权。Power Apps 的“只显示自己的行”公式不是数据安全边界。
3. `EngageMessages` 可能包含私有社区消息，继续沿用已确认的站点权限；不要因排行榜而放宽它的权限。
4. 若普通用户需要直接看公开前十且不能看到整张 `LeaderboardTotals`，必须先设计安全的发布边界（例如单独公开榜单列表或经权限验证的服务）。仅设置 `IsVisible` 或 Power Apps Filter 不会隐藏 SharePoint REST/列表中的其他行。

## 7. 建好后的检查清单

- `EngageMessages`、`EngageSyncRuns` 未被修改。
- 实际确认 `ActivityPoints` 是否存在及其列结构。
- 若 `ActivityPoints` 有稳定用户键、MessageKey、最终分数、发布时间、发布状态、重复标记和版本追溯，则跳过 `PointsLedger`。
- `LeaderboardTotals` 已建，`SummaryKey` 唯一。
- 若创建 `PointsLedger`，`LedgerKey` 唯一，且不含原帖正文副本。
- 所有 ID 都是单行文本；没有把 Viva Engage ID 建成 Number。
- 日期列启用时间并按 UTC 写入。
- 数值列的小数位数为 0（如将来有小数积分，再统一调整）。
- 状态选择值与 Python/Power Automate 的实际状态完全一致。
- 列表权限已检查；普通用户不能通过直接打开列表读取所有积分日志。
- 默认视图使用有索引的筛选列，数据增长后避免无筛选全表查询。

## 8. 建表后下一步

完成这些列表后，再配置下游 Power Automate 汇总流程和 Power Apps。首次写入前，先用 2–3 条人工测试记录验证唯一键、状态过滤、周期键、权限和前十筛选；确认结果后再接入真实积分输出。

