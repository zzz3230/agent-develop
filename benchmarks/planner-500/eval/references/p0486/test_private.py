import unittest

import lib_275f75aa as m


class Private(unittest.TestCase):
    def test_only_empty(self):
        result = m.x1('city,amount\nLima,\nRiga,4\n')
        self.assertEqual(result, {'Lima': 0, 'Riga': 4})
        self.assertTrue(all(type(v) is int for v in result.values()))

