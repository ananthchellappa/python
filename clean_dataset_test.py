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

    def test_double(self) :
        data = np.array([10,10,11,12,13,10,1,11,11,14,14,15,19,20,17,17,30])
        testcase = pd.Series( data )
        expected = { 30 : "Upper abs dist 3 sigma from mean-clean-avg-dist",
                    1 : "Lower abs dist 3 sigma from mean-clean-avg-dist"}
        self.assertEqual( get_numeric_outliers(testcase), expected )

    # def test_nan(self) :
    #     data = np.array([10,10,11,12,13,10,1,11,11,14,14,15,19,20,17,17,np.NaN])
    #     testcase = pd.Series( data )
    #     expected = { 30 : "Upper abs dist 3 sigma from mean-clean-avg-dist",
    #                 1 : "Lower abs dist 3 sigma from mean-clean-avg-dist"}
    #     self.assertEqual( get_numeric_outliers(testcase), expected )

    def test_if_cleaned( self ) :
        data = np.array(['$100', '1.1', '2', '3', '4', '4', '4', '?'])
        testcase = pd.Series( data )
        expectd = True
        self.assertEqual( is_numeric_if_cleaned( testcase), expectd )

    def test_if_cl_strs( self ) :
        data = np.array(['$100', 'one', 'two', 'one', 'two', 'three', 'four', 'four', '4'])
        testcase = pd.Series( data )
        expectd = False
        self.assertEqual( is_numeric_if_cleaned( testcase), expectd )

pdb.set_trace()
unittest.main()
