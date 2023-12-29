
import pandas as pd
import tools
from DataFrame.ECdataStream import ECDataFrame

class MainDataFrame(pd.DataFrame):
  
  def __init__(self, data=None, index=None, columns=None, unitList=[], tableName = "Corners", **kwargs):
    super(MainDataFrame, self).__init__(data=data, index=index, columns=columns, **kwargs)
    self.tableName = tableName
    self.tableUnit = unitList
    
    self.options = {
      "header": False,
      "index": True,
      "startrow": 6, 
      "startcol": 1
    }
  
  # Add Header to excel sheet
  def AddHeaders(self, writer, valueList):
    worksheet = writer.sheets[self.tableName]	# the secret sauce that makes the macros ready to go!
    
    columns = self.columns.tolist()
    columns.insert(0, "#")
    headers = list(map(lambda x : { 'header' : x } , columns))
    
    worksheet.add_table( 
      self.options["startrow"] - 1,
      1,
      self.options["startrow"] - 1 + self.shape[0], 
      self.shape[1]+1, {
      'columns' : headers,
      'header_row' : True,
      'autofilter' : True,
      'style' : 'Table Style Light 18',
    })

    mapper = {"Mean": "101", "Std_Dev": "107"}
    ind_pf = columns.index('Pass/Fail')

    for i, header in enumerate( columns ) :
      worksheet.write( self.options["startrow"] - 3,i+1 , header ) # header (yes, again)
      if i > 0 :
          worksheet.write( 0,i+1 , "=ROUND(SUBTOTAL(104, Table2[" + header + "]), 2)" ) # max
          worksheet.write( 1,i+1 , "=ROUND(SUBTOTAL(105, Table2[" + header + "]), 2)" ) # min
          if i > ind_pf:
            for j in range(0, len(valueList)):
              worksheet.write(2 + j, i+1, "=ROUND(SUBTOTAL(" + mapper[valueList[j]] + ", Table2[" + header + "]), 2)") 

          worksheet.write( self.options["startrow"] - 2,i+1 , self.tableUnit[i-1] ) # unit
      else :
          worksheet.write( 0,0, "Max" )
          worksheet.write( 1,0, "Min" )
          for j in range(0, len(valueList)):
            worksheet.write(2 + j, 0, valueList[j])

  
    

    # worksheet.write_comment( "A1" , metadata )
    worksheet.set_vba_name('Sheet1') 
    
  def CreateExcelTable(self, writer, tableName = None, options = None):
    if tableName == None:
      tableName = self.tableName
    else:
      self.tableName = tableName

    valueList = [key for key, val in options.items() if val]
    self.options["startrow"] += len(valueList)
    
    self.to_excel(
      writer, 
      sheet_name = tableName, 
      header = self.options["header"], 
      index = self.options["index"], 
      startrow = self.options["startrow"], 
      startcol = self.options["startcol"]
    )
    
    self.AddHeaders(writer, valueList)
  
  def GetFilteredDataFrame(self, ruleList, tableName = "EC 1"):
    data = self.copy()
    # cond = pd.DataFrame({'col': [False] * self.dataStream.shape[0]})
    for rules in ruleList:
      cond = tools.GenerateFilterCondition(data, rules[0])
      for i in range(1, len(rules)):
        cond = cond | tools.GenerateFilterCondition(data, rules[i])
      data= data[cond]
      
      
    cols = self.columns.tolist()
    cols.insert( 0 , "#" )
    
    return ECDataFrame(data, tableName = tableName, unitList = self.tableUnit)
  
  # def AddHeaders(self, writer):
  