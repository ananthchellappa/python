#!/usr/bin/perl -w

# usage :
# > eng_formatter.pl whatever.csv
# note, prior work : you MUST ensure signals and "oppoints" are at the end (final fields) in the output fed to the scipt
# meaning - anything like /x10/xamp/whatever MUST be one of the final fields!!
# you can just go to the Outputs Setup pane and drag outputs to the bottom to accomplish this...
# When viewing results, you can hide signals, but you cannot hide oppoints, so... this...

# trying now to add fault-tolerance - ignore non-numeric stuff..

use strict;
use warnings;
# $SIG{__WARN__} = sub { $DB::single = 1 };		# http://www.perlmonks.org/?node_id=640915 -- perl debugger how to break on error

# use Text::CSV;	# didn't work :( -- tried cpan install - failed the ISHIGAKI thing.. *ds!
use Scalar::Util qw( looks_like_number );	# works awesome
use List::Util qw( min max );
use Data::Dumper qw( Dumper );       # debugging aid --- p Dumper \@arrayName

my $infile = shift or die "Must provide a CSV as input\n";
die "Must be a CSV file :) .. that exists :)\n" unless (-e $infile and $infile =~ /\.csv$/ );

# open( INFO, "$infile") or die "Can't read the specfied file\n";

my @fields = split( /,/ , `head -1 $infile` );
my @data = split( /,/ , `sed -n '2p' $infile` );	# get 2nd line of the file
my $column;
my @col; my $finalExp; my $units = '';
my %eNotation = ('-18' => 'a',
				 '-15' => 'f',
				 '-12' => 'p',
				 '-9'  => 'n',
				 '-6'  => 'u',
				 '-3'  => 'm',
				 '3'	=> 'k',
				 '6'	=> 'M',
				 '9'	=> 'G',
				 '12'	=> 'T' );

# now, you read the next line and then decide which fields to actually keep..

my $ix = $#fields;		# going backwards - in this case, it's "know your data... :) "
my $field; my @output = (); my $nu_lin_ct;	# how much numeric data?
while ( $ix ) {
	if( $fields[$ix] =~ m#/#  ){ # this means it's a signal, that we want to get rid of..
		splice( @fields, $ix, 1 );
	} else {
		last;	# you just want to get rid of the junk like /xdut/whatever/whatever
	}
	$ix--;

}

$ix = 1; my $my_clean_cols; my @clean_cols;
foreach $field (@fields ){
	$column = `tail -n +2 $infile | cut -d',' -f$ix,$ix`;
	@col = split( /\n\r?/ , $column );
	# this is to avoid creating a new variable :) It's just how many numeric entries there are
	$column = `cut -d',' -f$ix,$ix $infile | perl -MScalar::Util -nl -e 'chomp; print if Scalar::Util::looks_like_number(\$_);' | wc -l`;

	if( $column > 0  ) {	# if there's even a single numeric entry..
#	print join( "\n", @col );
		$my_clean_cols = `cut -d',' -f$ix,$ix $infile | perl -MScalar::Util -nl -e 'chomp; print if Scalar::Util::looks_like_number(\$_);'`;
		@clean_cols = split( /\n\r?/ , $my_clean_cols );
		$finalExp = expo_anal( @clean_cols );
		if( ! defined( $finalExp ) ){
			print STDERR "time for a break mate :)\n";
		}
		fix_exp( $finalExp, \@col );
		if( defined $eNotation{$finalExp} ){
			$units = $units . ',' . $eNotation{$finalExp};
		} else { $units .= ',';}
	} else {
		$units .= ',';
	}
	if( -1 == $#output ){		# i.e., @output is empty
		@output = @col; # this is a true copy
	} else {
		stitch_CSV( \@output, \@col );
	}
	$ix++;
}

$units =~ s/^,//;
print $units , "\n";
print join( ",", @fields ) , "\n";
print join( "\n", @output ) , "\n";

sub expo_anal {
# array of floats (strings) -> integer
# it takes an array of numbers in scientific notation and returns the appropriate engineering notation exponent
	
	my @in_arr = @_;
	my %expHash = ();
	my $num;
	my $eng_exp;
	foreach $num (@in_arr) {
		# 1e-07 => 100e-09 -- pick the appropriate multiple of 3.. -- the smaller value : -7 --> -9; +7 --> +6

   ### chg 1 ###
		if ( $num ){ # ignore zero values
		
			# you just have to subtract (num % 3) from num
			if( $num =~ /(.+)[eE](.+)/ ){
				$eng_exp = $2 - ($2 % 3 );
			} else {
				$eng_exp = 0;
			}
			if( defined $expHash{$eng_exp} ){
				$expHash{$eng_exp}++;
			} else {
				$expHash{$eng_exp} = 1;
			}
		}
	}
#	return min( keys( %expHash) );		# thought this was a good choice till I was reporting offset current in pA :)

  ### chg 2 ###
 	if (!(keys %expHash)){ # return zero if hash is empty
 		return 0;
 	}
 	else {
		return (sort {$expHash{$b} <=> $expHash{$a} } keys %expHash)[0] 	# sort in descending order
	}
}

sub fix_exp {
# integer, ref to array -> nothing ( it mutates array1 )
# it uses the provided integer to process every element so that if given 9 and 1e11, will put out 100e9
	my $unit = 10**$_[0];
	my $elem;
	foreach $elem ( @{$_[1]} ){
		if( looks_like_number( $elem ) ){
			$elem = sprintf( "%.3f" , $elem/$unit );	# processes by reference - looks like $elem is unique, but no..
		} else {
			$elem = "NaN";
		}
	}
}

sub stitch_CSV {
# ref to array1, ref to array2 -> nothing (it mutates array1 )
# it dumps array2 into array1 in CSV fashion that is ( (1,2,3), (4,5,6) ) -> ( '1,4', '2,5' , '3,6' )
# also supports the empty array
	my @add_arr = @{$_[1]};
	my $index = 0;
	foreach ( @{$_[0]} ){
		if( -1 == $#add_arr) {  #empty
			${$_[0]}[$index] = ${$_[0]}[$index] . ',';
		} else {
			${$_[0]}[$index] = ${$_[0]}[$index] . ',' . $add_arr[$index];
		}
		$index++;
	}
}

