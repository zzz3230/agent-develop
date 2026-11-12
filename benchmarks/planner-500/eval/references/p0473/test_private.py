import unittest

import lib_cc2ae2d1 as m


class Private(unittest.TestCase):
    def test_lowercase_input(self):
        self.assertEqual(m.initials('анна мария ли'), 'А. М. Л.')

