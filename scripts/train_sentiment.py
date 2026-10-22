"""Reproducible train/test experiment; no dataset texts redistributed."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request
import joblib
import sklearn
import numpy
import scipy
import platform
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://www.cs.cornell.edu/people/pabo/movie-review-data/rt-polaritydata.tar.gz'

def train():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', help='Optional local copy of rt-polaritydata.tar.gz')
    args = parser.parse_args()
    if args.archive:
        raw = Path(args.archive).read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            raw = response.read()
    texts, labels, seen = [], [], set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for suffix, label in [('rt-polarity.neg', 0), ('rt-polarity.pos', 1)]:
            member = next(m for m in archive.getmembers() if m.name.endswith(suffix))
            for line in archive.extractfile(member).read().split(b'\n'):
                text = line.decode('latin-1').strip()
                if text and text.casefold() not in seen:
                    seen.add(text.casefold()); texts.append(text); labels.append(label)
    xtrain, xtest, ytrain, ytest = train_test_split(texts, labels, test_size=.2, random_state=42, stratify=labels)
    model = Pipeline([('tfidf', TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=60000)),
                      ('classifier', LogisticRegression(C=4, max_iter=1000, random_state=42))])
    model.fit(xtrain, ytrain)
    predictions = model.predict(xtest)
    metrics = {'dataset': 'Pang and Lee sentence polarity v1.0 (2005)', 'source': URL,
               'archive_sha256': hashlib.sha256(raw).hexdigest(), 'unique_samples': len(texts),
               'train_samples': len(xtrain), 'test_samples': len(xtest), 'random_state': 42, 'versions': {'python': platform.python_version(), 'scikit_learn': sklearn.__version__, 'numpy': numpy.__version__, 'scipy': scipy.__version__},
               'accuracy': accuracy_score(ytest, predictions),
               'classification_report': classification_report(ytest, predictions, target_names=['Negative','Positive'], output_dict=True),
               'confusion_matrix': confusion_matrix(ytest, predictions).tolist(),
               'matrix_order': ['Negative','Positive'],
               'limitations': 'Binary English sentence polarity. No neutral training class. Sentence-level random split; source film/author overlap may exist. Not an independent real-world benchmark.'}
    (ROOT/'models').mkdir(exist_ok=True)
    joblib.dump(model, ROOT/'models/sentiment.joblib', compress=3)
    (ROOT/'models/metrics.json').write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))

if __name__ == '__main__':
    train()
