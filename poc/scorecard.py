"""Exploratory v0.2-alpha; frozen quantile card, never a calibrated quality model."""
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from .eda import NAMES, matrix, ANSWER, PRACTICE

VERSION = 'quantile-scorecard-0.2-alpha'
# M8/M10 classify intent. M3 is density of formatting, not semantic density.
# Relevance cannot be measured defensibly by these ten metrics: use an explicit
# topic/context heuristic and require human review instead of inventing a metric.
DIM_METRICS = {'value': [NAMES[0], NAMES[1], NAMES[2]],
               'evidence': [NAMES[3], NAMES[4], NAMES[5]],
               'discussion_impact': [NAMES[6], NAMES[8]]}
TOPIC = re.compile(r'AI|模型|摘要|检索|知识库|评分|智能体|算法|数据|OCR|ECU|sensor|fault|retrieve|test', re.I)
ACTION = re.compile(r'过滤|保存|保留|核对|检查|比较|记录|划分|统计|确认|验证|补充|加入|分开|固定|冻结|keep|retrieve|check|show|ask', re.I)
RETRO = re.compile(r'复盘|回看|才发现|被掩盖|漏掉这种错误|误报')
LIMIT = re.compile(r'尚未|不能|不足|失败|没有|不一定|缺少|暂不能|未验证|模拟|虚构|not yet|not evidence', re.I)


def fit(rows):
    records = matrix(rows)
    if not records:
        raise ValueError('Cannot fit an empty calibration set')
    metrics = {}
    for name in NAMES:
        values = [math.log1p(r[name]) for r in records]
        metrics[name] = {'cuts_log1p': [float(np.quantile(values, q)) for q in (.25, .6, .9)],
                         'degenerate': len(set(values)) < 2}
    digest = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    return {'version': VERSION, 'status': 'exploratory_not_validated',
            'calibration_n': len(rows), 'calibration_digest': digest,
            'metrics': metrics, 'dimension_metrics': DIM_METRICS,
            'normalization': 'log1p; strict > quantile; equal cuts collapsed; zero maps to zero',
            'weights': 'equal within dimension; equal across four dimensions',
            'origins': sorted({r.get('DataOrigin', 'unspecified') for r in rows})}


def level(value, spec):
    if value <= 0 or spec['degenerate']:
        return 0
    cuts = sorted(set(spec['cuts_log1p']))
    return sum(math.log1p(value) > c for c in cuts)


def intent(text, metrics, is_root):
    if re.search(r'感谢|收藏|收到|周末.*跑步', text) and len(text) < 65:
        return 'social', .8
    if metrics[NAMES[7]] > 0:
        return 'question', .65
    if RETRO.search(text) and PRACTICE.search(text):
        return 'retrospective', .65
    if not is_root:
        if ACTION.search(text) or ANSWER.search(text):
            return 'answer', .65
        if PRACTICE.search(text):
            return 'practice_share', .5
        return 'social', .35
    if metrics[NAMES[4]] and re.search(r'论文|报告|读|链接|分享|推荐|https', text):
        return 'resource', .65
    if PRACTICE.search(text) or TOPIC.search(text):
        return 'practice_share', .5
    return 'social', .35


class ScorecardBackend:
    def __init__(self, card, rows):
        if card.get('version') != VERSION:
            raise ValueError('Unsupported scorecard version')
        self.card = card
        self.records = {r['MessageKey']: r for r in matrix(rows)}

    @classmethod
    def load(cls, path, rows):
        return cls(json.loads(Path(path).read_text(encoding='utf-8')), rows)

    def evaluate(self, message, summary, ctx):
        metrics = self.records[message.message_key]
        text = message.text
        kind, confidence = intent(text, metrics, message.row.get('IsRootPost') == 'True')
        quantiles = {name: level(metrics[name], self.card['metrics'][name]) for name in NAMES}
        dims = {}
        active = {dim: [n for n in names if not self.card['metrics'][n]['degenerate']]
                  for dim, names in DIM_METRICS.items()}
        for dim, names in active.items():
            value = math.floor(sum(quantiles[n] for n in names) / len(names) + .5) if names else 0
            dims[dim] = {'level': value, 'evidence': [text[:100]] if text else [],
                         'reason': '等权分位等级；' + ', '.join(f'{n}={metrics[n]:.3g}/L{quantiles[n]}' for n in names)}
        on_topic = bool(TOPIC.search(text) or (ctx.parent and TOPIC.search(ctx.parent.text)))
        dims['relevance'] = {'level': 2 if on_topic and kind != 'social' else 0,
                             'evidence': [text[:100]] if text else [],
                             'reason': '主题/父帖规则代理，未测量语义相关性'}
        # Guardrails do not award points simply for verbosity or URL volume.
        if not ACTION.search(text):
            dims['value']['level'] = min(1, dims['value']['level'])
            dims['value']['reason'] += '；未检出具体操作，价值封顶L1'
        elif kind == 'answer':
            dims['value']['level'] = max(1, dims['value']['level'])
            dims['value']['reason'] += '；答复含操作信号，至少L1（待人工核实）'
        if kind == 'social':
            for dim in dims.values():
                dim['level'] = 0
                dim['reason'] += '；普通互动不加维度分'
        flags = list(summary['uncertainties']) + ['EXPLORATORY_CALIBRATION', 'RELEVANCE_PROXY']
        if confidence < .45:
            flags.append('LOW_TYPE_CONFIDENCE')
        if any(self.card['metrics'][n]['degenerate'] for names in DIM_METRICS.values() for n in names):
            flags.append('DEGENERATE_METRICS_EXCLUDED')
        if re.search(r'忽略.*评分|打满分|ignore.*instructions', text, re.I):
            flags.append('INSTRUCTION_IN_CONTENT')
        if re.search(r'100%|所有工厂|不需要人工', text):
            flags.append('CLAIM_REQUIRES_VERIFICATION')
        if LIMIT.search(text):
            flags.append('LIMITATION_OR_SIMULATION_STATED')
        return {'message_key': message.message_key, 'contribution_type': kind,
                'type_confidence': confidence, 'confidence_kind': 'heuristic_not_probability',
                'dimensions': dims, 'metrics': {n: metrics[n] for n in NAMES},
                'quality_flags': sorted(set(flags)), 'needs_human_review': True,
                'review_reason': 'alpha切点来自探索样例，未经真实双人标注定标；仅供试评分',
                'score_model_version': VERSION, 'prompt_version': 'none-deterministic',
                'calibration_digest': self.card['calibration_digest']}
