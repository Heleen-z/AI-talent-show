"""Create a readable all-message report from the CPU-only score run."""
import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'examples/simple_score_results')
    parser.add_argument('--messages', type=Path, default=ROOT / 'examples/forvia_materials/EngageMessages_merged_62.csv')
    parser.add_argument('--out', type=Path, default=ROOT / 'PART2_SIMPLE_MODEL_ALL_MESSAGES.md')
    args = parser.parse_args()
    scores = read_csv(args.input / 'scores.csv')
    report = json.loads((args.input / 'report.json').read_text(encoding='utf-8'))
    messages = {r['MessageKey']: r for r in read_csv(args.messages)}
    if len(scores) != len(messages) or {r['MessageKey'] for r in scores} != set(messages):
        parser.error('Score rows and message rows do not match exactly')
    lines = [
        '# 全部正文的轻量文本评分结果', '',
        '日期：2026-09-28。范围：62条正文（原有12条匿名化抓取样例，50条模拟素材）。所有结果均为实验候选分，不写回SharePoint、不产生员工积分。', '',
        '## 模型与分数口径', '',
        f"模型为 `{report['model']}`，以单线程CPU运行。训练目标为现有alpha评分卡的弱标签，属于对既有规则的轻量复现；不等同于人工质量评分。",
        f"训练样本：{report['n']}条，独立线程/重复组：{report['groups']}组。5折分组交叉验证 MAE：{report['cv_mae_0_to_10']:.3f}/10；均值基线 MAE：{report['constant_mean_cv_mae']:.3f}/10。性能数据见 [轻量模型POC](PART2_SIMPLE_MODEL_POC.md)。", '',
        '每条展示两种分数：**候选分**是在全部62条上训练后回代的分数，方便当前批次排序；**验证分**来自未使用该条所在讨论串/完全重复文本组训练的折，适合查看泛化误差。候选分不能作为准确率证据。', '',
        '“形成原因”由线性模型的字符TF-IDF特征贡献组成：`截距 + 所有出现特征的贡献 = 未截断预测`，最后截断到0—10。正/负短语只是与当前弱标签的统计相关，并不表示短语本身有业务价值、内容为真，或员工应使用该措辞。没有显著正/负短语时写“无”。', '',
        '重复惩罚不在此模型中学习；若日后用于积分流程，仍要在模型之后执行相同作者同正文的业务规则、人工复核和发布门禁。', '',
        '## 逐条结果', '']
    for index, score in enumerate(scores, 1):
        message = messages[score['MessageKey']]
        title = message.get('Title', '').replace('\n', ' ') or '（无标题）'
        scenario = score.get('ScenarioId') or f'原样例{index:02d}'
        body = message.get('ContentText', '').strip()
        lines.extend([
            f'### {scenario}｜{title}', '',
            f"- 消息键：`{score['MessageKey']}`；来源：`{score['DataOrigin']}`；讨论折：{score['Fold']}",
            f"- 正文：{body}",
            f"- 弱标签目标分：{float(score['TargetScore']):.2f}/10；候选分：{float(score['FittedScore']):.2f}/10；验证分：{float(score['OutOfFoldScore']):.2f}/10。",
            f"- 分数形成：截距 {float(score['Intercept']):+.3f} + 特征贡献 {float(score['FeatureContribution']):+.3f}。正向短语：{score['TopPositiveNgrams']}。负向短语：{score['TopNegativeNgrams']}。",
            f"- 状态：{score['Status']}；需要人工检查的重点：短语贡献是否确实对应有价值内容，而非只是在弱标签中经常出现。", ''])
    args.out.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Wrote {args.out} with {len(scores)} message results.')


if __name__ == '__main__':
    main()
