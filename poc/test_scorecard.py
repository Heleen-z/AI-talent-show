import copy

import pytest

from .baseline import Message, build_contexts, run_pipeline
from .eda import matrix, NAMES
from .preprocess import preprocess_message
from .scorecard import ScorecardBackend, fit, level


def row(mid='1', text='先确认版本，再检查原文。', parent='', root='1'):
    return dict(MessageKey='n:' + mid, MessageId=mid, NetworkId='n', ThreadId=root,
                IsRootPost=str(not parent), ReplyToId=parent, ContentText=text,
                SenderId='u', SenderName='example', PostedAt='2026-09-28', LanguageCode='zh-Hans')


def test_nested_parent_and_network_isolation():
    rows = [row(), row('2', parent='1'), row('3', parent='2')]
    other = dict(row(), NetworkId='other', MessageKey='other:1')
    messages = [Message(r) for r in rows + [other]]
    contexts = build_contexts(messages)
    assert contexts['n:3'].parent.message_key == 'n:2'
    assert contexts['other:1'].starter.message_key == 'other:1'


def test_metrics_url_numbers_steps_and_root_interactions():
    rows = [row(text='首先检查20条。https://example.org/12345'), row('2', parent='1')]
    result = matrix(rows)
    assert result[0][NAMES[4]] == 1
    assert result[0][NAMES[5]] == pytest.approx(100 / len(rows[0]['ContentText']))
    assert result[0][NAMES[6]] == 1
    assert result[0][NAMES[8]] == 1
    assert result[1][NAMES[8]] == 0


def test_degenerate_and_tied_cuts_do_not_award_three_levels():
    assert level(10, {'degenerate': True, 'cuts_log1p': [0, 0, 0]}) == 0
    assert level(1, {'degenerate': False, 'cuts_log1p': [0, 0, 0]}) == 1
    assert level(0, {'degenerate': False, 'cuts_log1p': [0, 0, 0]}) == 0


def test_hold_duplicates_and_metadata_does_not_leak():
    rows = [row(), row('2')]
    backend = ScorecardBackend(fit(rows), rows)
    results = run_pipeline(rows, backend.evaluate, review_hold=True)
    assert all(r['points']['points'] == 0 for r in results)
    assert all(r['points']['duplicate_flag'] for r in results)
    assert all(r['points']['scoring_status'] == 'PendingReview' for r in results)
    altered = copy.deepcopy(rows)
    for r in altered:
        r.update(DataOrigin='fake', ScenarioId='99', AuthorDesignedIntent='resource')
    new = run_pipeline(altered, ScorecardBackend(backend.card, altered).evaluate, review_hold=True)
    assert [r['evaluation'] for r in new] == [r['evaluation'] for r in results]


def test_qualifications_retained_and_gate_passes():
    rows = [row(text='我们测试摘要。准备比较模型。已经整理资料。尚未验证效果，所有数字是模拟。')]
    result = run_pipeline(rows)[0]
    assert any('尚未验证' in s for s in result['summary']['limitations'])
    assert not result['points'].get('gate_failures')


def test_duplicate_keys_rejected():
    with pytest.raises(ValueError, match='Duplicate MessageKey'):
        run_pipeline([row(), row()])


def test_frozen_card_does_not_recalibrate_with_batch():
    rows = [row(), row('2', text='模型验证。' * 50, root='2')]
    card = fit(rows)
    first = ScorecardBackend(card, rows).records['n:1']
    second = ScorecardBackend(card, rows[:1]).records['n:1']
    assert first == second
    assert card == fit(rows)
