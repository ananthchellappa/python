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

def find_numeric_columns( df_in ) :
    """ DataFrame --> list of strings (col names) and printed report"""
    # operates on the columns which are not already recognized as numeric
    # based on analysis, which columns should be considered numeric because
    # the majority of entries are numbers? (If diversity of non-numeric values too high (> 20%),
    # report as non-numeric )
    df = df_in.copy()
    numerics = {}
    non_numerics = {}
    candidates = df.select_dtypes( include='object').columns
    for cand in candidates :
        df[cand] = df[cand].str.replace('[$, ]', '') #  hitting space, $ and comma only
        non_num = df.loc[ ~df[cand].str.match( pat='^[+-]?(\d+|\d*\.\d+|\d+\.\d*)([eE][-+]?[0-9]+)?$'), cand]
        l_nn = len( non_num )
        ls_nn = len( set(non_num ) )
        if l_nn < 0.5 * df.shape[0] : # enough numeric items to classify this column
            if ls_nn < 3 or ls_nn < 0.2 * l_nn : # diversity low enough
                numerics[cand] = set(non_num)
            else :
                non_numerics[cand] = set(non_num)
    print("Cleaning done by removing $,space,comma prior to inspection and..\n")
    if len( numerics ) > 0 :
        print( "These columns should be considered numeric and subjected to cleaning :")
        print( " Name  : Entries to address")
        for col in numerics.keys() :
            print( "{} : {}".format( col, ','.join(numerics[col])))
    if len( non_numerics ) > 0 :
        print( "\nThese columns have too many unique non-numeric items and deserve a closer look :")
        for col in non_numerics.keys() :
            print( "{} : {}".format( col, ','.join(non_numerics[col])))
    return list(numerics.keys())

def clean_numeric_col( series ) :
    """pd.Series --> pd.Series"""
    if pd.api.types.is_numeric_dtype( series ) :
        return series
    ser = series.str.replace('[$, ]', '')
    temp = ser.copy()
    temp[ ~temp.str.match( pat='^[+-]?(\d+|\d*\.\d+|\d+\.\d*)([eE][-+]?[0-9]+)?$')] = np.NaN
    temp = temp.astype('float')
    non_num = ser[ ~ser.str.match( pat='^[+-]?(\d+|\d*\.\d+|\d+\.\d*)([eE][-+]?[0-9]+)?$')].unique()
    if len( non_num ) == 1 and temp.min() > 0 and re.match( '^\w+$', non_num[0] ) :
        ser = ser.str.replace( non_num[0], '0' )    # replace the singleton if other values are > 0
                                            # and uses only word characters (not specials like ?)
        ser = ser.astype('float')
    else :
        ser = temp  # since this already has the non-numeric replaced with NaN
    return ser

def rank_in_col( df_in, col, nameCol, name, reverse=False, cleaned=False ) :
    """ DataFrame, string, string, string, bool, bool--> int"""
    # A,B,C,D in 10,10,5,7 => D's rank is 3 since there are two ahead of it
    if cleaned :
        df = df_in
    else :
        df = df_in.copy()
        df[col] = clean_numeric_col( df[col] )
    if reverse :
        return 1 + df.loc[ df[col] < df.loc[df[nameCol] == name,col ].iloc[0] ].shape[0]
    else :
        return 1 + df.loc[ df[col] > df.loc[df[nameCol] == name,col ].iloc[0] ].shape[0]


def get_ID_col( df_in ) :
    """ DataFrame --> string"""
    # return name of the non-numeric column with the highest diversity
    # we do crude checking to see if the column is actually numeric to handle unclean data
    # that is, a truly numeric column with many unique values is read in as string (object) because
    # of a few non-numeric values
    df = df_in.copy()
    name_col = None
    nn_count = 0
    for col in df.select_dtypes( include='object').columns :
        df[col] = df[col].str.replace('[$, ]', '')
        non_num = df.loc[ ~df[col].str.match( pat='^[+-]?(\d+|\d*\.\d+|\d+\.\d*)([eE][-+]?[0-9]+)?$'), col].unique()
        if len( non_num ) > nn_count :
            nn_count = len( non_num )
            name_col = col
    return name_col



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