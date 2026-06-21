#!/bin/bash -eux

# -e : exit on error; -u : error on usage of undefined var; -x : print line prior to execution

# usage : > gen_xlsm_from_transpose csv_from_ADEXL

perl -pi -e 'if( m?^Point/Point? ){ s#/[^,]+##g; s#,Pass,#,Pass/Fail,#;}' $1

perl -pi -e 's/(?<=,)disabled(?=,)//ig;' $1

perl -w ~/perl/make_clean_csv_from_adexl.pl $1
fixed=$(echo $1 | perl -p -e 'chomp; s/\.csv/_fixed.csv/;')

perl -ni -e 's?,[^,.]+\.scs,?,Process,?; print unless /sim\s+err/i;' $fixed

#read -a fileName <<< $( echo $fixed | perl -p -e 's#“(.+?)/?([^/]+)$#$1 $2#;')
filename=$( echo $fixed | perl -p -e 's#^.*?([^/]+)$#$1#;')

# now remove col 1 (0 is the first) (redundant)

# python3 ~/python/del_csv_col.py $1 1 /tmp/$1 # well, this depends on Cadence's idiosyns..
cp -f $fixed /tmp/$filename
perl -pi -e 's/temperature,([^,]+),/TEMP,$1,/;' /tmp/$filename

eng=$(echo $fixed | perl -p -e 'chomp;s/\.csv/_eng.csv/;')

perl -pi -e 's/,(\d*\.\d+|\d\d\d\d*(\.\d*)?)(?=,)/sprintf(",%e",$1)/ge;' /tmp/$filename	# 4/28/21
~/perl/eng_formatter.pl /tmp/$filename > $eng

python3 ~/python/make_xlsm_from_adexl.py $eng

# the old stuff : rm -f /tmp/${fileName[1]}

rm -f /tmp/$filename

# the root-stem of the filename turned out to be useless :)
