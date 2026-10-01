"""Rebuild omitted data caches with the original preprocessing functions."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', choices=['books', 'yelp'])
    args = parser.parse_args()
    if args.dataset == 'books':
        from experiments.validation.amazon_books_categories import prepare
        data = ROOT / 'data/Amazon/Amazon Books Reviews'
        paths = [data / 'Books_rating.csv', data / 'books_data.csv']
        out = ROOT / 'outputs/amazon_books_categories_v2/prepared.json'
    else:
        data = ROOT / 'data/Yelp Dataset'
        paths = [data / 'yelp_academic_dataset_business.json',
                 data / 'yelp_academic_dataset_review.json']
        out = ROOT / 'outputs/data_suitability_audit/audit.json'
    missing = [str(p.relative_to(ROOT)) for p in paths if not p.is_file()]
    if missing:
        parser.error('Dataset files are not bundled. Put files here first: ' + ', '.join(missing))
    if args.dataset == 'books':
        payload = prepare(paths[0], paths[1], [2011, 2012, 2013])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload), encoding='utf8')
        print('Prepared Books:', len(payload['labels']), 'categories;',
              {year: len(values) for year, values in payload['events'].items()})
    else:
        from experiments.validation.audit_available_data import main as prepare_yelp
        prepare_yelp()
    print('Cache:', out)


if __name__ == '__main__':
    main()
