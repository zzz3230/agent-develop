import unittest
import lib_4292b1c7 as m


class Hidden(unittest.TestCase):
    def test_behavior(self):
        for n, text in [(3830, 'MMMDCCCXXX'), (164, 'CLXIV'), (2326, 'MMCCCXXVI'), (713, 'DCCXIII'), (1803, 'MDCCCIII'), (119, 'CXIX'), (2132, 'MMCXXXII'), (1263, 'MCCLXIII'), (391, 'CCCXCI'), (3927, 'MMMCMXXVII'), (2911, 'MMCMXI'), (3657, 'MMMDCLVII'), (777, 'DCCLXXVII'), (3387, 'MMMCCCLXXXVII'), (1819, 'MDCCCXIX'), (3699, 'MMMDCXCIX'), (1321, 'MCCCXXI'), (38, 'XXXVIII'), (1782, 'MDCCLXXXII'), (2863, 'MMDCCCLXIII'), (1994, 'MCMXCIV'), (2151, 'MMCLI'), (3882, 'MMMDCCCLXXXII'), (1023, 'MXXIII'), (1441, 'MCDXLI'), (56, 'LVI'), (1602, 'MDCII'), (890, 'DCCCXC'), (1595, 'MDXCV'), (3765, 'MMMDCCLXV'), (1109, 'MCIX'), (2787, 'MMDCCLXXXVII'), (3555, 'MMMDLV'), (384, 'CCCLXXXIV'), (3875, 'MMMDCCCLXXV'), (3184, 'MMMCLXXXIV'), (3074, 'MMMLXXIV'), (1537, 'MDXXXVII'), (2820, 'MMDCCCXX'), (3775, 'MMMDCCLXXV'), (1273, 'MCCLXXIII'), (3086, 'MMMLXXXVI'), (3743, 'MMMDCCXLIII'), (3903, 'MMMCMIII'), (3114, 'MMMCXIV'), (2350, 'MMCCCL'), (707, 'DCCVII'), (667, 'DCLXVII'), (3818, 'MMMDCCCXVIII'), (106, 'CVI'), (578, 'DLXXVIII'), (2000, 'MM'), (1674, 'MDCLXXIV'), (2299, 'MMCCXCIX'), (1730, 'MDCCXXX'), (3647, 'MMMDCXLVII'), (3833, 'MMMDCCCXXXIII'), (1725, 'MDCCXXV'), (444, 'CDXLIV'), (3438, 'MMMCDXXXVIII'), (888, 'DCCCLXXXVIII'), (778, 'DCCLXXVIII'), (1688, 'MDCLXXXVIII'), (361, 'CCCLXI'), (2092, 'MMXCII'), (3985, 'MMMCMLXXXV'), (1582, 'MDLXXXII'), (990, 'CMXC'), (3283, 'MMMCCLXXXIII'), (2024, 'MMXXIV'), (1451, 'MCDLI'), (1389, 'MCCCLXXXIX'), (1684, 'MDCLXXXIV'), (2660, 'MMDCLX'), (3845, 'MMMDCCCXLV'), (3781, 'MMMDCCLXXXI'), (2624, 'MMDCXXIV'), (1450, 'MCDL'), (1358, 'MCCCLVIII'), (2771, 'MMDCCLXXI')]:
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
