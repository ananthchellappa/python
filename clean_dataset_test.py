from clean_dataset import *
import numpy as np
import pdb

import unittest

class Test_get_numeric_outliers( unittest.TestCase ) :

    def test_basic(self) :
        data = np.array([10,10,11,12,13,10,11,11,14,14,1,15,19,20,17,17,])
        testcase = pd.Series( data )
        expected = {1 : "Lower abs dist 3 sigma from mean-clean-avg-dist"}
        self.assertEqual( get_numeric_outliers(testcase), expected )

    def test_max(self) :
        data = np.array([10,10,11,12,13,10,11,11,14,14,15,19,20,17,17,30])
        testcase = pd.Series( data )
        expected = { 30 : "Upper abs dist 3 sigma from mean-clean-avg-dist"}
        self.assertEqual( get_numeric_outliers(testcase), expected )

pdb.set_trace()
unittest.main()
