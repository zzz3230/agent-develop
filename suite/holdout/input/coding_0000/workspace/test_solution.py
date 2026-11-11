import unittest
import solution as m


class T(unittest.TestCase):
    def test_behavior(self):
        self.assertEqual(m.order({'b': ['a'], 'a': [], 'c': ['a']}), ['a', 'b', 'c'])
        with self.assertRaises(ValueError):
            m.order({'a': ['b'], 'b': ['a']})


if __name__ == "__main__":
    unittest.main()
