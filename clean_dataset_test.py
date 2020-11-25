from clean_dataset import *
import numpy as np
import pandas as pd
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

class Test_numeric_if_cleaned( unittest.TestCase ) :

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


class Test_get_string_outliers( unittest.TestCase ) :

    def setUp( self ) :
        # https://archive.ics.uci.edu/ml/machine-learning-databases/autos/imports-85.data
        headers=["symboling","normalized-losses","make","fuel-type","aspiration","num-of-doors","body-style","drive-wheels","engine-location","wheel-base","length","width","height","curb-weight","engine-type","num-of-cylinders","engine-size","fuel-system","bore","stroke","compression-ratio","horsepower","peak-rpm","city-mpg","highway-mpg","price"]
        df = pd.read_csv( "DATA/imports-85.data", names=headers)
        # self.tc_short = df['engine-type']
        self.tc_short = df['num-of-doors']

    def test_very_short( self ) :
        testcase = self.tc_short
        expected = { "?" : "Suspiciously low string length"}
        self.assertEqual( get_string_outliers(testcase), expected )

class Test_find_numeric_columns( unittest.TestCase ) :

    def setUp( self ) :
        # https://archive.ics.uci.edu/ml/machine-learning-databases/autos/imports-85.data
        headers=["symboling","normalized-losses","make","fuel-type","aspiration","num-of-doors","body-style","drive-wheels","engine-location","wheel-base","length","width","height","curb-weight","engine-type","num-of-cylinders","engine-size","fuel-system","bore","stroke","compression-ratio","horsepower","peak-rpm","city-mpg","highway-mpg","price"]
        df = pd.read_csv( "DATA/imports-85.data", names=headers)
        self.df1 = df
        # https://www.kaggle.com/jinxbe/wnba-player-stats-2017
        self.df2 = pd.read_csv( "DATA/WNBA Stats.csv")

    def test_wnba_experience( self ) :
        testcase = self.df2
        expected = ['Experience']
        self.assertEqual( find_numeric_columns(testcase), expected )

    def test_cars( self ) :
        testcase = self.df1
        expected = ['normalized-losses', 'bore', 'stroke', 'horsepower', 'peak-rpm', 'price']
        self.assertEqual( find_numeric_columns(testcase), expected )

    
class Test_get_ID_col( unittest.TestCase ) :

    def setUp( self ) :
        # https://www.kaggle.com/jinxbe/wnba-player-stats-2017
        self.df = pd.read_csv( "DATA/WNBA Stats.csv")
        # https://archive.ics.uci.edu/ml/machine-learning-databases/autos/imports-85.data
        headers=["symboling","normalized-losses","make","fuel-type","aspiration","num-of-doors","body-style","drive-wheels","engine-location","wheel-base","length","width","height","curb-weight","engine-type","num-of-cylinders","engine-size","fuel-system","bore","stroke","compression-ratio","horsepower","peak-rpm","city-mpg","highway-mpg","price"]
        self.df1 = pd.read_csv( "DATA/imports-85.data", names=headers)

    def test_wnba_name( self ) :
        testcase = self.df
        expected = 'Name'
        self.assertEqual( get_ID_col(testcase), expected )

    def test_cars( self ) :
        testcase = self.df1
        expected = 'make'
        self.assertEqual( get_ID_col(testcase), expected )        

class Test_clean_num_col ( unittest.TestCase ) :

    def setUp( self ) :
        # https://www.kaggle.com/jinxbe/wnba-player-stats-2017
        self.df = pd.read_csv( "DATA/WNBA Stats.csv")
        # https://archive.ics.uci.edu/ml/machine-learning-databases/autos/imports-85.data
        headers=["symboling","normalized-losses","make","fuel-type","aspiration","num-of-doors","body-style","drive-wheels","engine-location","wheel-base","length","width","height","curb-weight","engine-type","num-of-cylinders","engine-size","fuel-system","bore","stroke","compression-ratio","horsepower","peak-rpm","city-mpg","highway-mpg","price"]
        self.df1 = pd.read_csv( "DATA/imports-85.data", names=headers)

    def test_cars( self ) :
        testcase = self.df1['normalized-losses']
        expected = 41   # number of NaN in the series
        self.assertEqual( clean_numeric_col(testcase).isna().sum(), expected )
    
    def test_wnba_experience( self ) :
        testcase = self.df['Experience']
        expected = 0
        self.assertEqual( clean_numeric_col(testcase).isna().sum(), expected )

pdb.set_trace()
unittest.main()
