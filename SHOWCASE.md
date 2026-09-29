# 公司电脑展示说明

## 1. 获取项目

首次获取（需要有仓库访问权限）：

```powershell
git clone https://github.com/Heleen-z/AI-talent-show.git
cd AI-talent-show
```

已有副本：在仓库目录执行 `git pull --ff-only origin main`。若本地有修改或分支分叉，先保留修改再处理，不使用强制覆盖命令。

## 2. 打开汇报

双击根目录的 `打开项目汇报.cmd`；或者直接用 Edge / Chrome 打开 `docs/AITALENTSHOW_FEASIBILITY_REPORT.html`。

页面已内嵌三张结构图，不依赖网络、Python 或服务器。图下“单独打开结构图”可打开对应SVG放大查看。页面提供“打印 / 另存为 PDF”。HTML、SVG及Markdown之间使用相对链接，保持目录结构即可。

建议展示顺序：核心结论 → 第2节整体结构图 → 第6节一条消息完整流转 → 第5节实测结果 → 第8至9节缺口与实施方案。第3节提供具体文件流转表，用于回答实现细节问题。

## 3. 500字以内项目介绍

AI Talent Show的流程为：论坛记录→本地评分→人工复核→积分汇总→排行榜展示。

记录方面，Power Automate按设计每日读取Viva Engage主帖与回复，写入EngageMessages和采集日志。项目已有12条匿名化抓取样例，当前云端运行状态仍需现场核验。

评分方面，Python清洗CSV正文，通过TF-IDF＋Ridge生成0—10候选分，输出模型、评分明细和验证报告。62条实验数据包含50条模拟内容；分组验证MAE为0.937分，均值基线为0.980分。标签来自规则评分卡，尚未证明真实贡献评分有效。

排名方面，代码已实现按员工汇总周、月、年积分及排序。候选分经人工确认后，计划进入ActivityPoints，汇总写入LeaderboardTotals，再由Power Apps展示。独立新帖推理、复核写回和页面联调尚未完成。

本地计算可行，13项现有测试通过；正式发布闭环仍待完成。

## 4. 可选：运行本地实验

仅展示报告无需执行本节。若需要演示计算，请提前准备Python与依赖，先在公司电脑完整运行一次；本机历史复验使用Python 3.12.9，其他环境应实际验证。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m poc.simple_score
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

默认使用仓库内62条实验样例，输出到本地 `poc_output/simple_score/`。当前命令每次训练，对没有标签的记录会过滤，不是生产新帖推理服务；不会写回SharePoint或发布员工积分。

不运行也可查看 `examples/simple_score_results/report.json`、`scores.csv` 和 `PART2_SIMPLE_MODEL_ALL_MESSAGES.md` 中已保存的实验结果。加载joblib模型前应确认其来自可信项目版本。

`data/`、`poc_output/`及`.venv/`是忽略目录，不随Git同步。仓库不包含公司云端连接凭据，拉取不会自动部署Power Automate、SharePoint或Power Apps。

## 5. 更新汇报文件

修改文字稿后，在项目目录执行以下命令可重新生成HTML与三张SVG；生成脚本仅需Python标准库：

```powershell
python tools/build_feasibility_report.py
```

图的节点与布局定义位于该脚本中；若流程变化，应同步修改图定义。
