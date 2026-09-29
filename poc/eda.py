"""Deterministic M1–M10 extraction and descriptive, provenance-separated EDA."""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

from .preprocess import preprocess_message, URL_RE

NAMES = ['M1_characters', 'M2_paragraphs', 'M3_chars_per_paragraph',
         'M4_code_blocks', 'M5_urls', 'M6_numbers_per_100_chars',
         'M7_steps', 'M8_questions', 'M9_thread_replies', 'M10_intent_hints']
STEPS = re.compile(r'步骤|首先|其次|然后|最后|第一|第二|流程|先(?=按|确认|验证|检查|划分)|step\s*\d+', re.I)
QUESTIONS = re.compile(r'怎么|如何|怎么办|求助|请教|有没有|能不能|是否|可不可以', re.I)
PRACTICE = re.compile(r'实践|落地|项目|测试|实验|试验|复盘|搭建|部署|记录|验证', re.I)
ANSWER = re.compile(r'建议|可以试|试试|方法|步骤|解决|应该|先确认|先按|先验证|keep|retrieve|check', re.I)


def extract(artifact, row, thread_counts):
    text, stats = artifact['normalized_text'], artifact['text_stats']
    # URL identifiers/year strings in hyperlinks are not numerical evidence.
    without_urls = URL_RE.sub('', text)
    numeric_count = len(re.findall(r'(?<![A-Za-z0-9_])\d+(?:\.\d+)?%?', without_urls))
    values = [stats['characters'], stats['paragraphs'],
              stats['characters'] / max(1, stats['paragraphs']),
              stats['code_blocks'], stats['urls'],
              numeric_count * 100 / max(1, stats['characters']),
              len(STEPS.findall(without_urls)),
              len(re.findall(r'[?？]', text)) + len(QUESTIONS.findall(text[:300])),
              max(0, thread_counts.get((row.get('NetworkId', ''), row['ThreadId']), 1) - 1)
              if row.get('IsRootPost') == 'True' else 0,
              int(bool(PRACTICE.search(text))) + int(bool(ANSWER.search(text)))]
    return dict(zip(NAMES, values))


def matrix(rows):
    counts = Counter((r.get('NetworkId', ''), r['ThreadId']) for r in rows)
    return [dict(MessageKey=r['MessageKey'], DataOrigin=r.get('DataOrigin', 'unspecified'),
                 IsSynthetic=r.get('IsSynthetic', 'unknown'),
                 **extract(preprocess_message(r['MessageKey'], r.get('ContentText', ''),
                                              r.get('LanguageCode')), r, counts)) for r in rows]


def describe(records):
    groups = {'all': records}
    for origin in sorted({r['DataOrigin'] for r in records}):
        groups['origin:' + origin] = [r for r in records if r['DataOrigin'] == origin]
    return {group: {'n': len(items), 'metrics': {
        name: {'min': float(min(vals)), 'max': float(max(vals)),
               'p25': float(np.quantile(vals, .25)), 'p60': float(np.quantile(vals, .6)),
               'p90': float(np.quantile(vals, .9)), 'zero_count': sum(v == 0 for v in vals),
               'degenerate': len(set(vals)) < 2}
        for name in NAMES for vals in [[r[name] for r in items]]}}
        for group, items in groups.items() if items}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('csv', type=Path)
    parser.add_argument('--out', type=Path, default=Path('poc_output/eda'))
    args = parser.parse_args()
    with args.csv.open(encoding='utf-8-sig', newline='') as stream:
        records = matrix(list(csv.DictReader(stream)))
    if not records:
        parser.error('No input records')
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / 'metrics.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    (args.out / 'eda.json').write_text(json.dumps(describe(records), ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
