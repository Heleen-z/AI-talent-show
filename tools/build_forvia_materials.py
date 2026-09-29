"""Build synthetic forum fixtures without modifying the captured sample."""
import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'examples' / 'forvia_materials'
SOURCE = ROOT / 'examples' / 'EngageMessages_sample.csv'
REFERENCES = {
    'F1': ('FORVIA 2026 Capital Markets Day (2026-02-24)', 'https://www.forvia.com/en/press/forvia-2026-capital-markets-day'),
    'R1': ('Automotive requirements engineering RAG (2026-03, preprint)', 'https://arxiv.org/abs/2603.20534'),
    'R2': ('Qwen3 Technical Report (2025-05, technical report)', 'https://arxiv.org/abs/2505.09388'),
    'R3': ('Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena (2023, NeurIPS)', 'https://arxiv.org/abs/2306.05685'),
    'R4': ('Lost in the Middle: How Language Models Use Long Contexts (2023 preprint)', 'https://arxiv.org/abs/2307.03172'),
    'R5': ('SWE-Bench Pro Verified (2026-09, preprint)', 'https://arxiv.org/abs/2609.08149'),
}


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    materials = json.loads((DEST / 'materials.json').read_text(encoding='utf-8'))
    with SOURCE.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames)
        captured = list(reader)
    assert len(materials) == 50 and len(captured) == 12
    assert [p['id'] for p in materials] == list(range(1, 51))
    provenance_fields = ['DataOrigin', 'IsSynthetic', 'ScenarioId', 'SourceRefs']
    rows, labels = [], []
    by_number = {}
    for p in materials:
        number = p['id']
        assert all(ref in REFERENCES for ref in p['refs'])
        assert p['parent'] is None or p['parent'] in by_number
        mid = str(5_000_000_000_000 + number)
        parent = by_number.get(p['parent'])
        timestamp = (datetime(2026, 9, 28, 1, tzinfo=timezone.utc) + timedelta(minutes=number)).isoformat().replace('+00:00', 'Z')
        row = dict.fromkeys(fields, '')
        row.update(Title=p['title'], MessageKey=f'70000000001:{mid}', MessageId=mid,
                   NetworkId='70000000001', GroupId='70000000002', GroupName='Fight For Agentic',
                   ThreadId=parent['ThreadId'] if parent else mid,
                   IsRootPost=str(parent is None), SenderId=str(9_100_000_000_000 + p['author']),
                   SenderName=f"模拟员工{p['author']:02d}", PostedAt=timestamp, PublishedAt=timestamp,
                   LanguageCode='en' if number == 17 else 'zh',
                   SourceUrl=f'https://engage.example.invalid/threads/{parent["ThreadId"] if parent else mid}',
                   Privacy='private', MessageType='message', IsSystemMessage='False',
                   FirstCapturedAt=timestamp, LastSeenAt=timestamp, LastRunId='synthetic-forvia-20260928',
                   ContentText=p['text'], TextChangedAt=timestamp,
                   ReplyToId=parent['MessageId'] if parent else '',
                   DataOrigin='synthetic_forvia_v1', IsSynthetic='True', ScenarioId=f'S{number:02d}',
                   SourceRefs=';'.join(p['refs']))
        rows.append(row)
        by_number[number] = row
        labels.append({'ScenarioId': row['ScenarioId'], 'MessageKey': row['MessageKey'],
                       'AuthorDesignedIntent': p['intent'], 'ValidationFocus': p['check'],
                       'LabelStatus': 'author_design_not_human_ground_truth'})
    originals = [dict(r, DataOrigin='existing_anonymized_capture', IsSynthetic='False', ScenarioId='', SourceRefs='') for r in captured]
    merged = originals + rows
    assert len({r['MessageKey'] for r in merged}) == 62
    lookup = {r['MessageId']: r for r in merged}
    for row in merged:
        assert row['ThreadId'] in lookup
        if row['ReplyToId']:
            assert row['ReplyToId'] in lookup
            assert lookup[row['ReplyToId']]['ThreadId'] == row['ThreadId']
    assert [{k: r[k] for k in fields} for r in originals] == captured
    write_csv(DEST / 'EngageMessages_synthetic_50.csv', fields + provenance_fields, rows)
    write_csv(DEST / 'EngageMessages_merged_62.csv', fields + provenance_fields, merged)
    write_csv(DEST / 'author_design_labels.csv', list(labels[0]), labels)
    content = ['# FORVIA AI论坛模拟素材：50条', '',
               '> 全部新增帖子、员工、时间及实验经历均为虚构，用于本地评分验证。公开来源只支持公司背景或研究话题，不代表FORVIA开展了这些项目。', '',
               '本文展示新增50条；合并CSV另含原有12条匿名化抓取样例。帖子按消息编号排列，回复关系保留。', '',
               '作者设计标签另存于 author_design_labels.csv，不是人工标准答案，不应输入评分模型。', '']
    for p, r in zip(materials, rows):
        content.extend([f'## S{p["id"]:02d}｜{p["title"]}', '',
                        f'作者：{r["SenderName"]}｜' + (f'回复 S{p["parent"]:02d}' if p['parent'] else '主帖') + f'｜消息ID：{r["MessageId"]}', '',
                        p['text'], '', '背景/研究来源：' + ('、'.join(f'[{ref}]({REFERENCES[ref][1]})' for ref in p['refs']) or '原创模拟情境，无外部事实主张。'), ''])
    content.extend(['## 来源与适用范围', '', '检索核实日期：2026-09-28。以下不是系统性文献综述；2026年文献提供近期进展，2023—2025年文献提供基础方法。', ''])
    for key, (title, url) in REFERENCES.items():
        content.append(f'- {key}：[ {title} ]({url})')
    content.extend(['', 'FORVIA背景采用2026年资本市场日公开的业务框架；帖子将座椅、电子、照明、清洁出行、售后业务与通用制造任务结合，不声称其内部已采用某种模型。研究来源中的结论不能直接推广为本项目效果，预印本也不视为已完成同行评审。', ''])
    (DEST / 'MATERIALS_50.md').write_text('\n'.join(content), encoding='utf-8')
    report = {'original_rows': len(captured), 'new_synthetic_rows': len(rows), 'merged_rows': len(merged),
              'synthetic_roots': sum(r['IsRootPost'] == 'True' for r in rows),
              'synthetic_replies': sum(r['IsRootPost'] == 'False' for r in rows),
              'synthetic_authors': len({r['SenderId'] for r in rows}),
              'original_fields_preserved': True, 'all_thread_references_resolve': True,
              'author_designed_intents': dict(Counter(p['intent'] for p in materials))}
    (DEST / 'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
