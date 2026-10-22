import sqlite3
import unittest
from search import connect, load, mrr, search


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.db = connect(":memory:")
        load(self.db, [{"id":"1","name":"Bridge Inspector","body":"bridge report","state":"ON"},
                       {"id":"2","name":"Bridge Supplier","body":"bridge steel","state":"QC"},
                       {"id":"3","name":"Bridge Office","body":"bridge notices","state":"ON"}])

    def tearDown(self):
        self.db.close()

    def test_filters_and_cursor(self):
        first = search(self.db, "bridge", {"state":"ON"}, limit=1)
        second = search(self.db, "bridge", {"state":"ON"}, limit=1, cursor=first["next_cursor"])
        self.assertNotEqual(first["results"][0]["id"], second["results"][0]["id"])
        self.assertIsNone(second["next_cursor"])

    def test_relevance_and_invalid_cursor(self):
        self.assertEqual(mrr(self.db, [{"query":"inspector","expected_id":"1"}]), 1)
        with self.assertRaises(ValueError):
            search(self.db, "bridge", cursor="invalid")

