import csv
import sys

def get_base_instance(instance):
    parts = instance.split('/')
    for i in range(-1, -3, -1):  # Check the last two parts for bus notation
        if '<' in parts[i]:
            return '/'.join(parts[:i]) + '/' + parts[i].split('<')[0]  # Return the base instance without the bus number
    return instance  # Return the full instance if no bus notation is found

def filter_csv(input_file, output_file):
    with open(input_file, 'r') as infile, open(output_file, 'w', newline='') as outfile:
        reader = csv.DictReader(infile)
        writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
        writer.writeheader()

        seen = {}
        for row in reader:
            instance = row['Instance']
            base_instance = get_base_instance(instance)
            rest_of_row = ','.join([row[field] for field in reader.fieldnames[2:]])  # Capture only what is to the right of the Instance column

            key = (base_instance, rest_of_row)
            if key not in seen:
                seen[key] = True
                writer.writerow(row)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python script.py input.csv output.csv")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    filter_csv(input_file, output_file)
