import unittest

import lib_58933cde as m


class Private(unittest.TestCase):
    def test_upper_only(self):
        self.assertEqual(m.count_vowels('AEIOU'), 5)

    def test_none(self):
        self.assertEqual(m.count_vowels('rhythm'), 0)

