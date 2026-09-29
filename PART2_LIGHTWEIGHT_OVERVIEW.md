# 第二部分：本地轻量文本评分流程

当前主线为TF-IDF＋Ridge，用于AI论坛活动积分与培训反馈。总架构见 [README](README.md)，完整设计与操作细节仍保留在 [原第二部分指南](PART2_TEXT_PIPELINE.md)。本概览是补充文档，不替代各部分指导文档。

## 1. 输入

从第一部分的SharePoint `EngageMessages` 导出CSV，本地Python不重新抓取Viva Engage。

| 字段 | 用途 |
|---|---|
| MessageKey | 唯一关联键：NetworkId:MessageId |
| ContentText | 模型唯一文本输入；保留原文 |
| MessageId / ThreadId / NetworkId | 字符串标识，讨论串分组验证 |
| SenderId / SenderName | 归属与展示，不进入模型 |
| PostedAt / SourceUrl | 后续积分周期与原帖复核 |
| DataOrigin / IsSynthetic | 实验来源区分，不进入模型 |

现有样本共62条：12条匿名化抓取样例（11条测试帖、1条观点帖）和50条模拟素材。正式运行还需检查采集批次完整性、排除系统消息和校验字段；当前训练脚本并未实现全部生产入口校验。

## 2. 本地训练与验证

```text
已评分正文 → 清洗 → 按讨论串与完全重复正文分组
                    ↓
        每折独立训练TF-IDF＋Ridge → 误差与均值基线
                    ↓
        全量训练 → 保存模型 → 当前样本回代分数与特征贡献
```

入口为 `poc/simple_score.py`。字符TF-IDF取2—4字符组合、最多5000特征；Ridge固定alpha=1，单线程数值计算，预测截断至0—10。正文直接进入模型，摘要和类型识别不再是前置步骤。

未提供人工标签时，目标分取自 `examples/quant_validation/artifacts_scorecard.json` 的四维等级之和 × 10/12，不含重复惩罚。`--labels`可改用MessageKey和HumanScore。当前仅处理有匹配标签的行，每次运行重新训练；独立的新帖推理入口尚待实现。

## 3. 输出与解释

| 文件 | 内容 |
|---|---|
| model.joblib | 词表、IDF、回归模型、版本与标签来源 |
| scores.csv | 消息键、目标分、验证分、回代分、特征贡献与来源 |
| report.json | 样本数、误差、耗时与模型大小 |

`FittedScore`为当前样本回代候选分，`OutOfFoldScore`用于检查组外预测误差。正负特征贡献说明模型如何算分，不是事实核验或语义质量证明。结果为Experimental状态。

`tools/make_simple_score_report.py`将评分与原文关联，生成 [逐条技术文档](PART2_SIMPLE_MODEL_ALL_MESSAGES.md)。已保存的样例结果位于 `examples/simple_score_results/`；默认实验输出写入被Git忽略的 `poc_output/simple_score/`。

## 4. 后续发布接口

日常流程应是：加载已确认版本模型→预测新帖→复核和业务规则→最终积分。不需要每来一条消息就重新训练。

发布适配层至少需要MessageKey、SenderId、PostedAt、CandidateScore、FinalPoints、ScoringStatus、IsDuplicate、IsCurrentVersion、ModelVersion、RuleVersion与运行ID。候选分转换为最终积分的取整规则仍需统一实现。

排行榜接收显式批准/发布的最终积分，不直接接收Experimental预测。当前聚合函数对缺失状态有宽松默认值；CSV中的True/False文本也必须转换成真正布尔值再传入。周期函数当前按UTC计算，若活动按北京时间计周/月，上线前还需统一口径。

SharePoint使用一个积分事实来源ActivityPoints；仅当其审计能力不足时补建PointsLedger。复核、写回及Power Apps仍待实现/联调。

## 5. 验证与下一阶段

本地轻量运行已通过验证，对既有弱标签的MAE约0.937，均值基线约0.980。当前差异不足以证明实际业务评分有效。

下一步先补少量人工分数并分析误差，再积累真实帖子与双人标注。10指标EDA及原评分卡留作诊断对照，不再是新帖评分的必经步骤。实现细节与运行命令见 [轻量模型报告](PART2_SIMPLE_MODEL_POC.md)。
