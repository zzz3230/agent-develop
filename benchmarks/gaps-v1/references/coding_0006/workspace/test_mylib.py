import unittest

import mylib as m


class T(unittest.TestCase):
    def test_initials(self):
        self.assertEqual(m.initials('Иван Петров'), 'И. П.')

    def test_normalize_spaces(self):
        self.assertEqual(m.normalize_spaces('  Анна   Ли '), 'Анна Ли')


if __name__ == '__main__':
    unittest.main()
