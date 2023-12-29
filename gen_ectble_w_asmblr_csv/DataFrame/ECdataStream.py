import pandas as pd
from math import isnan
import re
import tools
class ECDataFrame(pd.DataFrame):
  
  def __init__(self, data=None, index=None, columns=None, unitList=[], tableName = "EC Table", **kwargs):
    super(ECDataFrame, self).__init__(data=data, index=index, columns=columns, **kwargs)
    
    self.tableUnit = unitList
    self.tableName = tableName
    self.options = {
      "header": False,
      "index": True,
      "startrow": 3, 
      "startcol": 1
    }
  
  # Update ECDataFrame from dataframe  
  def UpdateWithDF(self, df, options):
    tableName = self.tableName
    
    cols = df.columns.tolist()
    cols.insert(0, "#")
    ind_pf = cols.index('Pass/Fail')
    ec_cols = ['Spec', 'Units', 'Min','Typ', 'Max', 'Min Corner', 'Max Corner']

    additional_cols = [x for x in options if options[x] is True ]
    ec_cols[5:5] = additional_cols

    ecDataFrame = pd.DataFrame(columns=ec_cols)
        
    units = self.tableUnit
    
    min_rows = []
    max_rows = []
    for i, header in enumerate(cols[ind_pf+1:]): 
      
      maxv= df[header].max()
      if str == type(maxv) or isnan(maxv):
        maxc = "no data"
        max_rows.append(float("NaN")) 
      else:
          maxc = df[df[header] == maxv].iloc[0,0:ind_pf-1].to_string()
          maxc = re.sub( "\n", "; " , maxc )
          maxc = re.sub("\s+","=",maxc)
          maxc = re.sub(";=",";",maxc)
          max_rows.append(df.loc[df[header] == maxv].index[0])

      minv = df[header].min()
      if str == type(minv) or isnan( minv ) :
          minc = "no data"
          min_rows.append( float("NaN") )
      else : 
          minc = df[ df[header] == minv ].iloc[0,0:ind_pf-1].to_string()
          minc = re.sub( "\n", "; " , minc )
          minc = re.sub("\s+","=",minc)
          minc = re.sub(";=",";",minc)
          min_rows.append( df.loc[ df[header] == minv ].index[0] )
      
      typ = ''

      option = {
        'Spec' : header , 
        'Units' : units[ind_pf + i],
        'Typ' : typ,  
        'Min' : minv, 
        'Max' : maxv, 
        'Min Corner' : minc, 
        'Max Corner' : maxc,
      }

      if "Mean" in additional_cols:
        meanv = df[header].mean()
        option["Mean"] = round(meanv, 2)
      if "Std_Dev" in additional_cols:
        stdDev = df[header].std()
        option["Std_Dev"] = round(stdDev, 2)
      
      
      ecDataFrame = pd.concat([
          ecDataFrame, 
          pd.DataFrame.from_records(
              [option])], ignore_index=True)
    
    self.__dict__.update(ecDataFrame.__dict__)
    self.tableUnit = units[ind_pf:]
    self.tableName = tableName
    
    self.min_rows = min_rows
    self.max_rows = max_rows
    self.ind_pf = ind_pf
    
  def CreateMainTable(self, writer, indexDF, tableName = "EC Table"):
    indexDF.UpdateECList(tableName)
    
    self.to_excel( 
      writer, 
      sheet_name= tableName, 
      header=self.options["header"], 
      index = self.options["index"], 
      startrow = self.options["startrow"], 
      startcol = self.options["startcol"] 
    )
    
    name = self.tableName
    worksheet = writer.sheets[name]

    cols = ['#']
    cols.extend(self.columns.tolist())
    
    headers = list(map(lambda x : {'header':x}, cols))  
    worksheet.add_table( 
      2,
      1,
      2+self.shape[0], 
      1+self.shape[1], 
      {
        'columns' : headers,
        'header_row' : True,
        'autofilter' : False,
        'style' : 'Table Style Light 18',
      }
    )


    fob_format = writer.book.add_format({
        'align':       'center',
    })
    count = len(cols)
    worksheet.set_column(count - 1, count, 100, fob_format)


  def CreateLinkTable(self, writer, indexDF, tableName = "EC w Links"):
    indexDF.UpdateECLList(tableName)
    self.to_excel( 
      writer, 
      sheet_name= tableName, 
      header=self.options["header"], 
      index = self.options["index"], 
      startrow = self.options["startrow"], 
      startcol = self.options["startcol"] 
    )
    
    ind_pf = self.ind_pf
    worksheet = writer.sheets[tableName]
    count = len(self.columns.tolist())
    #table format
    format = writer.book.add_format({
        'align':       'center',
        'font_color' : 'blue',
    })

    cnt = len(self.columns.to_list())
    
    for i, min_row in enumerate(self.min_rows) :
      if not isnan( min_row ) :
        worksheet.write_url( 
          3+i, 
          count, 
          'internal:Corners!' + tools.colnum_string( i+ind_pf+3) + str(cnt + min_row),
          format,
          string = self['Min Corner'][i]
          )
      if not isnan( self.max_rows[i] ) :
        worksheet.write_url( 
          3+i, 
          count + 1, 
          'internal:Corners!' + tools.colnum_string( i+ind_pf+3) + str(cnt + self.max_rows[i]),
          format,
          string = self['Max Corner'][i])
      
    cols = ['#']
    cols.extend(self.columns.tolist())
    headers = list( map(lambda x : { 'header' : x } , cols ))
    worksheet.add_table( 
      2,1,2 + self.shape[0], 1+ self.shape[1], {        
        'columns' : headers,
        'header_row' : True,
        'autofilter' : False,
        'style' : 'Table Style Light 18',
      }
    )

    format = writer.book.add_format({
        'align':       'center',
    })

    worksheet.set_column(count, count + 1, 100, format)
    
       
  
