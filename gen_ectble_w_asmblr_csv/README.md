# Python xlsx handler

python 3.10

Get the new xlsx table from csv file filtered by RULE_LIST 


### how to run

- Basic command

```sh
  python main.py CSV_FILENAME RULE_LIST
```

  example:

```sh
  python main.py csv_file.csv "(VDD!=2.9;TEMP>-30)"
```

- Add Mean Value on Table (Optional)
 
  You can get the result by appending corresponding name of string. 

```sh
  python main.py CSV_FILENAME RULE_LIST mean
```

- Add Standard Deviation Value on Table (Optional)

```sh
  python main.py CSV_FILENAME RULE_LIST std_dev
```

### Rule Description

|    |Name| Op | Value | Expression | Description |
|----|----| ---| ----- | ---------- | ----------- |
| 1  |TEMP|  < |   10  |  TEMP < 10 | Filter each value that TEMP value is less than 10 |
| 2 |TEMP|  <= |   10  |  TEMP <= 10 | Filter each value that TEMP value is equal to or less than 10 |
| 3  |TEMP|  > |   10  |  TEMP > 10 | Filter each value that TEMP value is greater than 10 |
| 4  |TEMP|  >= |   10  |  TEMP >= 10 | Filter each value that TEMP value is greater than or equal to 10 |
| 5  |TEMP|  = |   10  |  TEMP = 10 | Filter each value that TEMP value is equal to 10 |
| 6  |TEMP|  != |   10  |  TEMP !=s 10 | Filter each value that TEMP value is not equal to 10 |

### Set of Rules

- AND operation

  just connect 2 rules with ";"

  ```sh
    Rule;Rule
  ```

- OR operation

  Enclose a set of rules in parentheses

  ```sh
    (Rule;Rule)
  ```

### Breakout

|     | Expression | Description |
|---- | ---------- | ----------- |
| 1   |    L        | For each unique value of L, create a separate EC Table and EC w Links type sheet |
|2    | L, condition | The comma after the variable name indicates that this is a breakout spec - you must use the condition to select values and then generate additional sheets for each value |

