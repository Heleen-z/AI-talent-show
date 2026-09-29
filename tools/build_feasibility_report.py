"""Render the local feasibility report as a self-contained, printable HTML file."""
from pathlib import Path
import html
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/AITALENTSHOW_FEASIBILITY_REPORT.md'
OUT = SOURCE.with_suffix('.html')


def diagram(title, nodes, edges, height=520):
    parts = [f'<svg viewBox="0 0 1080 {height}" role="img" aria-label="{html.escape(title)}" xmlns="http://www.w3.org/2000/svg">',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#51677d"/></marker></defs>']
    for d, pending in edges:
        dash = ' stroke-dasharray="7 5"' if pending else ''
        parts.append(f'<path d="{d}" fill="none" stroke="#51677d" stroke-width="2"{dash} marker-end="url(#arrow)"/>')
    for x, y, heading, line1, line2, pending in nodes:
        color = '#fff5e6' if pending else '#edf4f8'
        parts.append(f'<rect x="{x}" y="{y}" width="222" height="100" rx="6" fill="{color}" stroke="#b9c9d4"/>')
        for dy, text, size, weight in [(27,heading,16,600),(53,line1,13,400),(77,line2,12,400)]:
            parts.append(f'<text x="{x+111}" y="{y+dy}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="{size}" font-weight="{weight}" fill="#20354a">{html.escape(text)}</text>')
    parts.append('</svg>')
    return ''.join(parts)


diagrams = [
    diagram('记录、评分、复核发布与排名全流程', [
        (24,30,'01 员工贡献','Viva Engage','主帖 + 回复',False),
        (294,30,'02 每日采集','Power Automate','社区分页 + 线程读取',False),
        (564,30,'03 原文与日志','EngageMessages','EngageSyncRuns',False),
        (834,30,'04 导出快照','CSV / MessageKey','正文 + 身份 + 时间',False),
        (834,210,'05 文本候选评分','normalize → TF-IDF → Ridge','simple_score.py · 本地已实现',False),
        (564,210,'06 实验产物','model / scores / report','Experimental · 不是最终积分',False),
        (294,210,'07 新帖推理与回联','加载冻结模型 + 原始快照','新入口 / 身份与版本待补',True),
        (24,210,'08 人工复核','候选分 → FinalPoints','批准 / 拒绝 / 留存原因',True),
        (24,390,'09 积分事实','ActivityPoints','审计不足时补 PointsLedger',True),
        (294,390,'10 按人按周期汇总','build_totals()','函数已实现 · 接口待接入',True),
        (564,390,'11 排名快照','LeaderboardTotals','唯一键 + 状态 + 发布批次',True),
        (834,390,'12 员工展示','Power Apps','周 / 月 / 年榜与个人明细',True),
    ], [('M246 80H287',False),('M516 80H557',False),('M786 80H827',False),
        ('M945 130V203',False),('M834 260H793',False),('M564 260H523',True),
        ('M294 260H253',True),('M135 310V383',True),('M246 440H287',True),
        ('M516 440H557',True),('M786 440H827',True)]),
    diagram('训练、组外验证与日常推理的不同路径',[
        (24,30,'有标签正文','CSV + 人工 / 弱标签','按线程及重复正文分组',False),
        (390,30,'每折独立训练','TF-IDF + Ridge','词表与IDF只看训练折',False),
        (834,30,'组外评估','OutOfFoldScore','MAE 0.937 / 基线 0.980',False),
        (390,210,'全量拟合','冻结模型 model.joblib','FittedScore 是回代结果',False),
        (24,390,'新增或修改的消息','ContentText + 业务键','无需预先有人工作分',True),
        (390,390,'加载模型只预测','CandidateScore + 版本','独立推理入口待补',True),
        (834,390,'人工复核与发布','FinalPoints','业务规则在此执行',True),
    ], [('M246 80H383',False),('M612 80H827',False),('M135 130V260H383',False),
        ('M501 310V383',True),('M246 440H383',True),('M612 440H827',True)]),
    diagram('消息、评分版本、复核与榜单之间的键关系',[
        (24,30,'采集运行','EngageSyncRuns','RunId / Status',False),
        (390,30,'原文记录','EngageMessages','MessageKey / LastRunId',False),
        (834,30,'评分版本','MessageKey + 内容哈希','模型版本 + 评估版本',True),
        (834,210,'复核记录','Reviewer / ReviewAt','原因 + 状态',True),
        (390,210,'最终积分版本','MessageKey | Eval | Rule','一个消息一个当前有效版本',True),
        (24,210,'上次汇总快照','同用户 + 同周期','用于计算净变化和排名变化',True),
        (390,390,'当前周期汇总','UserId | PeriodType | Key','完整快照 / 失效旧行',True),
        (834,390,'榜单与追溯','Power Apps','总分 → 积分 → 复核 → 原帖',True),
    ], [('M246 80H383',False),('M612 80H827',True),('M945 130V203',True),
        ('M834 260H619',True),('M501 310V383',True),('M135 310V440H383',True),
        ('M612 440H827',True)])
]


def inline(text):
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)


def render(source):
    lines = source.splitlines()
    result, nav = [], []
    i = chart = section = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith('```'):
            language = line[3:]
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                block.append(lines[i]); i += 1
            if language == 'mermaid':
                result.append('<figure>' + diagrams[chart] + f'<figcaption><a href="AITALENTSHOW_DIAGRAM_{chart+1}.svg" target="_blank">单独打开结构图</a> · 蓝灰：已有设计/样例或本地实现；浅橙及虚线：待接入或待完善。图示不等于云端部署证明。</figcaption></figure>')
                chart += 1
            else:
                result.append('<pre><code>' + html.escape('\n'.join(block)) + '</code></pre>')
            i += 1
            continue
        if line.startswith('# '):
            i += 1
            continue
        if line.startswith('## '):
            section += 1
            title = line[3:]
            if section > 1: result.append('</section>')
            result.append(f'<section id="s{section}"><h2>{inline(title)}</h2>')
            nav.append(f'<a href="#s{section}">{html.escape(title)}</a>')
            i += 1
            continue
        if line.startswith('### '):
            result.append('<h3>' + inline(line[4:]) + '</h3>'); i += 1
            continue
        if line.startswith('|'):
            table = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [x.strip() for x in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', c) for c in cells): table.append(cells)
                i += 1
            result.append('<div class="tablewrap"><table><thead><tr>' + ''.join('<th>'+inline(c)+'</th>' for c in table[0]) + '</tr></thead><tbody>')
            for row in table[1:]: result.append('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>')
            result.append('</tbody></table></div>')
            continue
        if line.startswith('- ') or re.match(r'^\d+\. ',line):
            ordered = not line.startswith('- ')
            tag = 'ol' if ordered else 'ul'
            result.append('<'+tag+'>')
            while i < len(lines) and (re.match(r'^\d+\. ',lines[i]) if ordered else lines[i].startswith('- ')):
                result.append('<li>'+inline(re.sub(r'^(?:- |\d+\. )','',lines[i]))+'</li>'); i += 1
            result.append('</'+tag+'>')
            continue
        if line.startswith('> '):
            result.append('<blockquote>'+inline(line[2:])+'</blockquote>'); i += 1
            continue
        result.append('<p>'+inline(line)+'</p>'); i += 1
    result.append('</section>')
    assert chart == 3
    return ''.join(result), ''.join(nav)


body, navigation = render(SOURCE.read_text(encoding='utf-8'))
css = '''
:root{color-scheme:light;--ink:#1c3246;--muted:#526577;--accent:#145c83;--line:#d7e0e6;--paper:#fff;--ground:#f3f6f8}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:var(--ground);color:var(--ink);font:15px/1.85 "Microsoft YaHei","Segoe UI",sans-serif}a{color:var(--accent)}aside{position:fixed;width:240px;height:100vh;overflow:auto;padding:26px 22px;background:#eaf0f4;border-right:1px solid var(--line)}aside .brand{font-weight:700;font-size:18px;line-height:1.4;margin-bottom:12px}aside a{display:block;font-size:13px;text-decoration:none;padding:8px 0;border-bottom:1px solid var(--line)}aside small{color:var(--muted)}main{max-width:1420px;margin-left:240px;padding:40px 48px 80px}header{border-bottom:3px solid var(--accent);padding-bottom:25px;margin-bottom:24px}.eyebrow{color:var(--accent);font-size:12px;letter-spacing:2px;font-weight:700}h1{font-size:30px;line-height:1.4;margin:8px 0}header p{margin:8px 0;color:var(--muted)}.conclusion{font-size:19px;max-width:960px;font-weight:600;color:var(--ink)}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin-top:26px}.stat{border-left:3px solid var(--line);padding-left:16px}.stat b{font-size:24px;display:block;line-height:1.4}.stat span{font-size:12px;color:var(--muted)}section{background:var(--paper);padding:28px 30px;margin-bottom:24px;border:1px solid var(--line);overflow:hidden}h2{font-size:22px;line-height:1.5;margin:0 0 20px}h3{font-size:17px;margin:25px 0 12px}p{margin:12px 0}li{margin:9px 0}strong{font-weight:650}.tablewrap{overflow-x:auto;margin:20px 0}table{width:100%;border-collapse:collapse;font-size:13px;line-height:1.75;min-width:660px}th,td{text-align:left;vertical-align:top;padding:12px 13px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{background:#eaf0f4;font-weight:650}td:first-child{min-width:100px}tr:nth-child(even) td{background:#f8fafb}figure{margin:22px 0;overflow-x:auto}svg{display:block;width:100%;min-width:0;height:auto}figcaption{font-size:12px;color:var(--muted);margin:8px 0}pre{overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;padding:18px;background:#eff3f6;border-left:3px solid #7892a6;font-size:12px;line-height:1.7}code{font-family:Consolas,monospace;font-size:.92em}blockquote{border-left:3px solid var(--accent);padding:12px 20px;margin:18px 0;background:#f0f6f9}button{font:inherit;font-size:13px;cursor:pointer;border:1px solid var(--accent);color:var(--accent);padding:7px 14px;background:white;margin-top:14px}footer{font-size:13px;color:var(--muted)}
@media(max-width:1050px){aside{position:static;width:auto;height:auto;padding:16px 22px}aside nav{display:none}aside small{display:none}main{margin:0;padding:22px 16px}section{padding:22px 18px}.stats{gap:12px}h1{font-size:26px}}
@media print{@page{size:A4 landscape;margin:12mm}body{background:white;font-size:10pt}aside,button{display:none}main{margin:0;max-width:none;padding:0}header{margin-bottom:15px}h1{font-size:24pt}section{border:0;padding:0;margin:20px 0;overflow:visible}h2,h3{break-after:avoid}table{font-size:9pt;min-width:0}thead{display:table-header-group}tr,figure,.stats{break-inside:avoid}td,th{padding:7px 8px}.tablewrap{overflow:visible}svg{min-width:0}pre{font-size:9pt}a{color:inherit;text-decoration:none}h2{border-top:1px solid #ccd5db;padding-top:14px}}
'''
page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Talent Show｜全流程可行性分析汇报</title><style>{css}</style></head><body>
<aside><div class="brand">AI Talent Show<br>可行性分析汇报</div><small>项目证据 · 2026年9月29日</small><nav>{navigation}</nav><button onclick="window.print()">打印 / 另存为 PDF</button><a href="AITALENTSHOW_FEASIBILITY_REPORT.md">查看 Markdown 源稿</a></aside>
<main><header><div class="eyebrow">PROJECT FEASIBILITY / EVIDENCE REVIEW</div><h1>从活动记录，到评分，再到排名</h1><p class="conclusion">具备受控试点基础。正式发布还需要贯通人工复核、版本化积分与榜单写回。</p><p>基于当前项目文件与本地复验，明确区分已有实现、历史证据及待接入环节。</p><div class="stats"><div class="stat"><b>62 / 35</b><span>实验消息 / 分组</span></div><div class="stat"><b>0.937</b><span>弱标签验证 MAE · 满分10</span></div><div class="stat"><b>13 / 13</b><span>现有本地测试通过</span></div><div class="stat"><b>待闭环</b><span>审批 → 写回 → 展示</span></div></div></header>{body}<footer>项目文件核验与本地执行：2026年9月29日。模拟审批与建议字段不代表真实员工已获积分。无外部资源依赖，可离线阅读和打印。</footer></main></body></html>'''
for index, svg in enumerate(diagrams, 1):
    (SOURCE.parent / f'AITALENTSHOW_DIAGRAM_{index}.svg').write_text(svg, encoding='utf-8')
OUT.write_text(page, encoding='utf-8')
print(OUT)
print(f'{len(page):,} characters; {len(diagrams)} inline SVG diagrams; 11 sections')
