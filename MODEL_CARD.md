# Sentiment model card

Model: TF-IDF unigrams/bigrams + Logistic Regression (binary English polarity).
Dataset: Pang & Lee sentence polarity v1.0, 2005.
Source: https://www.cs.cornell.edu/people/pabo/movie-review-data/rt-polaritydata.tar.gz
Archive SHA-256: `a05befe52aafda71d458d188a1c54506a998b1308613ba76bbda2e5029409ce9`

After exact case-insensitive deduplication: 10662 samples.
Training: 8529; test: 2133; stratified 80/20 split, seed 42.

Measured held-out accuracy: **78.48%**.
Macro F1: **0.7848**.
Confusion matrix (actual rows, predicted columns; Negative, Positive): `[[832, 235], [224, 842]]`.

Metrics use the binary 0.50 boundary. UI abstains as Uncertain between 0.40 and 0.60. No neutral training class. Probabilities are uncalibrated. The test set is older sentence snippets; it does not validate live review performance or Hindi/Hinglish, and source film/author overlap may exist across the split.

Training code: `scripts/train_sentiment.py`. Exact metrics: `models/metrics.json`. Vocabulary fit only on training data. Model bundled for immediate offline inference. Training archive and review texts are not redistributed.

Reproduction used Python 3.12, scikit-learn 1.6.1, NumPy 2.2.6 and SciPy 1.15.3. Runtime dependencies are pinned. The Render blueprint uses Python 3.11.11; cross-platform install and deployment should be checked on the target machine.

## Release 3.1.0 routing

Reviews of up to 50 whitespace-separated words use VADER 3.3.2 English sentiment rules, including its local negation handling. Positive and negative component ratios both >=0.10 cause abstention as Uncertain. Otherwise compound >=0.20 is Positive; <=-0.20 is Negative; weak scores abstain. These thresholds are product heuristics. VADER's compound score is not a probability. Source: https://github.com/cjhutto/vaderSentiment

Longer reviews use the original trained classifier with its 0.40–0.60 abstention band. The accuracy above is ONLY for that original classifier, before routing. The combined system has targeted regression tests but no independent benchmark. It can still fail on context, sarcasm and code-switching. The UI does not show a confidence percentage. Legacy API probability fields and stored probabilities retain the original baseline classifier estimates for compatibility and are identified as baseline-only; they do not measure confidence in a rule-derived label.
