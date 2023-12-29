import tools
import pandas as pd
from DataFrame.indexdataStream import IndexDataFrame
from DataFrame.ECdataStream import ECDataFrame
from DataFrame.MaindataStream import MainDataFrame

import warnings
import os
warnings.filterwarnings("ignore","Pandas doesn't allow columns to be created via a new attribute name - see https://pandas.pydata.org/pandas-docs/stable/indexing.html#attribute-access", UserWarning)

def main():
  # Load Argument.
  CMD_ARG = tools.GetArgs()
  
  # load input data from csv file
  inFileName = CMD_ARG["inName"] + "." + CMD_ARG["inFormat"]
  mainDF, cols, units = tools.LoadDataFrameFromCSV(inFileName)
   # Parse Rules
  RULELIST, BREAKOUT = tools.ParseRule(CMD_ARG["rule"], mainDF, cols)
  # Define Output file Name
  outFileName = ".".join([CMD_ARG["outName"], CMD_ARG["outFormat"]])
  
  # Define xlsx writer and workbook
  writer = pd.ExcelWriter(outFileName, engine="xlsxwriter")
  workbook = writer.book
  
  workbookName = ".".join([CMD_ARG["outName"], 'xlsm'])
  
  workbook.filename = workbookName
  
  dir_path = os.path.dirname(os.path.abspath(__file__))
  workbook.add_vba_project(dir_path + '/vbaProject.bin')
  workbook.set_vba_name('ThisWorkbook')
  
  # Define indexDF to manage sheet
  indexDF = IndexDataFrame(columns = ['Originating specifier', 'VAR1', 'Plain', 'w Links'])
  
  options = {key: CMD_ARG[key] for key in ['Mean', 'Std_Dev']}

  # Create mainDF for "Corners" sheet
  mainDF = MainDataFrame(mainDF, unitList = units)
  mainDF.CreateExcelTable(writer, options = options)
  
  # Create mainECDataFrame for main "EC" sheet
  mainECDataFrame = ECDataFrame(unitList = units)
  mainECDataFrame.UpdateWithDF(mainDF, options)
  mainECDataFrame.CreateMainTable(writer, indexDF)
  mainECDataFrame.CreateLinkTable(writer, indexDF)

  if RULELIST or BREAKOUT["values"] != '':
    if len(BREAKOUT["values"]) == 0:  # condition to find breakout is exist
      
      # without Breakout    
      filteredDF = mainDF.GetFilteredDataFrame(RULELIST) # Get Filtered DataFrame by rule list
      filteredECDataFrame = ECDataFrame(unitList = units, tableName = "EC 1") # initialize new EC DataFrame
      
      filteredECDataFrame.UpdateWithDF(filteredDF, options) # update ECDataFrame with filtered dataframe 
      filteredECDataFrame.CreateMainTable(writer, indexDF, tableName =
      "EC 1") 
      filteredECDataFrame.CreateLinkTable(writer, indexDF, tableName =
      "ECL 1")
      
      # Update indexDF with the newly created sheet.
      indexDF.UpdateDF(["Originating specifier"],"",plain = "Plain", ec_wl = "w Links")
      indexDF.UpdateDF([CMD_ARG["rule"]],"",plain = "EC 1", ec_wl = "ECL 1")

      
    else:
      indexDF.UpdateDF(["Originating specifier"], BREAKOUT["variable"],plain = "Plain", ec_wl = "w Links")
      bName = tools.DecodeRuleList(RULELIST) # Get breakout variable
      
      for value in BREAKOUT["values"]:
        # Add breakout condition to rule list
        if type(value) == str:
          newRule = [{"variable": BREAKOUT["variable"], "value": value, "symbol": "include"}]
        else: 
          newRule = [{"variable": BREAKOUT["variable"], "value": str(value), "symbol": "="}]
        newList = RULELIST.copy()
        newList.append(newRule)
        
        breakout = tools.DecodeRule(newRule[0]) # decode breakout condtion to name the EC sheet.
        
        filteredDF = mainDF.GetFilteredDataFrame(newList)
        filteredECDataFrame = ECDataFrame(unitList = units, tableName = "EC " + breakout)
        
        ECTableName = "EC " + breakout
        ECLTableName = "ECL " + breakout
        
        filteredECDataFrame.UpdateWithDF(filteredDF, options)
        filteredECDataFrame.CreateMainTable(writer, indexDF, tableName = ECTableName)
        filteredECDataFrame.CreateLinkTable(writer, indexDF, tableName = ECLTableName)
        
        # Update indexDF
        indexDF.UpdateDF([bName], value, plain = ECTableName, ec_wl = ECLTableName)
        
  # Create indexTable
  indexDF.CreateTable(writer, workbook)
  # print(indexDF)
  writer.close()
  
main()