import pandas as pd
import numpy as np

def get_numeric_outliers( series ) :
    """ pd.Series (truly numeric) --> dict of outlier values (key) and reasons (values )"""
    raw_avg = np.mean( series )
    elems = series.tolist()
    uniques = series.unique().tolist()
    uniques.sort()
    done = False
    outliers = {}

    # process from bottom up
    while (not done and uniques) :
        suspect = uniques[0]
        uniques = uniques[1:]
        subset = list( filter( (suspect).__ne__, elems) )  # all but this one
        abs_dists = np.asarray( [abs(x-raw_avg) for x in subset ] )
        # really need to DRY these into a separate function :(
        if abs(suspect - raw_avg) > abs_dists.mean() + 3 * abs_dists.std() :
            outliers[suspect] = "Lower abs dist 3 sigma from mean-clean-avg-dist"
        else :
            done = True   

    done = False
    # process from top down (this are the largest elements)
    while ( not done and uniques) :
        suspect = uniques[-1]
        uniques = uniques[:-1]
        subset = list( filter( (suspect).__ne__, elems) )  # all but this one
        abs_dists = np.asarray( [abs(x-raw_avg) for x in subset ] )
        if suspect - raw_avg > abs_dists.mean() + 3 * abs_dists.std() :
            outliers[suspect] = "Upper abs dist 3 sigma from mean-clean-avg-dist"
        else :
            done = True

     
    if len( outliers ) > 0 :
        return outliers
    else :
        return None

# given a dataframe, report the outliers in each column
# default is preview mode. User has to set update=True
def clean_dataset( df , update=False ) :
    """ dataframe, bool --> nothing (strings printed)"""
    for col in df.columns :
        if df[col].dtypes == np.number :    # is numeric already
            outs = get_numeric_outliers( df[col] )
        else :
            pass