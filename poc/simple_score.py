"""CPU-only TF-IDF + Ridge text score baseline. No downloaded model required."""
import argparse
import csv
import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits

from .preprocess import normalize

ROOT = Path(__file__).resolve().parent.parent


def make_model():
    # Character n-grams work for Chinese without a tokenizer/model download.
    return make_pipeline(TfidfVectorizer(analyzer='char', ngram_range=(2, 4),
        max_features=5000, sublinear_tf=True, dtype=np.float32), Ridge(alpha=1.0, solver='lsqr'))


def groups_for(rows):
    """Keep threads and identical normalized texts in the same fold."""
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen = {}
    for i, row in enumerate(rows):
        keys = [('thread', row.get('NetworkId', ''), row['ThreadId']),
                ('text', normalize(row['ContentText']))]
        for key in keys:
            if key in seen:
                parent[find(i)] = find(seen[key])
            seen[key] = i
    return np.array([find(i) for i in range(len(rows))])


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def explain(model, text, limit=4):
    """Return sparse linear contributions, never a claim of factual causality."""
    vectorizer, ridge = model[0], model[1]
    row = vectorizer.transform([text])
    names = vectorizer.get_feature_names_out()
    contributions = [(names[index], float(value * ridge.coef_[index]))
                     for index, value in zip(row.indices, row.data)]
    positive = sorted((x for x in contributions if x[1] > 0), key=lambda x: -x[1])[:limit]
    negative = sorted((x for x in contributions if x[1] < 0), key=lambda x: x[1])[:limit]
    fmt = lambda items: '；'.join(f'{term} ({value:+.3f})' for term, value in items) or '无'
    return fmt(positive), fmt(negative), float(ridge.intercept_), float(sum(x[1] for x in contributions))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=ROOT / 'examples/forvia_materials/EngageMessages_merged_62.csv')
    parser.add_argument('--labels', type=Path, help='Optional human labels: MessageKey,HumanScore (0–10)')
    parser.add_argument('--out', type=Path, default=ROOT / 'poc_output/simple_score')
    args = parser.parse_args()
    start = time.perf_counter()
    rows = read_csv(args.csv)
    if len({r['MessageKey'] for r in rows}) != len(rows):
        parser.error('Duplicate MessageKey')
    if args.labels:
        labeled = [r for r in read_csv(args.labels) if r.get('HumanScore', '').strip()]
        if len({r['MessageKey'] for r in labeled}) != len(labeled):
            parser.error('Duplicate label key; adjudicate multiple raters before training')
        targets = {r['MessageKey']: float(r['HumanScore']) for r in labeled}
        source = 'human_provided_not_independently_verified'
    else:
        artifacts = json.loads((ROOT / 'examples/quant_validation/artifacts_scorecard.json').read_text(encoding='utf-8'))
        targets = {r['message_key']: sum(d['level'] for d in r['evaluation']['dimensions'].values()) * 10 / 12 for r in artifacts}
        source = 'existing_scorecard_weak_labels_before_duplicate_penalty'
    if not all(np.isfinite(y) and 0 <= y <= 10 for y in targets.values()):
        parser.error('All scores must be finite and within 0–10')
    rows = [r for r in rows if r['MessageKey'] in targets]
    groups = groups_for(rows)
    group_count = len(set(groups))
    if group_count < 3:
        parser.error('Need at least 3 independent thread/duplicate groups')
    texts = np.array([normalize(r['ContentText']) for r in rows])
    y = np.array([targets[r['MessageKey']] for r in rows])
    predictions, dummy = np.zeros(len(rows)), np.zeros(len(rows))
    fold_ids = np.zeros(len(rows), dtype=int)
    with threadpool_limits(limits=1):
        cv_start = time.perf_counter()
        for fold, (train, test) in enumerate(GroupKFold(min(5, group_count)).split(texts, y, groups), 1):
            model = make_model()  # Vocabulary and IDF fitted only on this fold's training rows.
            model.fit(texts[train], y[train])
            predictions[test] = np.clip(model.predict(texts[test]), 0, 10)
            dummy[test] = y[train].mean()
            fold_ids[test] = fold
        cv_seconds = time.perf_counter() - cv_start
        fit_start = time.perf_counter()
        model = make_model().fit(texts, y)
        fit_seconds = time.perf_counter() - fit_start
        predict_start = time.perf_counter()
        for _ in range(20):
            fitted_scores = np.clip(model.predict(texts), 0, 10)
        batch_ms = (time.perf_counter() - predict_start) * 1000 / 20
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / 'model.joblib'
    joblib.dump({'pipeline': model, 'label_source': source, 'version': 'char-tfidf-ridge-1'}, path, compress=3)
    with (args.out / 'scores.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['MessageKey', 'ScenarioId', 'DataOrigin', 'TargetScore', 'OutOfFoldScore', 'FittedScore',
                         'Intercept', 'FeatureContribution', 'TopPositiveNgrams', 'TopNegativeNgrams', 'Fold', 'Status'])
        for i, r in enumerate(rows):
            positive, negative, intercept, contribution = explain(model, texts[i])
            writer.writerow([r['MessageKey'], r.get('ScenarioId', ''), r.get('DataOrigin', ''),
                round(y[i], 3), round(predictions[i], 3), round(fitted_scores[i], 3),
                round(intercept, 3), round(contribution, 3), positive, negative, fold_ids[i], 'Experimental'])
    report = {'model': 'TF-IDF char(2,4), max_features=5000 + Ridge(alpha=1, solver=lsqr)',
              'label_source': source, 'n': len(rows), 'groups': group_count,
              'cv_mae_0_to_10': float(np.abs(predictions-y).mean()),
              'constant_mean_cv_mae': float(np.abs(dummy-y).mean()),
              'fit_seconds': fit_seconds, 'cv_seconds': cv_seconds,
              'predict_batch_ms': batch_ms, 'predict_per_row_ms': batch_ms / len(rows),
              'compressed_model_bytes': path.stat().st_size,
              'features': len(model[0].vocabulary_), 'numerical_threads': 1,
              'scope': 'Text-only experiment; no factuality guarantee; no score publication',
              'timing_excludes': 'Python process startup and package imports',
              'elapsed_seconds_after_import': time.perf_counter() - start}
    (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
