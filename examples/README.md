# 示例数据集（匿名化）

新增素材见 [FORVIA模拟素材与合并验证集](forvia_materials/README.md)：50条模拟消息与本目录12条样例合并为62条，附阅读版、来源标识和作者设计的验证重点。

量化评分卡的新实跑结果见 [quant_validation](quant_validation/README.md)，完整效果报告与流程图见 [PART2_SCORECARD_VALIDATION.md](../PART2_SCORECARD_VALIDATION.md)。

全部62条正文的轻量TF-IDF＋Ridge候选分及其特征贡献见 [PART2_SIMPLE_MODEL_ALL_MESSAGES.md](../PART2_SIMPLE_MODEL_ALL_MESSAGES.md)，机器可读结果在 [simple_score_results](simple_score_results/)。

本目录是一套可入库的示例数据，用于在不接 SharePoint 的情况下演示/验证 PART2 评分流水线（`poc/`）。

## 内容

| 文件 | 说明 |
|---|---|
| `EngageMessages_sample.csv` | 匿名化示例数据，12 条消息，schema 与 `EngageMessages` 列表导出一致 |
| `run_output/artifact_*.json` | 逐条评分产物：规则后端（无后缀）与 ML 后端（`_ml` 后缀）各 12 条 |
| `run_output/summary_table_rules.csv` / `summary_table_ml.csv` | 两个后端的明细表（总积分 71，示例值不发布） |
| `run_output/models/` | 弱监督 ML 模型（LogReg+Ridge，joblib）及元数据，供 `--model ml` 复现 |

## 数据来源与匿名化

源数据 = 2026-09-22 `EngageMessages` 列表导出（12 条：11 条测试帖 + 1 条真实观点帖）。
按 `PART2_POC_REPORT.md` §5.2 的口径匿名化后入库（agent.md 治理要求：员工数据不进 Git）：

- 姓名：真实姓名 → `服务账号` / `员工B`；`SenderId` 同步重映射为 `900000000000x`（同一发送者固定）；
- 消息 ID：`MessageId`/`ThreadId`/`ReplyToId`/`MessageKey` 按首次出现顺序重映射为 `400000000000x`，回复/线程引用关系保持不变；
- `NetworkId`/`GroupId`/`LastRunId`：固定占位值；
- `SourceUrl`：替换为 `https://engage.example.invalid/threads/<id>`（原 URL 含租户与真实线程令牌）；
- 正文与时间戳保留原样（内容不指向个人，作者已匿名化）。

生成脚本 `tools/make_example_dataset.py` 自带防泄漏校验（输出中不得残留任何原始姓名/ID/租户 URL），对新导出可复用。

## 复现

```bash
# 规则后端（零依赖）
PYTHONUTF8=1 python -m poc.run_poc examples/EngageMessages_sample.csv
# ML 后端（需先落模型文件）
cp examples/run_output/models/* poc_output/models/
PYTHONUTF8=1 python -m poc.run_poc examples/EngageMessages_sample.csv --model ml
```

输出写入 `poc_output/`（已 gitignore）。`run_output/` 是 2026-09-28 在示例数据上的预生成结果：
F1–F7 可行性检查单全部通过，规则与 ML 后端类型一致 12/12、积分平均差 0.0。
