from lib2to3.pgen2.parse import ParseError
import sys
import re
import ast
import csv
import pandas as pd
from math import isnan


def GetArgs():
    if sys.argv[1].split(".")[-1] != "csv":
        print("Couldn't load excel files except .csv format.")
        sys.exit(1)

    type_args = {}
    type_args["inFormat"] = sys.argv[1].split(".")[-1]
    type_args["inName"] = ".".join(sys.argv[1].split(".")[:-1])
    try:
        type_args["rule"] = sys.argv[2]

        if "mean" in type_args["rule"] or "std_dev" in type_args["rule"]:
            type_args["rule"] = ""
    except:
        type_args["rule"] = ""
    type_args["outFormat"] = "xlsx"
    type_args["outName"] = type_args["inName"]

    type_args["Mean"] = False
    type_args["Std_Dev"] = False

    for i in range(2, len(sys.argv)):
        if sys.argv[i].find("mean") != -1:
            type_args["Mean"] = True
        if sys.argv[i].find("std_dev") != -1:
            type_args["Std_Dev"] = True
    return type_args


def ParseRule(ruleString, mainDF, columns):
    ruleList = []
    breakoutCondition = {"values": "", "variable": ""}
    # find parentheses
    result = re.findall(r'\([^()]+\)', ruleString)
    columnsStr = "|".join(columns)
    for res in result:
        # find condition_list_string
        resTmp = re.findall(r'\(([^()]+)\)', res)[0].split(";")

        # parse condition_list_string
        conditions = []
        for item in resTmp:
            if not item:
                continue
            if item in columns or "," in item:
                # breakoutCondition = GetBreakoutCondition(item, mainDF, columns)
                # continue
                print("invalid breakout condition.")
                sys.exit(2)
            try:
                item2 = re.match(
                    rf"({columnsStr})([><=!]+)(-?\d+(\.\d+)?)", item)
                cond = {}
                cond["variable"] = item2[1]
                cond["symbol"] = item2[2]
                cond["value"] = item2[3]
                conditions.append(cond)
            except:
                try:
                    item2 = re.match(rf"({columnsStr})([><=!]+)(\w+)", item)
                    cond = {
                        "variable": item2[1],
                        "value": item2[3],
                    }
                    if item2[2] == "=" or item2[2] == "==":
                        cond['symbol'] = "include"
                    else:
                        cond['symbol'] = "exclude"
                    conditions.append(cond)
                except:
                # raise(ParseError, "Can't parse filter condition")
                    print("Can't get filter condition (unexpected condition with string)")
                    sys.exit(2)

        ruleList.append(conditions)

        # remove parsed string in parentheses
        ruleString = ruleString.replace(res, "")
    for item in ruleString.split(";"):
        if item:
            if not item:
                continue
            if item in columns or "," in item:
                try:
                    breakoutCondition = GetBreakoutCondition(
                        item, mainDF, columns)
                except:
                    print("Error on parsing breakout condition")
                    sys.exit(2)
                continue
            conditions = []
            try:
                item2 = re.match(
                    rf"({columnsStr})([<>=!]+)(-?\d+(\.\d+)?)", item)
                cond = {
                    "variable": item2[1],
                    "symbol": item2[2],
                    "value": item2[3],
                }
                conditions.append(cond)
            except:
                try:
                    item2 = re.match(rf"({columnsStr})([=!]+)(\w+)", item)
                    cond = {
                        "variable": item2[1],
                        "value": item2[3],
                    }
                    if item2[2] == "=" or item2[2] == "==":
                        cond['symbol'] = "include"
                    else:
                        cond['symbol'] = "exclude"
                    conditions.append(cond)
                except:
                # raise(ParseError, "Can't parse filter condition")
                    print("Can't parse filter condition (unexpected condition with string)")
                    sys.exit(2)
            if conditions != []:
                ruleList.append(conditions)

    return ruleList, breakoutCondition


def GenerateFilterCondition(df, match):
    field = match["variable"]
    op = match["symbol"]
    value = match["value"]

    if op == '<':
        try:
            value = ast.literal_eval(value)
            return df[field] < value
        except:
            print("invalid filter condition")
            sys.exit(2)
    elif op == '>':
        try:
            value = ast.literal_eval(value)
            return df[field] > value
        except:
            print("invalid filter condition")
            sys.exit(2)
    elif op == '<=':
        try:
            value = ast.literal_eval(value)
            return df[field] <= value
        except:
            print("invalid filter condition")
            sys.exit(2)
    if op == '>=':
        try:
            value = ast.literal_eval(value)
            return df[field] >= value
        except:
            print("invalid filter condition")
            sys.exit(2)
    elif op == '=':
        try:
            value = "[" + value + "]"
            value = ast.literal_eval(value)
            return df[field].isin(value)

        except:
            print("invalid filter condition")
            sys.exit(2)
    elif op == '!=' or op =='!' or op == '~':
        try:
            value = "[" + value + "]"
            value = ast.literal_eval(value)
            return ~df[field].isin(value)

        except:
            print("invalid filter condition")
            sys.exit(2)

    elif op == "include":
        try:
            return df[field].str.contains(value, case= false)
        except:
            print("invalid filter condition")
            sys.exit(2)
    elif op == "exclude":
        try:
            return ~df[field].str.contains(value, case= false)
        except:
            print("invalid filter condition")
            sys.exit(2)


def GetBreakoutCondition(item, mainDF, cols):
    breakout = {"values": []}
    columnsStr = "|".join(cols)
    if item in cols:
        valueList = mainDF[item].unique()
        breakout["variable"] = item
    else:
        str = item.split(",")
        valueList = mainDF[str[0]].unique()
        breakout["variable"] = str[0]

        try:
            str2 = re.match(r"([=!]+)(\w+)", str[1])
            if str2.group(1) == "!=" or str2.group(1) == "!":
                valueList = [a for a in valueList if a != str2.group(2)]

            if str2.group(1) == "==" or str2.group(1) == "=":
                valueList = [a for a in valueList if a == str2.group(2)]
            breakout["values"] = valueList
            return breakout
        except:
            pass

        try:
            str2 = re.match(r"([><=!]+)(-?\d+(\.\d+)?)", str[1])

            if str2.group(1) == "!=":
                valueList = [a for a in valueList if a !=
                    ast.literal_eval(str2.group(2))]
            if str2.group(1) == '>':
                valueList = [a for a in valueList if a >
                    ast.literal_eval(str2.group(2))]
            if str2.group(1) == ">=":
                valueList = [a for a in valueList if a >=
                    ast.literal_eval(str2.group(2))]
            if str2.group(1) == '<':
                valueList = [a for a in valueList if a <
                    ast.literal_eval(str2.group(2))]
            if str2.group(1) == ">=":
                valueList = [a for a in valueList if a >=
                    ast.literal_eval(str2.group(2))]
            if str2.group(1) == '<':
                valueList = [a for a in valueList if a <
                    ast.literal_eval(str2.group(2))]
            if str2.group(1) == "<=":
                valueList = [a for a in valueList if a >=
                    ast.literal_eval(str2.group(2))]
        except:
            valueList = [a for a in valueList if a == ast.literal_eval(str[1])]
    breakout["values"] = valueList
    return breakout


def LoadDataFrameFromCSV(fileName):

    with open(fileName, mode='r') as f_csv:
        csv_reader = csv.reader(f_csv)
        units = next(csv_reader)

    # dataFrame
    df = pd.read_csv(fileName, skiprows=1)  # captures the corner data
    df = df.dropna(how= 'all')   # remove all missing values

    # edit column
    cols = df.columns.tolist()
    if "Pass/Fail" not in cols:
        print("Didn't see expected header. Are you sure you not missing some pre-processing steps?")
        sys.exit(2)
    cols.insert(0 , "#" )

    if df.empty:
        print("No data in csv")
        sys.exit(2)
    return df, cols, units


def colnum_string(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string


def DecodeRule(ruleDic):
    if type(ruleDic['value']) == str:
        return ruleDic["variable"] + "=" + str(ruleDic["value"])
    return ruleDic["variable"] + ruleDic["symbol"] + str(ruleDic["value"])


def DecodeRuleList(ruleList):
    result = ""
    for rules in ruleList:
        rule_str = ";".join([DecodeRule(rule) for rule in rules])
        if len(rules) >= 1:
            rule_str = "(" + rule_str + ")"
        result += rule_str
    return result
