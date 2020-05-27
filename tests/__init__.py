from unittest import TestCase

from pandagg.utils import ordered, equal_queries, equal_search


class PandaggTestCase(TestCase):
    def assertQueryEqual(self, first, second, msg=None):
        self.assertIsInstance(first, dict, msg)
        self.assertIsInstance(second, dict, msg)
        # preserve regular formatting
        if not equal_queries(first, second):
            self.assertEqual(first, second, msg)

    def assertSearchEqual(self, first, second, msg=None):
        self.assertIsInstance(first, dict, msg)
        self.assertIsInstance(second, dict, msg)
        # preserve regular formatting
        if not equal_search(first, second):
            self.assertEqual(first, second, msg)
