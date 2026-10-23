import unittest
from unittest.mock import patch
import ml


class SentimentRegressionTests(unittest.TestCase):
    def test_short_positive_reviews(self):
        for text in ('this movie is too good yar', 'This is a good movie',
                     'I loved this movie', 'Amazing brilliant film',
                     'The performances were wonderful', 'It was okay'):
            with self.subTest(text=text):
                self.assertEqual(ml.analyze(text)['label'], 'Positive')

    def test_negation(self):
        for text, expected in [('this movie is not good','Negative'),
                               ('this movie is not bad','Positive'),
                               ('I did not enjoy this movie','Negative'),
                               ("This movie isn't good",'Negative')]:
            with self.subTest(text=text):
                self.assertEqual(ml.analyze(text)['label'], expected)

    def test_negative_reviews(self):
        for text in ('Awful boring movie', 'I hated every minute',
                     'Terrible acting and a stupid story'):
            with self.subTest(text=text):
                self.assertEqual(ml.analyze(text)['label'], 'Negative')

    def test_mixed_and_no_clear_opinion_abstain(self):
        for text in ('The acting was great but the plot was terrible',
                     'Amazing cinematography but a boring story',
                     'The film was released in 2020', 'xyz qwerty abc'):
            with self.subTest(text=text):
                self.assertEqual(ml.analyze(text)['label'], 'Uncertain')

    def test_long_reviews_use_original_classifier(self):
        text = 'The cinematography creates an interesting world. ' * 12
        result = ml.analyze(text)
        self.assertEqual(result['method'], 'trained-classifier')
        self.assertEqual(result['characters_analyzed'],len(text))

    def test_probability_is_explicitly_baseline_only(self):
        result = ml.analyze('this movie is too good yar')
        self.assertEqual(result['label'],'Positive')
        self.assertLess(result['positive_probability'], .5)
        self.assertEqual(result['probability_source'],'baseline-classifier-only')
        self.assertIn('positive opinion', result['explanation'])
        self.assertNotIn('confidence',result)

    def test_summary_counts_abstentions(self):
        summary = ml.aggregate([{'sentiment':ml.analyze(t)} for t in
                               ('Great movie', 'Awful movie', 'The film was released in 2020')])
        self.assertEqual(summary['counts'],{'Positive':1,'Negative':1,'Uncertain':1})
