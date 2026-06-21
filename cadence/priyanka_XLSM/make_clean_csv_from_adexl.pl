#!/usr/bin/perl -w

# usage : $ > perl -w /path/to/script starter.csv  --> generates starter_fixed.csv
# what it does - "fixes" the nominal corner lines (which have the breakups messed up - like typ_res in the MOM cap column, etc 

use Data::Dumper qw( Dumper );	# debug aid $ p Dumper \@varname
use strict;
use List::MoreUtils qw( indexes );

my %table = (); my $csv; my $sys_c; my $fixed; my @fields; my $buf; my $inits = 1; # init is about Point sweep
my @nom_fields; my @other_fields; my $elem; my $best; my $size; my @nom_text; my $replace;
my $other;

$csv = shift or die "A filename as argument is required\n";
die "File not found :(\n" unless -e $csv;

$sys_c = q{perl -n -i -e 'print if /\S/;' }.$csv;
print STDERR "Removing blank lines..\n";
system( $sys_c );

$fixed = $csv;
$fixed =~ s/\.csv/_fixed.csv/;

# now, get the field numbers for the headers that are spectre_something_model.slib
# something_usage.scs:1
$buf = `head -1 $csv`;
@fields = indexes { $_ =~ /(model.*\..*lib|_usage\.scs(:\d+)?)$/ } split( /,/ , $buf );
$inits = 2 if $buf =~ /^Point/;

# now, for each field, get the LCSS (Longest Common Sub Sequence ) and put that in a table
# note that unix cut starts numbering fields from 1.., which isn't what indexes gives :)
foreach ( @fields ){
	$sys_c = "grep -v -P '^(?:Point,)?Corner|^(?:\\d+,)?nom,' $csv | cut -d',' -f" . ($_ + 1); # '  -- comment quote is to just help NEdit with the syntax highlighting..
			# up to here --- get the lines from the CSV that have don't have have the header or the nominal corner data
	$sys_c .= " | python3 ~/python/long_substr.py";
	$buf = `$sys_c`; # this now has the LCSS
	chomp( $buf );
	$table{$_} = $buf;	# this is still in perl's numbering (staring from 0), so not ordinal..
}

# what do you have now? Eg from run #848
#  DB<9> p Dumper \%table 
#$VAR1 = {
#          '8' => 'maxf_dio_disres',
#          '6' => 'f_mos_moscap_post',
#          '11' => 'nom',
#          '7' => 'maxf_res',
#          '10' => 'beol_typical',
#          '9' => 'maxf_mom'
#        };


# since there is no need to process the nominal corner line(s) on an as needed basis (i.e., one size fits all is fine)
# let's just build up the string now..
# since our assumption of process corner breakup data (text) is contiguous is correct and reasonable

# we want to end up with a perl one liner that will "fix" the nominal corner lines..
# the regex to match will be ^(([^,]+,){$fields[0]}) + <see below> -- with variable interpolated of course..  
# this assumes the first entry in fields is the (perl numbering)
# first field that has the process corner breakup ID. So, if it's 2, it's the third field, 
# so we need to look for two fields before that we don't touch..

# then, we match (to replace) ([^,]+,){($#fields+1)}  -- this is the number of fields to replace..

# before we even get there, build the replacement string first..
# get 'a' nom line
$buf = `grep -P '^(?:\\d+,)?nom' $csv | head -1`;

# now, with the fields from nom - which you can easily get using @fields, you need to figure out
# which of the LCSS table entries best fits each field and that gives you your replacement text..
# you take an entry in @nom_fields (which we haven't built yet) and then get its LCSS with each model field
# and then, compare the length of that with what you get when you use the remaining nominal fields to get an LCSS with the "currently chosen one"

# first, build the @nom_fields -- from $buf
@nom_fields = (split( /,/ , $buf ))[ $fields[0]..$fields[-1] ];
#  DB<10> p Dumper \@nom_fields 
#$VAR1 = [
#          'tt_mos_moscap_pre',
#          'typ_res',
#          'typ_bip',
#          'typ_dio_disres',
#          'typ_mom',
#          'beol_typical'
#        ];
@nom_text = ('') x (1+$#nom_fields);	# poor documentation - should have said what this is used for..

foreach $elem ( @nom_fields ){
	@other_fields = grep { $_ ne $elem } @nom_fields; # this needs to be improved - once something
													# has been assigned on a previous pass, it can't
													# be up for consideration here..
	
	$size = 0;
	foreach ( @fields ){	# a bunch of integers
		$sys_c = q{echo "}.$elem.' '.$table{$_}.q{" | perl -p -e 's/\h+/\n/g;' | python3 ~/python/long_substr.py};
# echo "tt_mos_moscap_pre f_mos_moscap_post" | perl -p -e 's/\h+/\n/g;' | python3 ~/python/long_substr.py
		$buf = `$sys_c`; chomp( $buf );
		if ( length( $buf ) >= $size ) { # we're saying this one is currently chosen... but..
			# now, since we have a candidate, we decide if we're done by looking at the other fields -
			# to see if something other than $elem generates a longer LCSS
			$best = $_;
			$size = length( $buf ); # bad programming :) DRY!!
	
			foreach $other ( @other_fields ) {
				$sys_c = 'echo "' . "$other" . " $table{$best}";
				$sys_c .= q{" | perl -p -e 's/\h+/\n/g;' | python3 ~/python/long_substr.py};
				$buf = `$sys_c`; chomp( $buf );
	
				if( length( $buf ) > $size ) {	# then, reject this candidate
					$size = 0;	# so that some other field will surely take over..
					last;
				}
			}

		} # if 
	} # foreach
	# now, you have the field from the table that should replace this "element"
	$nom_text[$best-$fields[0]] = $elem; # using the "contiguous" argument, first elem of @fields will have the index of the lowest..
	# and that needs to be translated to 0
}

# now for the tricky business of replacing the jumbled stuff in the nominal lines with the good stuff..
# hey, that also needs to be done for the header !!

$sys_c = "perl -p -e 's/^(\\d+,)?nom,(([^,]+,){".($fields[0]-$inits)."})([^,]+,){".($#fields+1).'}/$1nom,$2' . join( "," , @nom_text ) . ",/;' $csv";
$sys_c .= " > $fixed";	#  doing an overwrite here..
print STDERR "Fixing nominal corner lines\n";
system( $sys_c );


$replace = '';
foreach ( @fields ){
	$replace .= $table{$_} . ',' ;
#now, make multiple passes through the file fixing one field at a time..
# might as well get it down now :)
	# $sys_c = "perl -p -i -e 's/((?:[^,]*,){$_})(".'\w'."*)$table{$_},/" . '$1$2,' .  "/;' $fixed"; 
	# above was okay as long as we didn't condense to zilch
	$sys_c = "perl -p -i -e 's/^((?:[^,]*,){$_})(" . '\w' . "*)$table{$_},/sprintf(" . q{"$1%s,", ($2 eq "")?"*":$2 )/e;' } . $fixed; #'
	system( $sys_c );
}

# now to fix the header as well..
$sys_c = "perl -p -i -e 's/^(Point,)?Corner,(([^,]+,){".($fields[0]-$inits)."})([^,]+,){".($#fields+1).'}/$1Corner,$2' . $replace . "/;' $fixed";
print STDERR "Fixing header\n";
system( $sys_c );

print STDERR "\nDone.. output in $fixed\n\n";
