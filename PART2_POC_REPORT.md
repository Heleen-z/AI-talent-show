# 第二部分 POC 可行性验证报告

文档版本：1.0
日期：2026-09-22
验证范围：PART2 文本处理、摘要与评分流水线的本地可行性（不依赖 LLM 端点）
结论速览：**工程链路全部验证通过（F1–F7）；未验证项仅剩模型端点与内容质量，二者均以「可替换接口 + 人工标注」解耦，不阻塞结论。**

## 1. 验证目标

在不接入任何 LLM 的前提下，回答三个可行性问题：

1. 流水线骨架（预处理 → 摘要 → 评分 → 积分 → 质量门禁）能否端到端跑通；
2. PART2 各章节的关键机制（幂等、上下文、证据回指、复核通道、积分封顶、重复检测）是否成立；
3. 用简单机器学习模型替换规则实现后，训练 → 持久化 → 推理的模型工程链路是否成立。

## 2. 上游数据摸底（2026-09-22）

### 2.1 已确认

- 站点：`https://faurecia.sharepoint.com/sites/AIPortal`
- `EngageMessages` 列表 GUID：`5e2b2ce2-5833-43ef-b65c-5fb1be918512`（来源：Excel 导出 `.iqy` 中的 `SharePointListName`）
- 23 列结构与 agent.md 字段映射完全一致，分组如下：

| 分组 | 字段 |
|---|---|
| 主键/关联 | MessageKey、MessageId、NetworkId、GroupId、GroupName、ThreadId、ReplyToId |
| 作者 | SenderId、SenderName |
| 正文 | Title、ContentText、LanguageCode |
| 时间 | PostedAt、PublishedAt、FirstCapturedAt、LastSeenAt、TextChangedAt |
| 标志 | IsRootPost、IsSystemMessage、Privacy、MessageType |
| 溯源 | SourceUrl、LastRunId |

- 数据画像：12 条 = 9 条验收测试帖（TC02–TC10）+ 2 条早期测试 + 1 条真实帖（个人账号发布）
- 采集验证通过：幂等（同 MessageKey 唯一）、回复关系（ThreadId/ReplyToId 正确）、超长文本（3000+ 字完整）、特殊字符/emoji/JSON 引号完好
- **每日采集流程已实际运行**：LastSeenAt 为当日，全表同一 LastRunId，说明全量复查生效（状态比 agent.md 2026-09-20 版「云端联调待执行」更新）

### 2.2 遗留问题

| 问题 | 影响 | 待办 |
|---|---|---|
| PostedAt 等时间列疑似 Date Only（无时分秒） | PART2 活动周期、时效、时区计算 | Graph 直读核实；若确认需改列类型 |
| Title 是 ContentText 的截断副本 | 分析不得使用 Title 当正文 | 无需修复，使用约定 |
| PART2 所需 ScoringStatus / LastProcessedAt / PipelineVersion 列未建 | 增量取数依赖这些字段 | 进入 P1 前在列表加列 |
| EngageSyncRuns 结构未读取 | 上游批次状态检查（§2.1）暂缺 | Graph 登录后用 `tools/read_list_schema.py` 补齐 |

## 3. POC 实现（`poc/` 目录）

| 模块 | 职责 | 方法 |
|---|---|---|
| `preprocess.py` | 规范化、占位符、语言检测、统计特征、ContentHash | 规则（确定性，符合 §6） |
| `baseline.py` | 线程上下文（§5.2）、抽取式摘要、规则评分、积分引擎、质量门禁 | TF-IDF + 余弦相似度（无监督）+ 规则 |
| `features.py` | 文本 TF-IDF 特征 + 12 维数值统计特征 | sklearn |
| `train.py` | 弱监督训练：类型分类器 + 4 维度回归器，LOOCV 评估，joblib 持久化（含版本元数据） | LogisticRegression + Ridge |
| `ml_model.py` | ML 推理后端，与规则后端同签名 `evaluate(message, summary, ctx)` | 可替换接口（§12.3） |
| `run_poc.py` | 端到端入口 + F1–F7 可行性检查单 | — |

复现命令（项目根目录）：

```bash
PYTHONUTF8=1 python -m poc.run_poc                 # 规则后端（零额外依赖）
PYTHONUTF8=1 python -m poc.train                   # 训练弱监督模型
PYTHONUTF8=1 python -m poc.run_poc --model ml      # ML 后端 + 与规则基线对比
```

## 4. 评分机制 v0.1（`scoring-rules-0.1`）

### 4.1 贡献类型判定（优先级从上到下，命中即停）

| 优先级 | 条件 | 判为 |
|---|---|---|
| 1 | 前 300 字含疑问标记（?？/怎么/如何/求助/吗/能不能） | question |
| 2 | 回复 且（含建议/方法/步骤/解决/应该/参考 或 有代码块） | answer |
| 2b | 回复 且不满足上条 | social |
| 3 | URL ≥ 2 | resource |
| 4 | 含 我们/实践/落地/项目/效果/复盘/总结/搭建/部署 或 有代码块 | practice_share |
| 5 | 正文 < 30 字 | social |
| 6 | 兜底：≥ 30 字的主帖 | practice_share |

### 4.2 四维度分级（0–3）

| 维度 | 规则 |
|---|---|
| relevance | 回复：与父帖关键词重合 ≥25% → L3，否则 L2；主帖一律 L2 |
| value | ≥500 字或含代码块 → L3；≥100 → L2；≥30 → L1；<30 → L0 |
| evidence | 4 信号计数（数字/步骤词/URL/代码块），级别 = min(3, 计数) |
| discussion_impact | answer 且有可执行建议 → L3；question/share/resource 且 ≥100 字 → L2；其余 L1 |

### 4.3 积分与门禁

```text
积分 = 基础分[类型] + 四维总和(0–12)，单项封顶 10
基础分：social 1 / question 2 / answer 3 / resource 4 / practice_share 5
同作者同 ContentHash 出现 2 次以上 → 该组全部清零（疑似重复）
质量门禁不过（JSON/键一致/证据回指失败）→ 清零
```

## 5. 运行结果（12 条全量）

### 5.1 可行性检查单

| 检查项 | 结果 |
|---|---|
| F1 端到端流水线 | 12/12 |
| F2 证据可回指原文（§8 门禁） | 12/12 |
| F3 重复检测（§11.1） | 两对同正文帖（4 条）全部清零 |
| F4 NeedsReview 通道（§4） | 4 条进入复核（语言检测冲突触发） |
| F5 积分封顶 | 生效（7 条触发） |
| F6 员工聚合 | 服务账号 61 / 员工B 10 |
| F7 ML vs 规则一致性 | 类型 12/12，积分平均差 0.0 |

### 5.2 逐条结果（作者匿名化）

| 消息 | 作者 | 类型 | r/v/e/i | 积分 | 标记 |
|---|---|---|---|---|---|
| Hello World（23 字） | 服务账号 | social | 2/0/1/1 | 5 | — |
| `9/18 test`（9/18 首发） | 服务账号 | social | 2/0/1/1 | 0 | 疑似重复 |
| `9/18 test`（9/20 重发） | 服务账号 | social | 2/0/1/1 | 0 | 疑似重复 |
| 行业动态观点帖（105 字，唯一真实帖） | 员工B | practice_share | 2/2/1/2 | 10 | 12 分封顶 |
| TC02 中英混合 | 服务账号 | practice_share | 2/2/2/2 | 10 | — |
| TC03 换行保留 | 服务账号 | practice_share | 2/1/2/1 | 10 | — |
| TC04 特殊字符 | 服务账号 | practice_share | 2/2/1/2 | 10 | — |
| TC05 超长文本（1905 字） | 服务账号 | practice_share | 2/3/1/2 | 10 | — |
| TC06 空白行 | 服务账号 | practice_share | 2/1/1/1 | 10 | 复核（语言冲突） |
| TC07 重复帖 ×2 | 服务账号 | practice_share | 2/1/2/1 | 0 | 疑似重复 + 复核 |
| TC10 回复测试 | 服务账号 | social | 2/1/1/1 | 6 | 复核（语言冲突） |

总积分 71（示例，未发布）。需复核的 4 条均为中英混排触发语言检测警告（detected=en vs 上游 zh-Hans），属 §4 设计的「语言检测不确定」触发路径，非缺陷。

## 6. ML 模拟链路（无 LLM 的机器学习实现）

- **弱监督训练**：无人工标注，以规则基线输出为弱标签。LogisticRegression（类型）+ 4×Ridge（维度），特征 = TF-IDF（jieba 分词）+ 12 维统计特征（字数/段落/URL/代码块/是否回复/句式暗示等）
- **评估**：LOOCV（12 条样本下唯一可信方式）——类型准确率 83%，维度 MAE 0.00–0.58
- **模型工程**：joblib 持久化，bundle 含 model_version / features_version / weak_label_source / trained_at / n_samples / metrics，满足 §7.3「版本可追溯」要求
- **推理后端**：`SklearnBackend.evaluate` 与规则后端同签名；类型置信度 < 0.45 自动进 NeedsReview（§4 模型触发通道，本批未触发——训练集内样本置信度 0.65–1.00）
- **替换路径**：将来 LLM 或微调模型实现同签名类即可，流水线其余部分零改动

### 6.1 端到端轨迹示例（真实帖，节选）

```text
【原始文本】行业动态观点帖（105 字，1 句）
【预处理】  hash=sha256:2f8533c7…，zh-Hans，105 字/74 词/1 段/0 URL/0 代码块
【摘要】    TF-IDF 主题句 = 原句（单句帖抽取式摘要 ≈ 复制，见局限）
【评分】    practice_share (p=0.877)；r2/v2/e1/i2，依据=字数 105、实践暗示词
【积分】    5 + 7 = 12 → 封顶 10
```

## 7. 结论与局限

### 已验证

1. 工程链路完整成立：预处理 → 上下文 → 摘要 → 评分 → 积分 → 门禁 → 复核，全部可跑、可追溯、可重跑；
2. PART2 关键机制成立：幂等键、证据回指门禁、重复清零、积分封顶、语言冲突复核、员工聚合；
3. 模型工程链路成立：训练 → 持久化（版本化）→ 加载推理 → 置信度触发复核，且评分后端可替换。

### 局限（诚实声明）

1. **无人工标注**：规则是启发式，ML 是弱监督（学的是规则输出）——评分反映表面特征（长度/格式/关键词），不反映内容价值，**不可用于发布积分**（符合 PART2 P1 前须人工复核的约定）；
2. **环形验证**：F7 的 12/12 一致是训练集记忆，LOOCV 83% 才是泛化参考；
3. **类别缺失**：12 条中无 question/answer 样本，两分支从未触发；8/12 的类型走兜底分支；relevance 维度恒为 L2；
4. **抽取式摘要天花板**：只能挑原句，不能压缩改写，单句帖摘要≈原文。

### 未验证项（均不阻塞可行性结论）

- 模型端点连通性（公司 API 或本地 Ollama/Qwen）——接口已隔离，接入即换；
- 评分质量与人工一致性（§14.2）——需 P0 标注后评估。

## 8. 下一步

| 优先级 | 事项 | 依赖 |
|---|---|---|
| 高 | P0 人工标注 100–200 条真实帖（贡献类型/四维等级/积分建议） | 社区真实内容积累 |
| 高 | 核实时间列精度；EngageSyncRuns 结构补读 | Graph 登录一次 |
| 中 | 模型端点接入，同签名后端替换，与基线对比 | 端点可用 |
| 中 | 进入 P1 前为 EngageMessages 加 ScoringStatus 等三列 | SharePoint 管理操作 |

## 附录：治理与数据安全

- `data/`（员工数据）与 `poc_output/`（运行产物、模型）已加入 `.gitignore`，不入库；
- 本报告作者匿名化（服务账号/员工B），不出现个人姓名；
- Graph 探测脚本 `tools/read_list_schema.py` 使用设备码流程，token 缓存于用户目录，不进仓库；
- 所有积分为示例输出，未发布、未写入 SharePoint。
