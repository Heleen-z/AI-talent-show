import numpy as np
from .simple_score import explain, groups_for, make_model


def test_threads_and_duplicates_stay_together():
    rows = [dict(NetworkId='n', ThreadId=t, ContentText=s) for t, s in
            [('1', '重复'), ('1', '回复'), ('2', '重复'), ('3', '独立')]]
    groups = groups_for(rows)
    assert groups[0] == groups[1] == groups[2]
    assert groups[3] != groups[0]


def test_vocabulary_does_not_include_unseen_test_text():
    model = make_model().fit(['方法验证', '普通交流', '有用经验'], [7, 2, 6])
    before = dict(model[0].vocabulary_)
    prediction = model.predict(['稀有词汇XYZ'])
    assert np.isfinite(prediction).all()
    assert before == model[0].vocabulary_
    assert 'XYZ' not in before


def test_explanation_is_sparse_feature_contributions():
    model = make_model().fit(['具体方法可复用', '普通问候'], [8, 1])
    positive, negative, intercept, contribution = explain(model, '具体方法可复用')
    assert isinstance(positive, str) and isinstance(negative, str)
    assert np.isfinite(intercept) and np.isfinite(contribution)
