import unittest
import solution as m


class Hidden(unittest.TestCase):
    def test_behavior(self):
        for n, text in [(650, 'DCL'), (324, 'CCCXXIV'), (2325, 'MMCCCXXV'), (483, 'CDLXXXIII'), (1909, 'MCMIX'), (1248, 'MCCXLVIII'), (2554, 'MMDLIV'), (1748, 'MDCCXLVIII'), (866, 'DCCCLXVI'), (985, 'CMLXXXV'), (397, 'CCCXCVII'), (2759, 'MMDCCLIX'), (3751, 'MMMDCCLI'), (634, 'DCXXXIV'), (3745, 'MMMDCCXLV'), (3621, 'MMMDCXXI'), (37, 'XXXVII'), (3664, 'MMMDCLXIV'), (3151, 'MMMCLI'), (143, 'CXLIII'), (3535, 'MMMDXXXV'), (1981, 'MCMLXXXI'), (1474, 'MCDLXXIV'), (1595, 'MDXCV'), (1905, 'MCMV'), (1477, 'MCDLXXVII'), (1873, 'MDCCCLXXIII'), (1604, 'MDCIV'), (834, 'DCCCXXXIV'), (2418, 'MMCDXVIII'), (2058, 'MMLVIII'), (304, 'CCCIV'), (794, 'DCCXCIV'), (1577, 'MDLXXVII'), (1010, 'MX'), (1197, 'MCXCVII'), (3208, 'MMMCCVIII'), (839, 'DCCCXXXIX'), (1978, 'MCMLXXVIII'), (1879, 'MDCCCLXXIX'), (725, 'DCCXXV'), (1742, 'MDCCXLII'), (131, 'CXXXI'), (2856, 'MMDCCCLVI'), (949, 'CMXLIX'), (3863, 'MMMDCCCLXIII'), (3501, 'MMMDI'), (3183, 'MMMCLXXXIII'), (775, 'DCCLXXV'), (528, 'DXXVIII'), (3512, 'MMMDXII'), (2503, 'MMDIII'), (299, 'CCXCIX'), (1487, 'MCDLXXXVII'), (3721, 'MMMDCCXXI'), (754, 'DCCLIV'), (3673, 'MMMDCLXXIII'), (1501, 'MDI'), (2213, 'MMCCXIII'), (3735, 'MMMDCCXXXV'), (3405, 'MMMCDV'), (3579, 'MMMDLXXIX'), (410, 'CDX'), (3725, 'MMMDCCXXV'), (862, 'DCCCLXII'), (2484, 'MMCDLXXXIV'), (2893, 'MMDCCCXCIII'), (3972, 'MMMCMLXXII'), (2718, 'MMDCCXVIII'), (2920, 'MMCMXX'), (3956, 'MMMCMLVI'), (338, 'CCCXXXVIII'), (3547, 'MMMDXLVII'), (3810, 'MMMDCCCX'), (2384, 'MMCCCLXXXIV'), (3463, 'MMMCDLXIII'), (3129, 'MMMCXXIX'), (421, 'CDXXI'), (3295, 'MMMCCXCV'), (589, 'DLXXXIX')]:
            self.assertEqual(m.to_roman(n), text)
            self.assertEqual(m.from_roman(text), n)
        for bad in ['', 'IC', 'VX', 'IIII', 'xlii', 'MMMM', 'IVI', 'LL', 'A']:
            with self.assertRaises(ValueError):
                m.from_roman(bad)
        for bad in [0, 4000, -1, 2.0, True]:
            with self.assertRaises(ValueError):
                m.to_roman(bad)


if __name__ == "__main__":
    unittest.main()
