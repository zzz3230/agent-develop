import unittest

import lib_1e7810cf as m


class Private(unittest.TestCase):
    def test_negative(self):
        self.assertEqual(m.to_upper('-0.125'), '-0.13')

    def test_integer(self):
        self.assertEqual(m.to_upper('10'), '10.00')

