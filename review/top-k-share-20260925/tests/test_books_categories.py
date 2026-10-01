"""Privacy-boundary and reproducibility checks for the Books preparation."""
import csv
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'experiments'/'validation'))
from amazon_books_categories import prepare, run
from ldp_protocols import FrequencyEstimate


class BooksPreparationTests(unittest.TestCase):
    def test_fixed_target_and_release_reuse(self):
        payload = dict(labels=['A', 'B', 'C'], catalog=[1, 1, 1],
                       events={'2011': [0, 0, 1, 2], '2012': [0, 1, 1, 2],
                               '2013': [0, 0, 0, 1, 2]},
                       book_events={'2011': ['a', 'a', 'b', 'c'],
                                    '2012': ['a', 'b', 'b', 'c'],
                                    '2013': ['a', 'a', 'a', 'b', 'c']})
        args = SimpleNamespace(users=2, epsilon=2, report_ratio=1, top_k=1,
                               source_years=[2011, 2012], target_year=2013,
                               seeds=[7], full_target=True)
        cache = {}
        with patch('amazon_books_categories.estimate_frequency',
                   return_value=FrequencyEstimate(np.array([2., 1., 0.]), np.ones(3), 'OLH')) as estimate:
            first = run(payload, args, cache)
            args.report_ratio = 2
            second = run(payload, args, cache)
        self.assertEqual(estimate.call_count, 2)
        self.assertTrue(all(r['target_users'] == 5 for r in first+second))
        self.assertTrue(all(abs(r['target_topk_mass']-.6) < 1e-12 for r in first+second))
        self.assertTrue(all(r['candidate_recall_upper_bound'] >= r['recall'] for r in first+second))

    def test_order_independence_and_global_year_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata, ratings = root/'metadata.csv', root/'ratings.csv'
            with metadata.open('w', newline='', encoding='utf8') as f:
                w = csv.DictWriter(f, fieldnames=['Title', 'categories'])
                w.writeheader()
                w.writerows([dict(Title='A', categories="['X', 'Y']"),
                             dict(Title='B', categories="['Unreviewed']")])
            fields = ['Title', 'User_id', 'Id', 'review/time', 'review/score']
            rows = [dict(zip(fields, ['A', 'u', 'book', time, '5']))
                    for time in ['1293840000', '1325376000', '1356998400']]
            rows += [dict(zip(fields, ['A', 'v', 'book2', '1356998400', '4']))]
            def write(records):
                with ratings.open('w', newline='', encoding='utf8') as f:
                    w = csv.DictWriter(f, fieldnames=fields)
                    w.writeheader()
                    w.writerows(records)
            write(rows)
            full = prepare(ratings, metadata, [2011, 2012, 2013])
            narrow = prepare(ratings, metadata, [2013])
            write(list(reversed(rows)) + [rows[0]])
            reordered = prepare(ratings, metadata, [2011, 2012, 2013])
            self.assertEqual(full['events'], reordered['events'])
            self.assertEqual(full['book_events'], reordered['book_events'])
            self.assertEqual(full['events']['2013'], narrow['events']['2013'])
            self.assertEqual(sum(map(len, full['events'].values())), 2)
            self.assertEqual(full['labels'], ['Unreviewed', 'X', 'Y'])
            self.assertEqual(sum(full['catalog']), 2)


if __name__ == '__main__':
    unittest.main()
