import unittest

import lib_7c687802 as m


class Private(unittest.TestCase):
    def test_lowercase_input(self):
        self.assertEqual(m.initials('анна мария ли'), 'А. М. Л.')

