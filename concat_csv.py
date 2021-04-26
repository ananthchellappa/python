#!/usr/bin/env python3

# usage : python3 script.py <filelist> > output.csv

import pandas as pd
import sys

just_begun = True

for arg in sys.argv[1:] : 
    frame = pd.read_csv( arg )
    if just_begun :
        buffer = frame
        just_begun = False
        headers = set(buffer.columns)
    else :
        buffer = pd.concat( (buffer, frame.loc[:,[col for col in frame.columns if not col in headers]] ), axis=1 )
    headers = set( frame.columns )
    
buffer.to_csv( sys.stdout , index=False)

