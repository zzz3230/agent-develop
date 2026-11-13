import unittest

import lib_55ce5eb3 as m


class T(unittest.TestCase):
    def test_lifo(self):
        q = m.Q(2)
        q.a(1)
        q.a(2)
        self.assertEqual(q.b(), 2)


if __name__ == '__main__':
    unittest.main()
