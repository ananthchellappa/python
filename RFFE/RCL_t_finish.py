import sys

if len(sys.argv)==1:
    print("You need to specify the text file to work on like in the following model:\n\tpython3 script.py read_RCL_text_file  read_write_clk_period_in_ns [read_clk_period_in_ns]")
    sys.exit(0)
elif len(sys.argv)==2:
    print("You need to specify the read_write_clk_period_in_ns like in the following model:\n\tpython3 script.py read_RCL_text_file  read_write_clk_period_in_ns [read_clk_period_in_ns]")
    sys.exit(0)

end_result = 0
read_write_clk_period_in_ns = float(sys.argv[2])
optional_read_clk_period_in_ns = 0
if len(sys.argv)==4:
    optional_read_clk_period_in_ns = float(sys.argv[3])
else:
    optional_read_clk_period_in_ns = read_write_clk_period_in_ns * 2

command = ''
v = 0
with open(sys.argv[1]) as f:
    for i,line in enumerate(f):
        c = line.split(',')
        command = c[0].strip()
        if command == 'd':
            end_result += float(c[1].strip().replace('_',''))
            v = float(c[1].strip().replace('_',''))
        elif command == 'w':
            end_result += 25 * read_write_clk_period_in_ns
        elif command == 'r':
            end_result += 17 * read_write_clk_period_in_ns +  10 * optional_read_clk_period_in_ns
        elif command == 'ew':
            end_result += 34 * read_write_clk_period_in_ns
        elif command == 'er':
            end_result += 26 * read_write_clk_period_in_ns + 10 * optional_read_clk_period_in_ns

if command=='d':
    end_result -= v
print('{:0.1f} us'.format(end_result/1000.0))
