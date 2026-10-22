# Search API over Records

A local JSON search service over SQLite FTS5. Index records, rank name matches above body matches, filter by state, role, and organisation type, and paginate with a stable score-and-ID cursor. An evaluation command reports mean reciprocal rank for labeled queries.

```sh
python search.py load examples/records.json --db records.db
python search.py serve --db records.db
python search.py evaluate examples/queries.json --db records.db
python -m unittest discover -s tests -v
```

GET `/search?q=bridge&state=ON&limit=10` returns JSON with `results` and `next_cursor`. The service binds to localhost by default. The input format and evaluation examples are included. FTS5 must be available in the local SQLite build.

