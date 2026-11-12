import unittest
import lib_ca1bf34c as m


class Hidden(unittest.TestCase):
    def test_behavior(self):
        for n, text in [(574, 'DLXXIV'), (462, 'CDLXII'), (2172, 'MMCLXXII'), (1180, 'MCLXXX'), (2331, 'MMCCCXXXI'), (945, 'CMXLV'), (2048, 'MMXLVIII'), (1782, 'MDCCLXXXII'), (3853, 'MMMDCCCLIII'), (2511, 'MMDXI'), (3349, 'MMMCCCXLIX'), (2061, 'MMLXI'), (2028, 'MMXXVIII'), (1662, 'MDCLXII'), (3428, 'MMMCDXXVIII'), (3320, 'MMMCCCXX'), (1708, 'MDCCVIII'), (2646, 'MMDCXLVI'), (2710, 'MMDCCX'), (1541, 'MDXLI'), (1858, 'MDCCCLVIII'), (2872, 'MMDCCCLXXII'), (1934, 'MCMXXXIV'), (1108, 'MCVIII'), (2469, 'MMCDLXIX'), (3258, 'MMMCCLVIII'), (3581, 'MMMDLXXXI'), (3128, 'MMMCXXVIII'), (2836, 'MMDCCCXXXVI'), (3135, 'MMMCXXXV'), (6, 'VI'), (1549, 'MDXLIX'), (1799, 'MDCCXCIX'), (1076, 'MLXXVI'), (1673, 'MDCLXXIII'), (3237, 'MMMCCXXXVII'), (2226, 'MMCCXXVI'), (1067, 'MLXVII'), (898, 'DCCCXCVIII'), (2841, 'MMDCCCXLI'), (787, 'DCCLXXXVII'), (2828, 'MMDCCCXXVIII'), (3511, 'MMMDXI'), (1640, 'MDCXL'), (3441, 'MMMCDXLI'), (1601, 'MDCI'), (2122, 'MMCXXII'), (1525, 'MDXXV'), (3579, 'MMMDLXXIX'), (567, 'DLXVII'), (3726, 'MMMDCCXXVI'), (1384, 'MCCCLXXXIV'), (2364, 'MMCCCLXIV'), (2479, 'MMCDLXXIX'), (1571, 'MDLXXI'), (2677, 'MMDCLXXVII'), (2861, 'MMDCCCLXI'), (847, 'DCCCXLVII'), (3898, 'MMMDCCCXCVIII'), (3484, 'MMMCDLXXXIV'), (2462, 'MMCDLXII'), (2041, 'MMXLI'), (2308, 'MMCCCVIII'), (638, 'DCXXXVIII'), (3854, 'MMMDCCCLIV'), (1863, 'MDCCCLXIII'), (2009, 'MMIX'), (1735, 'MDCCXXXV'), (1651, 'MDCLI'), (350, 'CCCL'), (2277, 'MMCCLXXVII'), (3895, 'MMMDCCCXCV'), (502, 'DII'), (1777, 'MDCCLXXVII'), (3044, 'MMMXLIV'), (557, 'DLVII'), (1751, 'MDCCLI'), (3967, 'MMMCMLXVII'), (2808, 'MMDCCCVIII'), (2981, 'MMCMLXXXI')]:
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
