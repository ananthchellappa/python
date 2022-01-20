#!/usr/bin/env python
# coding: utf-8


import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression 
from sklearn.preprocessing import StandardScaler
from sklearn import metrics
from sklearn.linear_model import Lasso
from warnings import simplefilter
from sklearn.exceptions import ConvergenceWarning
from pandas.core.common import SettingWithCopyWarning
simplefilter("ignore", category=ConvergenceWarning)
simplefilter(action="ignore", category=SettingWithCopyWarning)
import sys



if not sys.argv[1].endswith(".csv") :
    print("Sorry, script only processes CSV files")
    exit(1)
df = pd.read_csv(sys.argv[1])


x_cols_lst = [col for col in df if col.startswith('statistical:')]
y_cols_lst = [col for col in df if not col.startswith('statistical:')]
col_names = pd.Series(x_cols_lst)


result = pd.DataFrame([], columns = ['Variable'])
for y_col in y_cols_lst:
    #get important variables using Lasso
    ls = Lasso(alpha = 0.001)     
    X = df.drop(columns = y_cols_lst)
    y = df[[y_col]]
    sc_X = StandardScaler()
    sc_y = StandardScaler()
    X = sc_X.fit_transform(X)
    y = sc_y.fit_transform(y)
    ls.fit(X, y.flatten()) 
    #print(ls.score(X, y)) 
    #create a temp dataframe ls_ with variables in order of importance
    coefficients = ls.coef_
    importance = np.abs(coefficients)
    ls_ = pd.DataFrame(coefficients)
    ls_['Variable'] = col_names
    ls_['Abs Coeff'] = ls_[0].abs()
    ls_ = ls_.sort_values(by = ['Abs Coeff'], ascending = False)
    #run Regression adding one variable at a time in order of importance and get incremental variance
    cols = ls_['Variable'].to_list()
    y = df[[y_col]]
    variance_ = []
    for i in range(0,len(cols)): 
        col_sub_list = cols[0:i+1]
        X = df[col_sub_list]
        sc_X = StandardScaler()
        sc_y = StandardScaler()
        X = sc_X.fit_transform(X)
        y = sc_y.fit_transform(y)
        ls.fit(X, y.flatten()) 
        variance_.append(ls.score(X, y)*100)
    ls_.reset_index(inplace = True, drop = True)
    ls_['Cum Variance'] = pd.Series(variance_) # this is cumulative variance
    #calculate incremental variance
    ls_[y_col] = ls_['Cum Variance'].diff(1)
    ls_.at[0,y_col] = ls_.at[0,'Cum Variance']
    if result.empty:
        result = ls_[['Variable',y_col]]
    else:
        result = pd.merge(result,ls_[['Variable',y_col]], on = ['Variable'])



result['Variable'] = result['Variable'].str.replace("statistical:","")
out_file_name = '.'.join( sys.argv[1].split('.')[:-1] ) + "_regrpt.csv"
result.to_csv(out_file_name,index= False)

