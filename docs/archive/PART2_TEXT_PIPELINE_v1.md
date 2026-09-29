# 第二部分：Viva Engage 文本处理、摘要与评分流水线

文档版本：1.0
更新时间：2026-09-22
项目阶段：第二部分（承接第一部分 Viva Engage → SharePoint 数据通路）
适用场景：AI 论坛活动积分、激励和培训反馈

## 1. 目标与范围

第一部分负责把 Viva Engage 社区中的主帖和回复采集到 SharePoint。本部分从 SharePoint 的 `EngageMessages` 表读取已经落库的消息，完成以下处理：

```text
SharePoint EngageMessages
    → 取数与批次登记
    → 文本预处理与规范化
    → 摘要生成
    → 摘要质量检查与保存
    → 贡献类型识别
    → 评分模型计算
    → 评分结果与证据保存
    → 活动积分汇总
    → Power Automate 反馈、复核和发布
```

本部分的结果用于活动积分、激励和培训反馈，不作为正式绩效、晋升或纪律处分的唯一依据。评分必须保留原文证据、规则版本和模型版本，以便员工或活动管理员复核。

## 2. 与第一部分的接口

### 2.1 上游输入

上游是第一部分维护的 SharePoint 列表 `EngageMessages`，站点为 AIPortal。Python 不直接依赖 Power Automate 的动作输出，也不直接从 Viva Engage 抓取消息；Python 只读取已经落库的记录。

关键字段如下：

| 字段 | 用途 | 处理要求 |
|---|---|---|
| `MessageKey` | 业务唯一键 | 使用 `NetworkId:MessageId`，整个流水线的幂等键 |
| `MessageId` | 消息 ID | 字符串保存，不能转换为浮点数 |
| `ThreadId` | 讨论串 ID | 用于构造上下文和合并同一讨论串 |
| `ReplyToId` | 直接回复 ID | 判断回复关系 |
| `SenderId` | 作者 ID | 员工聚合的稳定标识 |
| `SenderName` | 作者显示名 | 展示用途；模型输入建议使用匿名化作者标识 |
| `ContentText` | 纯文本正文 | 文本处理主输入 |
| `PostedAt` | 发帖时间 | 活动周期、时区和时效计算 |
| `SourceUrl` | 原帖链接 | 评分证据和复核入口 |
| `LanguageCode` | 语言代码 | 选择语言处理策略 |
| `IsRootPost` | 是否主帖 | 区分提问、分享和回复 |
| `IsSystemMessage` | 是否系统消息 | 系统消息不进入员工内容评分 |
| `LastSeenAt` | 最近采集时间 | 增量处理和数据新鲜度检查 |
| `LastRunId` | 最近采集运行 ID | 追踪上游采集批次 |

`EngageSyncRuns` 是上游的采集日志。Python 在开始处理前应读取最近一次运行状态；如果上游状态为 `Partial` 或 `Failed`，本批次仍可处理已成功入库的消息，但不得对外宣称本周期评分覆盖了全部论坛内容。

### 2.2 下游输出

建议在 SharePoint 新建以下列表，或在已有列表中增加相同字段：

| 列表 | 作用 |
|---|---|
| `TextProcessingRuns` | 文本处理批次、模型版本、耗时和错误统计 |
| `EngageTextArtifacts` | 规范化文本、摘要、语言、质量检查和处理状态 |
| `EngageEvaluations` | 分项评分、模型理由、原文证据和复核状态 |
| `ActivityPoints` | 面向活动积分的最终结果 |
| `EvaluationReviews` | 员工或管理员提出的漏帖、异议和人工修订 |

任何列表都不应把 SharePoint 系统行 ID 当作 Viva Engage 消息 ID。所有跨表关联使用 `MessageKey`，讨论串使用 `ThreadId`。

## 3. 总体架构

本项目预计采用本地 Python 方案。Windows 任务计划程序或内部服务器定时启动 Python；Python 主动通过 Microsoft Graph 访问 SharePoint。Power Automate 负责上游采集和下游通知、审批，不负责直接执行完整评分模型。

```mermaid
flowchart LR
    A[EngageMessages<br/>SharePoint] --> B[Batch Reader<br/>读取 Pending/Changed]
    B --> C[Preprocessor<br/>清洗、规范化、脱敏]
    C --> D[Summary Model<br/>生成结构化摘要]
    D --> E[Artifact Store<br/>保存摘要与质量状态]
    E --> F[Scoring Model<br/>分类、证据抽取、评分]
    F --> G[Evaluation Store<br/>保存评分与解释]
    G --> H[Points Engine<br/>积分规则与封顶]
    H --> I[ActivityPoints<br/>周期积分]
    I --> J[Power Automate<br/>复核、通知、发布]
    B --> K[TextProcessingRuns<br/>批次日志]
    C --> K
    D --> K
    F --> K
    H --> K
```

## 4. 状态机与处理批次

每条消息在 `EngageTextArtifacts` 和 `EngageEvaluations` 中都要有独立状态。推荐状态如下：

```text
Pending
  → Preprocessed
  → Summarized
  → Scored
  → Published

任意阶段 → NeedsReview
任意阶段 → Failed（达到重试上限）
```

`NeedsReview` 的触发条件包括：正文为空但不是系统消息、语言检测不确定、上下文缺失、摘要质量检查失败、结构化输出无法解析、模型分数与规则冲突、疑似重复或高影响力积分。

批次使用 `ProcessingRunId` 标识。每次运行开始时创建 `TextProcessingRuns` 记录，写入 `Running`；正常完成写 `Succeeded`；存在可继续处理的单条错误写 `Partial`；批次无法完成或权限失效写 `Failed`。

Python 必须以 `MessageKey + ContentHash + PipelineVersion` 作为处理缓存键：

- 正文和规则都没有变化时跳过重复计算；
- 正文变化时重新预处理、摘要和评分；
- 规则或模型版本变化时可以选择重算；
- 人工确认过的结果不被自动重算覆盖，除非明确建立新的评估版本。

## 5. 阶段一：取数、增量和批次控制

### 5.1 取数条件

第一版可以按以下条件读取：

```text
ScoringStatus = Pending
或 LastScoredAt 为空
或 LastSeenAt > LastProcessedAt
或 PipelineVersion 与当前版本不同
```

查询应按 `MessageKey`、`ThreadId`、`PostedAt` 和状态字段分批读取。SharePoint 视图和查询不要依赖一次读取全部列表；大量列表必须使用索引字段和分页。

### 5.2 线程上下文

单条回复的评分不能只把回复本身送入模型。最少应提供：

1. 目标消息正文；
2. 它直接回复的消息（如果存在）；
3. 讨论串主帖；
4. 同一线程中必要的前后文，设置长度上限；
5. 目标消息与上下文的作者角色标识。

上下文应明确标注 `target_message`、`thread_starter`、`parent_message` 和 `context_message`，避免模型把别人的观点归到目标员工名下。

### 5.3 取数伪代码

```python
def load_work_items(sp_client, pipeline_version, limit=200):
    rows = sp_client.query_messages(
        filter=(
            "IsSystemMessage ne true and "
            "(ScoringStatus eq 'Pending' or "
            "PipelineVersion ne '{version}')"
        ).format(version=pipeline_version),
        order_by="PostedAt asc",
        top=limit,
    )
    return deduplicate(rows, key="MessageKey")
```

实际 Graph 查询需要根据租户的列表 ID、内部列名和权限配置生成，不能把显示名称直接假设为内部名称。

## 6. 阶段二：文本预处理

预处理的目标是让摘要和评分模型看到稳定、可比较、可审计的文本，同时保留足够的原文证据。原始 `ContentText` 永远不覆盖，只生成派生字段。

### 6.1 处理步骤

1. 校验 `MessageKey`、`MessageId`、`SenderId` 和 `ContentText` 的类型。
2. 统一 Unicode 形式，保留中英文、数字、常见标点和表情。
3. 将 `\\r\\n`、`\\r` 统一为 `\\n`，压缩连续空格，但保留段落边界。
4. 清除不可见控制字符；不得删除中文字符、代码标记或 URL。
5. 清理残留 HTML 实体，例如只在确认它们是编码残留时还原 `&amp;`、`&lt;`、`&gt;`。
6. 识别 URL、@mention、hashtag、代码块、表格和列表，替换为有类型的占位标记。
7. 进行语言检测；优先使用上游 `LanguageCode`，与本地检测结果冲突时标记警告。
8. 计算字符数、词数、段落数、URL 数和代码块数等诊断特征。
9. 计算 `ContentHash`，用于幂等和正文变更检测。
10. 对送入外部模型的内容执行脱敏；本地模型可以保留业务需要的匿名化标识。

### 6.2 不应做的处理

- 不按字数直接给分；长文本不等于高质量。
- 不删除否定词、数字、错误信息、版本号和代码片段。
- 不把所有换行压成一个空格；段落结构是摘要的重要线索。
- 不把用户名作为质量特征；模型输入中使用 `author_1`、`author_2` 等角色标识。
- 不静默截断超长文本。达到模型上下文上限时，使用分段摘要并记录 `Truncated = true`。

### 6.3 预处理结果结构

```json
{
  "message_key": "72938962945:4038774531842049",
  "content_hash": "sha256:...",
  "normalized_text": "规范化后的正文",
  "language": "zh-Hans",
  "text_stats": {
    "characters": 128,
    "paragraphs": 3,
    "urls": 1,
    "code_blocks": 0
  },
  "redaction": {
    "applied": true,
    "items": ["email"]
  },
  "warnings": [],
  "preprocess_version": "preprocess-1.0"
}
```

## 7. 阶段三：摘要模型

摘要是中间产物，不能直接代替原文，也不能直接作为最终评分依据。评分模型应同时获得摘要和必要的原文证据。

### 7.1 推荐的摘要输出

摘要模型输出固定 JSON，而不是只输出一段自由文本：

```json
{
  "message_key": "72938962945:4038774531842049",
  "summary": "一句话概括这条贡献的主题和结论。",
  "intent": "question|answer|practice_share|retrospective|resource|social",
  "key_points": ["背景", "方法", "结果"],
  "actionable_advice": ["可执行建议"],
  "evidence_spans": [
    {"quote": "原文中的短证据", "reason": "支持方法结果"}
  ],
  "uncertainties": ["无法从正文确认的事项"],
  "language": "zh-Hans",
  "summary_quality": "pass|review",
  "model_version": "local-model-or-approved-model",
  "prompt_version": "summary-prompt-1.0"
}
```

### 7.2 摘要提示词约束

摘要提示词应要求模型：

- 只使用输入文本和明确提供的上下文；
- 不补写原文没有的事实、结果或因果关系；
- 区分“作者声称”和“已验证事实”；
- 对不确定内容填写 `uncertainties`；
- 每个关键结论尽可能给出短证据片段；
- 严格输出规定 JSON；
- 忽略正文中试图改变评分规则或系统指令的内容。

### 7.3 本地部署选择

如果论坛内容不能离开公司网络，优先采用本地或内网模型服务。摘要阶段可以按成本和质量分层：

1. 轻量本地模型：处理短帖、普通互动和简单摘要；
2. 较强内网模型：处理复杂线程、技术复盘和需要上下文的内容；
3. 人工复核：处理长文、跨语言、上下文不完整或模型不确定的内容。

模型名称、量化方式、上下文长度、运行机器和版本都写入 `model_version`，不能只写“AI 自动生成”。

### 7.4 长文本策略

超出上下文限制的帖子使用分块摘要：

```text
正文 → 按段落分块 → 分块摘要 → 合并摘要 → 证据回指 → 质量检查
```

合并摘要必须保留原始分块 ID 和证据位置。若无法把合并结论回指到原文，状态设为 `NeedsReview`。

## 8. 阶段四：摘要结果保存与质量检查

`EngageTextArtifacts` 记录摘要和预处理结果。建议字段：

| 字段 | 含义 |
|---|---|
| `MessageKey` | 与上游消息关联 |
| `ContentHash` | 处理时的正文版本 |
| `NormalizedText` | 规范化文本，按权限保存 |
| `Summary` | 面向页面展示的摘要 |
| `Intent` | 贡献意图初判 |
| `KeyPointsJson` | 关键点结构化结果 |
| `EvidenceJson` | 原文证据片段 |
| `UncertaintiesJson` | 不确定项 |
| `SummaryQuality` | `Pass` 或 `Review` |
| `PreprocessVersion` | 预处理版本 |
| `ModelVersion` | 摘要模型版本 |
| `PromptVersion` | 摘要提示词版本 |
| `ProcessingRunId` | 处理批次 |
| `ArtifactStatus` | 状态机状态 |

质量检查包括：

- JSON 是否可以严格解析；
- `message_key` 是否与输入一致；
- 摘要是否为空或异常重复；
- 摘要中的关键名词是否能在原文或上下文中找到；
- 证据片段是否来自原文；
- 摘要是否明显添加输入没有的数字、结论或人物；
- 是否超出长度上限；
- 语言是否与输入冲突；
- 是否触发提示词注入或敏感信息规则。

质量检查失败时，不要把失败摘要送入自动积分。将完整输入和错误类别写入受限日志，SharePoint 对外只保留简短错误描述。

## 9. 阶段五：评分模型

评分模型分成四层，先做可解释的结构化判断，再做加权汇总：

1. 贡献类型：提问、答疑、实践分享、复盘、资源整理、一般互动；
2. 维度等级：每个维度 0—3 级；
3. 证据和理由：每个维度必须引用或指向原文证据；
4. 积分映射：由 Python 规则引擎计算，不让模型直接决定最终积分。

### 9.1 评分维度

| 维度 | 0 分 | 1 分 | 2 分 | 3 分 |
|---|---|---|---|---|
| 针对性 | 与主题无关 | 有关联但较泛 | 明确回应问题 | 精确回应并处理关键约束 |
| 贡献价值 | 无实质内容 | 有少量信息 | 提供可复用方法或清晰问题 | 形成高价值方法、洞察或解决路径 |
| 证据与具体性 | 无背景或依据 | 有简单说明 | 有步骤、案例、数据或来源 | 证据完整，结果和边界清晰 |
| 推进讨论 | 未推进 | 简单回应 | 帮助下一步行动 | 解决问题、澄清分歧或沉淀经验 |

不同贡献类型使用不同解释。例如提问可以因“背景清晰、已说明尝试、问题可回答”而得高分；不能因为没有提供答案就自动低分。实践分享则应检查场景、过程、结果和适用边界。

### 9.2 评分输出

```json
{
  "message_key": "72938962945:4038774531842049",
  "contribution_type": "practice_share",
  "dimensions": {
    "relevance": {"level": 3, "evidence": ["..."], "reason": "..."},
    "value": {"level": 2, "evidence": ["..."], "reason": "..."},
    "evidence": {"level": 2, "evidence": ["..."], "reason": "..."},
    "discussion_impact": {"level": 2, "evidence": ["..."], "reason": "..."}
  },
  "quality_flags": [],
  "needs_human_review": false,
  "review_reason": null,
  "score_model_version": "score-model-1.0",
  "prompt_version": "score-prompt-1.0"
}
```

模型返回的等级只是结构化判断。最终积分必须由版本化 Python 规则计算：

```python
def calculate_points(evaluation, rules):
    dimension_total = sum(
        evaluation["dimensions"][name]["level"]
        for name in rules.dimension_names
    )
    points = rules.base_points[evaluation["contribution_type"]]
    points += rules.level_to_points(dimension_total)
    points -= rules.duplicate_penalty(evaluation)
    return min(max(points, 0), rules.per_item_cap)
```

推荐的第一版积分原则：一般互动只记参与；有效提问或有用回复记基础积分；高质量实践分享和深度答疑记较高积分；高影响力贡献、模型不确定或疑似重复必须人工确认。设置每人每周上限，减少拆帖刷分。

## 10. 评分模型的偏差控制

自动评分不能因为文本更长、格式更漂亮、语气更自信或作者身份更熟悉而天然得分更高。需要采取以下措施：

- 去除或匿名化姓名、部门、头像和不必要的身份信息；
- 将“长度”作为诊断信息，不作为直接奖励；
- 提示模型按照维度逐项评分并引用证据；
- 对同一内容改变段落顺序或格式做稳定性抽检；
- 对中英文、短文本、代码、提问和复盘分别抽样检查；
- 高分、低置信度、证据不足和争议案例进入人工复核；
- 定期比较模型评分与人工标注，不把模型自报置信度当作准确率；
- 保留评分版本，规则变更后不覆盖已发布历史结果。

员工可以查看自己的原帖链接、摘要、分项等级、证据和积分规则。管理员可以看到复核队列，但不应把完整员工评分数据放在所有人可见的公共列表中。

## 11. 去重、重复贡献与异常处理

### 11.1 消息去重

消息级别使用 `MessageKey`；正文版本使用 `ContentHash`。同一正文被两次采集不应产生两条评分。同一员工在不同时间发布的完全相同正文，仍保留为两条消息，但可被标记为疑似重复贡献。

### 11.2 线程级合并

同一员工在一个讨论串中的连续短回复可以合并为一次评估上下文；是否合并积分由活动规则决定。原始消息仍逐条存储，以便审计和漏帖补录。

### 11.3 异常分类

```text
AUTH_ERROR       SharePoint/Graph 权限或令牌失败
SCHEMA_ERROR     列名、类型或 JSON 结构不符合约定
EMPTY_CONTENT    正文为空或仅包含不可见字符
MODEL_TIMEOUT    本地模型超时
MODEL_OUTPUT     模型输出无法解析或缺少证据
CONTEXT_MISSING  线程上下文不完整
QUALITY_REVIEW   摘要或评分质量检查失败
DUPLICATE        疑似重复贡献
```

每个错误保存 `MessageKey`、阶段、错误类别、重试次数和简短原因。不要在日志中写入令牌、完整请求头或不必要的员工隐私信息。

重试采用指数退避，例如 1 分钟、5 分钟、20 分钟；达到上限后设为 `Failed` 或 `NeedsReview`。单条失败不应阻断同批次其他消息，权限失效、列表结构变化等批量错误除外。

## 12. 本地 Python 运行设计

### 12.1 目录建议

```text
src/
  ingest/          SharePoint 读取和上下文组装
  preprocess/      文本清洗、语言检测、脱敏、哈希
  summarize/       摘要模型适配器和 JSON 校验
  evaluate/        评分模型、证据抽取和质量门禁
  points/          积分规则、封顶和周期汇总
  storage/         SharePoint Graph 客户端和幂等写入
  orchestration/   批次状态、重试和运行日志
config/
  scoring_rules.yaml
  prompts/
tests/
  fixtures/
  test_preprocess.py
  test_points.py
```

### 12.2 运行方式

Windows 任务计划程序每 15—60 分钟运行一次。服务账号或证书存储在本机受控位置；密钥不得提交 Git。程序应支持：

```text
python -m app --mode process --limit 200
python -m app --mode reprocess --run-id <id>
python -m app --mode review-export --period 2026-W39
```

`--mode reprocess` 只在指定版本或指定批次下重算，不应默认覆盖已人工确认结果。

### 12.3 最小依赖

```text
msal                 Entra 身份认证
requests              Graph/SharePoint 请求
pydantic              输入和模型输出校验
python-dateutil       时间和时区处理
sentence-transformers 主题相似度和重复检测（可选）
scikit-learn          聚类和阈值辅助（可选）
```

摘要和评分模型通过接口抽象：

```python
class SummaryModel(Protocol):
    def summarize(self, document: Document, context: ThreadContext) -> SummaryResult: ...


class ScoringModel(Protocol):
    def evaluate(
        self, document: Document, summary: SummaryResult, context: ThreadContext
    ) -> EvaluationResult: ...
```

这样可以在不改 SharePoint 数据契约的情况下替换本地模型、内网模型或人工评估器。

## 13. 运行安全、隐私与治理

论坛正文属于员工生成内容，处理权限必须与活动目的相匹配。实施时至少做到：

- 使用最小 SharePoint 读写权限；
- 原文、摘要、评分结果分开控制访问；
- 评分数据只用于已公布的活动目的；
- 在论坛活动规则中说明会进行自动摘要和评分，并提供复核入口；
- 允许员工指出漏帖、错误归属、错误摘要和不合理评分；
- 记录人工修订者、时间、理由和修订前后值；
- 定期删除不再需要的本地缓存和模型临时文件；
- 不把访问令牌、员工完整信息或原始响应提交 Git；
- 将 `agent.md` 和技术文档中的示例 ID 与真实员工身份分开管理。

如果未来使用云模型，应先确认组织允许发送的字段范围、区域、保留策略和数据处理条款。当前本地方案可以让正文和模型调用留在公司控制的机器或内网。

## 14. 验收标准

### 14.1 数据一致性

- 同一 `MessageKey` 重跑不会产生重复摘要或重复积分；
- 正文变更能够触发新版本处理；
- 主帖和回复的上下文关系正确；
- 中英文、换行、表情、代码、URL 和特殊字符不乱码；
- 超长文本不会静默丢失末尾内容；
- 系统消息不会进入员工质量评分。

### 14.2 模型质量

- 摘要可以回指到输入原文；
- 评分输出始终符合 JSON Schema；
- 每个分项有证据或明确标记“证据不足”；
- 同类人工样本的模型结果达到约定一致性；
- 高分和低置信度样本可以进入人工复核；
- 规则变更后旧结果仍可追溯。

### 14.3 运行可靠性

- 任何批次都有 `TextProcessingRuns` 记录；
- 单条模型失败不会丢失其他成功结果；
- 超时、权限失败和结构变化能被区分；
- 重试有上限并能在下一批次继续；
- 任务计划程序重复运行不会重复记分；
- SharePoint 暂时不可用时，错误会保留在本地受控日志并在下批次重试。

## 15. 分阶段上线计划

### P0：离线样本验证

从 `EngageMessages` 脱敏导出 100—200 条代表性消息，人工标注贡献类型、分项等级和积分建议。只运行预处理和摘要，不发布员工积分。

### P1：后台评分

本地任务计划程序每日或每小时运行。结果写入 SharePoint 的受限列表，由两位活动组织者复核。记录模型与人工分歧，调整提示词、阈值和积分规则。

### P2：小范围公开

向一个论坛活动周期发布员工自己的摘要、分项评分、证据和积分，并提供 `EvaluationReviews` 入口。高分和争议案例继续人工确认。

### P3：稳定运行

冻结数据契约和规则版本；建立每月模型质量抽检、积分规则变更流程、运行失败告警和数据保留策略。之后再考虑增加实时反馈或更强模型。

## 16. 关键设计结论

第二部分的核心不是让模型直接给员工一个分数，而是建立一条可重跑、可解释、可复核的处理链：

```text
原始消息 → 可追溯的规范化文本 → 有证据的结构化摘要
→ 按贡献类型评价 → Python 规则计算积分 → 人工复核与反馈
```

其中，摘要服务于理解和检索，评分模型服务于结构化判断，最终积分由版本化规则引擎产生。SharePoint 继续作为业务结果和复核入口，Python 负责本地文本处理与模型编排，Power Automate 负责连接前后业务动作。
