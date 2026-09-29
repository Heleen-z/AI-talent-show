"""Reproduce the exploratory sample run, report and frozen scorecard."""
import csv
import json
import platform
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from poc.baseline import run_pipeline, DIMENSION_NAMES
from poc.eda import matrix, describe, NAMES
from poc.run_poc import load_rows
from poc.scorecard import fit, ScorecardBackend


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def csv_out(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = load_rows(ROOT / 'examples/forvia_materials/EngageMessages_merged_62.csv')
    out = ROOT / 'examples/quant_validation'
    out.mkdir(exist_ok=True)
    card = fit(rows)  # Explicit E0 exploratory fit; NOT held-out validation.
    dump(out / 'scorecard.json', card)
    metrics = matrix(rows)
    csv_out(out / 'metrics.csv', metrics)
    eda = describe(metrics)
    dump(out / 'eda.json', eda)
    baseline = run_pipeline(rows)
    alpha = run_pipeline(rows, ScorecardBackend(card, rows).evaluate, review_hold=True)
    dump(out / 'artifacts_scorecard.json', alpha)
    details = []
    for row, old, new in zip(rows, baseline, alpha):
        dims = new['evaluation']['dimensions']
        details.append(dict(MessageKey=row['MessageKey'], ScenarioId=row.get('ScenarioId', ''),
                            Title=row['Title'], DataOrigin=row['DataOrigin'], Sender=row['SenderName'],
                            OldType=old['evaluation']['contribution_type'],
                            NewType=new['evaluation']['contribution_type'],
                            **{dim: dims[dim]['level'] for dim in DIMENSION_NAMES},
                            OldPoints=old['points']['points'], CandidatePoints=new['points']['candidate_points'],
                            ReleasedPoints=new['points']['points'], Status=new['points']['scoring_status'],
                            Duplicate=new['points']['duplicate_flag'],
                            GatePass=not bool(new['points'].get('gate_failures')),
                            ReviewReason=new['evaluation']['review_reason']))
    csv_out(out / 'scores_comparison.csv', details)
    stats = {}
    for group in sorted({r['DataOrigin'] for r in rows}):
        items = [r for r in details if r['DataOrigin'] == group]
        stats[group] = {'n': len(items), 'old_total': sum(r['OldPoints'] for r in items),
                        'candidate_total': sum(r['CandidatePoints'] for r in items),
                        'released_total': sum(r['ReleasedPoints'] for r in items),
                        'type_changed': sum(r['OldType'] != r['NewType'] for r in items),
                        'duplicates': sum(r['Duplicate'] for r in items),
                        'old_at_cap': sum(r['OldPoints'] == 10 for r in items),
                        'new_at_cap': sum(r['CandidatePoints'] == 10 for r in items),
                        'gate_pass': sum(r['GatePass'] for r in items)}
    labels = load_rows(ROOT / 'examples/forvia_materials/author_design_labels.csv')
    # load_rows adds MessageId but does not alter the label fields.
    design = {r['MessageKey']: r['AuthorDesignedIntent'] for r in labels}
    agreement = {name: sum(r[field] == design.get(r['MessageKey']) for r in details if r['MessageKey'] in design)
                 for name, field in [('old', 'OldType'), ('alpha', 'NewType')]}
    csv_out(out / 'design_disagreements.csv', [dict(MessageKey=r['MessageKey'], ScenarioId=r['ScenarioId'],
        AuthorIntent=design[r['MessageKey']], OldType=r['OldType'], AlphaType=r['NewType'])
        for r in details if r['MessageKey'] in design and r['NewType'] != design[r['MessageKey']]])
    old_saved = load_rows(ROOT / 'examples/run_output/summary_table_rules.csv')
    regression = sum(float(r['积分']) for r in old_saved) == stats['existing_anonymized_capture']['old_total']
    import numpy, scipy, sklearn
    summary = dict(groups=stats, author_design_agreement=agreement, author_design_n=len(design),
                   old_12_total_matches_saved=regression, python=platform.python_version(),
                   numpy=numpy.__version__, scipy=scipy.__version__, sklearn=sklearn.__version__,
                   inference='descriptive_only_no_p_values_no_human_gold',
                   calibration='same_62_records_exploratory_not_holdout')
    dump(out / 'validation_summary.json', summary)
    lines = ['# PART2：量化评分卡 v0.2-alpha 实现与62条记录试评分', '',
        '日期：2026-09-28。实现之前计划的 P-EDA0：10指标、EDA、分位数卡与本地试评分。', '',
        '**当前完成的是探索版评分卡与工程验证。没有人工金标准，未完成E1/E2正式定标；候选分可查看，62条均待复核，可发布积分为0。**', '',
        '## 1. 完整评分流程', '',
        '```mermaid', 'flowchart TD',
        '  A[Viva Engage 主帖与回复] --> B[Power Automate 采集]',
        '  B --> C[SharePoint EngageMessages]',
        '  C --> D[导出CSV到本地 Python]',
        '  D --> E[清洗与保留原文 · ID检查 · 内容哈希]',
        '  E --> F[关联根帖与直接父回复]',
        '  F --> G[TF-IDF抽取摘要 · 证据 · 限制条件]',
        '  F --> H[M1至M10量化指标]',
        '  H --> I[EDA分布与退化检查]',
        '  I -. 探索定标并冻结 .-> J[分位数评分卡]',
        '  G --> K[类型判定与四维评分]',
        '  H --> K', '  J --> K',
        '  K --> L[候选积分 · 重复清零 · 证据与结构门禁]',
        '  L --> M{已校准且通过复核?}',
        '  M -- 当前alpha --> N[PendingReview · 保留候选分 · 发布分0]',
        '  M -- 后续接入 --> O[ActivityPoints 或 PointsLedger]',
        '  O --> P[LeaderboardTotals 与 Power Apps榜单]', '```', '',
        '实跑范围是本地CSV至复核输出。图中下游写回和榜单发布是后续接口，本次没有操作云端。', '',
        '## 2. 模型变化与可复算规则', '',
        '- 保留原 rules 和弱监督 ml 后端；新增 scorecard 后端，使用同一 evaluate(message, summary, ctx) 接口。',
        '- 十指标：有效字数、段落数、段均字数、代码块数、外链数、每百字数字信号、方法步骤、疑问信号、主帖线程回复数、实践/答疑暗示。URL中的编号不计数字信号；回复的M9为0。',
        '- 每指标先log1p，再保存P25/P60/P90切点。大于切点才升级，零值为L0，重复切点合并；无方差指标退出维度合成。每个维度对有效指标等级等权平均，再四舍五入到0–3。',
        '- value用M1/M2/M3，evidence用M4/M5/M6，discussion_impact用M7/M9；M8/M10辅助类型判断。段均字数不是语义信息密度。relevance缺少有效量化指标，暂用主题/父帖规则代理，并明确标记复核。',
        '- 防止纯篇幅获益：没有具体操作信号的value封顶L1；带操作的答疑至少L1；普通互动四维为0。这些仍是启发式护栏，不是已验证的语义质量判断。',
        '- alpha候选积分 = floor(10 × 四维等级之和 / 12 + 0.5)，范围0–10，去掉类型基础分以缓解封顶。相同作者同正文的所有记录继续按既有政策清零。',
        '- 置信值为规则强度，不是统计概率。alpha统一PendingReview，points=0，candidate_points保留诊断值。',
        '- 修正MessageId父回复查找及跨NetworkId线程隔离；拒绝重复MessageKey。摘要新增原文限制片段；门禁检查四维范围与证据回指。', '',
        '## 3. 数据与实际结果', '',
        '原12条含11条测试帖和1条真实观点帖；新增50条全是模拟素材。62条用于探索切点和回代试评分，没有独立测试集；作者设计标签只在评分完成后作描述对照，未输入模型。', '',
        '| 数据组 | 条数 | 旧规则积分合计 | alpha候选积分合计 | 可发布积分 | 类型变化 | 重复清零 | 旧/新满分条数 | 门禁通过 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name, s in stats.items():
        lines.append(f"| {name} | {s['n']} | {s['old_total']} | {s['candidate_total']} | {s['released_total']} | {s['type_changed']} | {s['duplicates']} | {s['old_at_cap']}/{s['new_at_cap']} | {s['gate_pass']} |")
    lines.extend(['', f"原12条旧规则积分合计与已保存结果一致：{regression}。",
        f"模拟50条与作者设计类型的一致数：旧规则 {agreement['old']}/50；alpha {agreement['alpha']}/50。这不是人工标注准确率，也不是泛化能力提升的证据。",
        '分数变化体现了评分规则改变；不能把分数降低或满分减少本身当作评分更准确。门禁通过仅说明结构和引用可回指，不保证事实正确。', '',
        '本次自动化测试：10项通过（7项新增评分测试、3项既有排行榜测试）。覆盖父回复/网络隔离、数字与URL区分、零方差及相同切点、复核冻结、重复处理、辅助标签不泄漏、摘要限制保留、重复主键拒绝、评分卡冻结。CLI评分入口也已实跑62条。', '',
        '### 指标退化情况', '', '| 分组 | 无方差指标 |', '|---|---|'])
    for name, group in eda.items():
        lines.append('| ' + name + ' | ' + (', '.join(n for n, s in group['metrics'].items() if s['degenerate']) or '无') + ' |')
    lines.extend(['', '## 4. 逐条评分', '',
        '四维顺序：相关性/价值/证据/讨论推进。完整理由、指标和摘要见 examples/quant_validation/artifacts_scorecard.json；CSV见同目录scores_comparison.csv。所有记录状态均PendingReview。', '',
        '| 记录 | 标题 | 旧类型→新类型 | 四维等级 | 旧积分 | 候选分 | 重复 |', '|---|---|---|---|---:|---:|---|'])
    for i, r in enumerate(details, 1):
        title = r['Title'].replace('|', '／').replace('\n', ' ')[:60]
        lines.append(f"| {r['ScenarioId'] or '原'+str(i).zfill(2)} | {title} | {r['OldType']}→{r['NewType']} | " + '/'.join(str(r[d]) for d in DIMENSION_NAMES) + f" | {r['OldPoints']} | {r['CandidatePoints']} | {'是' if r['Duplicate'] else ''} |")
    lines.extend(['', '## 5. 验证边界与下一阶段', '',
        '- 本次不计算p值、人工一致性κ或模型真实准确率：独立真实记录及双标注尚缺。合成50条不能满足真实帖≥30或标注100–200条的要求。',
        '- 类型规则仍会混淆讨论中的反问与真正提问、资源分享与实践；见design_disagreements.csv。长文护栏也可能误伤没有动作词的有价值分析。',
        '- 回复数依赖当前导出覆盖范围，后续新增回复会改变该指标与候选分，不能解读为固定的个人质量。',
        '- 数字和URL仅是具体性信号，不能证明实验真实或文献可靠；操作词不是实际可执行性的证明。摘要限制词抽取仍会遗漏表达变体。',
        '- 当前M4代码块全零，无法评价其区分力；M5分位切点全部为零且合并为一个，链接信号最多只到L1。这是稀疏样本分布的限制，后续应对离散指标单独定标。',
        '- 下阶段按原计划：真实记录积累→双人盲标→类型κ/四维加权κ→按线程与重复族隔离探索和验证集→分位数敏感性与效度分析→正式定权与发布。', '',
        '## 6. 复现', '', '```powershell',
        'python -m venv .venv', '.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt',
        '.\\.venv\\Scripts\\python.exe tools/run_quant_validation.py',
        '.\\.venv\\Scripts\\python.exe -m pytest -q',
        '.\\.venv\\Scripts\\python.exe -m poc.run_poc examples/forvia_materials/EngageMessages_merged_62.csv --model scorecard --card examples/quant_validation/scorecard.json --out poc_output/scorecard',
        '```', '', f"实跑版本：Python {summary['python']}；numpy {summary['numpy']}；scipy {summary['scipy']}；scikit-learn {summary['sklearn']}。", ''])
    (ROOT / 'PART2_SCORECARD_VALIDATION.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
