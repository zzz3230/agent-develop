import unittest

import mylib as m


class T(unittest.TestCase):
    def test_count_vowels(self):
        self.assertEqual(m.count_vowels('Umbrella united'), 6)


if __name__ == '__main__':
    unittest.main()
