import unittest
import lib_8865cd30 as m


class Hidden(unittest.TestCase):
    def test_behavior(self):
        for n, text in [(1403, 'MCDIII'), (3858, 'MMMDCCCLVIII'), (3303, 'MMMCCCIII'), (2533, 'MMDXXXIII'), (3331, 'MMMCCCXXXI'), (2428, 'MMCDXXVIII'), (2694, 'MMDCXCIV'), (3688, 'MMMDCLXXXVIII'), (242, 'CCXLII'), (1463, 'MCDLXIII'), (2483, 'MMCDLXXXIII'), (1671, 'MDCLXXI'), (1283, 'MCCLXXXIII'), (2154, 'MMCLIV'), (3708, 'MMMDCCVIII'), (927, 'CMXXVII'), (3589, 'MMMDLXXXIX'), (3166, 'MMMCLXVI'), (3516, 'MMMDXVI'), (3262, 'MMMCCLXII'), (2926, 'MMCMXXVI'), (2569, 'MMDLXIX'), (3102, 'MMMCII'), (3010, 'MMMX'), (1967, 'MCMLXVII'), (1106, 'MCVI'), (3472, 'MMMCDLXXII'), (738, 'DCCXXXVIII'), (3906, 'MMMCMVI'), (3778, 'MMMDCCLXXVIII'), (2451, 'MMCDLI'), (674, 'DCLXXIV'), (2139, 'MMCXXXIX'), (3135, 'MMMCXXXV'), (2932, 'MMCMXXXII'), (2206, 'MMCCVI'), (419, 'CDXIX'), (3629, 'MMMDCXXIX'), (1373, 'MCCCLXXIII'), (2116, 'MMCXVI'), (2644, 'MMDCXLIV'), (3051, 'MMMLI'), (1620, 'MDCXX'), (1474, 'MCDLXXIV'), (1219, 'MCCXIX'), (2764, 'MMDCCLXIV'), (3168, 'MMMCLXVIII'), (2832, 'MMDCCCXXXII'), (3325, 'MMMCCCXXV'), (2075, 'MMLXXV'), (3675, 'MMMDCLXXV'), (1901, 'MCMI'), (3762, 'MMMDCCLXII'), (2868, 'MMDCCCLXVIII'), (3551, 'MMMDLI'), (380, 'CCCLXXX'), (1005, 'MV'), (3008, 'MMMVIII'), (1886, 'MDCCCLXXXVI'), (2899, 'MMDCCCXCIX'), (3390, 'MMMCCCXC'), (3744, 'MMMDCCXLIV'), (2382, 'MMCCCLXXXII'), (2726, 'MMDCCXXVI'), (208, 'CCVIII'), (2811, 'MMDCCCXI'), (64, 'LXIV'), (3056, 'MMMLVI'), (692, 'DCXCII'), (3277, 'MMMCCLXXVII'), (3076, 'MMMLXXVI'), (171, 'CLXXI'), (3852, 'MMMDCCCLII'), (3543, 'MMMDXLIII'), (3881, 'MMMDCCCLXXXI'), (3175, 'MMMCLXXV'), (184, 'CLXXXIV'), (2993, 'MMCMXCIII'), (1961, 'MCMLXI'), (3943, 'MMMCMXLIII')]:
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
