import pandas as pd
import numpy as np
import re

def get_numeric_outliers( series ) :
    """ pd.Series (truly numeric) --> dict of outlier values (key) and reasons (values )"""
    # currently will not handle NaN
    raw_avg = np.mean( series )
    elems = series.tolist()
    uniques = series.unique().tolist()
    uniques.sort()
    outliers = {}
    orig_num = 0
    current_num = None

    while( current_num != orig_num ) :
        orig_num = len( outliers )
        done = False
        # process from bottom up
        while (not done and uniques) :
            suspect = uniques[0]
            subset = list( filter( (suspect).__ne__, elems) )  # all but this one
            abs_dists = np.asarray( [abs(x-raw_avg) for x in subset ] )
            # really need to DRY these into a separate function :(
            if abs(suspect - raw_avg) > abs_dists.mean() + 3 * abs_dists.std() :
                outliers[suspect] = "Lower abs dist 3 sigma from mean-clean-avg-dist"
                uniques = uniques[1:]
                elems = subset[:]
                raw_avg = np.mean( elems )
            else :
                done = True   

        done = False
        # process from top down (this are the largest elements)
        while ( not done and uniques) :
            suspect = uniques[-1]
            subset = list( filter( (suspect).__ne__, elems) )  # all but this one
            abs_dists = np.asarray( [abs(x-raw_avg) for x in subset ] )
            if suspect - raw_avg > abs_dists.mean() + 3 * abs_dists.std() :
                outliers[suspect] = "Upper abs dist 3 sigma from mean-clean-avg-dist"
                uniques = uniques[:-1]
                elems = subset[:]
                raw_avg = np.mean( elems )
            else :
                done = True
        current_num = len( outliers )

    # now look at counts
    # rem = pd.Series( elems )  # may not be a good idea. Consider : 10, bunch of 11's - 10 is an outlier, but..

    if len( outliers ) > 0 :
        return outliers
    else :
        return None

def is_numeric_if_cleaned( series ) :
    """ pd.Series --> True if series can be cast as numeric - looking at three most frequent members"""
    # we get rid of , and space and $ and ?. 
    # All we are saying is whether it is worth processing this column as numeric
    if pd.api.types.is_numeric_dtype( series.dtypes ) :
        return True
    # now we know we're dealing with strings
    vcs = series.value_counts()
    for i in range(3) :
        candidate = vcs.index[i]
        candidate = re.sub( '[? $,]', '', candidate )
        try :
            float( candidate )
            return True
        except ValueError :
            pass
    return False

def get_string_outliers( series ) :
    """ pd.Series --> dict of outlier values (keys) and reasons (values)"""
    vcs = series.value_counts()
    mu = np.mean( vcs )
    std = np.std( vcs )
    outliers = {}
    done = False
    start = -1
    while not done :
        if vcs[start] < mu - 3 * std :
            outliers[ vcs.index[start] ] = "Suspiciously low count"
        else :
            done = True
        start -= 1
    # now look at lengths
    done = False
    lengths = series.apply( len )
    words = series.unique()
    w_ls = pd.Series(words).apply( len )
    s_df = pd.DataFrame( {'words' : words, 'lengths' : w_ls} )
    vcs = lengths.value_counts()
    mu = np.mean( lengths )
    std = np.std( lengths )
    start = -1
    while not done :
        if vcs.index[start] < mu - 3 * std :     # since we care about the actual length, not the count..
            for candidate in s_df.loc[ s_df['lengths'] == vcs.index[start] , 'words'] :
                if candidate in outliers.keys() :
                    outliers[ candidate ] += ", Suspiciously low string length"
                else :
                    outliers[ candidate ] = "Suspiciously low string length"
        else :
            done = True
        start -= 1

    if len( outliers ) > 0 :
        return outliers
    else :
        return None


# given a dataframe, report the outliers in each column
# default is preview mode. User has to set update=True
def clean_dataset( df_in , update=False ) :
    """ dataframe, bool --> nothing (strings printed)"""
    df = df_in.copy()   # later we can optimize
    df.replace( '?', np.NaN, inplace=True )
    for col in df.columns :
        if df[col].isna( ).value_counts( normalize=True )[False] < 0.95 :    # more then 5%
            print( "Dropping Column : {}".format( col ) )
            df.drop( axis='columns', columns=[col] , inplace=True)
            continue
        else : # drop only the rows
            print( "Dropping rows from {}".format( col ) )
            df.dropna( axis='index', subset=[col], inplace=True )
        if pd.api.types.is_numeric_dtype( df[col].dtypes ) :    # is numeric already
            outs = get_numeric_outliers( df[col] )
        else :
            if is_numeric_if_cleaned( df[col] ) :
                df[col] = df[col].str.replace('[? $,]', '' )    # replace
                # recast (try/except)
                try :
                    df[col] = df[col].astype( 'float' )
                    outs = get_numeric_outliers( df[col] )
                except ValueError as e :
                    print( "With {}, still an issue with {}".format( col, e) )  # test : have '!' as an entry
            else : # dealing with strings now
                pass