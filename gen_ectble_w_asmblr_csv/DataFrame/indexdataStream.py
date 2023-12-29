import pandas as pd

class IndexDataFrame(pd.DataFrame):
  
  def __init__(self, data=None, index=None, columns=None, **kwargs):
    super(IndexDataFrame, self).__init__(data=data, index=index, columns=columns, **kwargs)
    self.ECList = []
    self.ECLList = []
    self.UpdateDF([""],"",plain = "", ec_wl = "")

  def UpdateDF(self, originating_spec, val, plain = "EC", ec_wl = "EC wL"):
    
    app = pd.concat([
      self, 
      pd.DataFrame.from_records([{
        'Originating specifier': originating_spec[0], 
        'VAR1': val, 
        'Plain': plain, 
        'w Links' : ec_wl
      }])
      ], 
      ignore_index = True
    )

    self.__dict__.update(app.__dict__)
    # print(self)

  def CreateTable(self, writer, workbook):
    self.to_excel(
      writer, 
      sheet_name= "Index", 
      header = False, 
      startrow = 2, 
      startcol = 2 , 
      index = False
    )
    
    # first row is empty, therefore starting from 2 insted of 3
    worksheet = writer.sheets['Index'] 
    headers = list(map(lambda x : {'header' : x} , self.columns)) 
    worksheet.add_table(
      3,
      2,
      3 + self.shape[0] -2, 
      1 + self.shape[1], 
      {        
        'columns' : headers,
        'header_row' : False,
        'autofilter' : False,
        'style' : 'Table Style Light 18',
      }
    )

    # Add link format.
    link_format1 = workbook.add_format({
        'font_color': 'blue',
        'bold':       1,
        'underline':  0,
        'align' : 'center'
        #'font_size':  12,
    })

    link_format2 = workbook.add_format({
        'font_color': 'blue',
        'bold':       1,
        'underline':  1,
        'align' : 'center'
        #'font_size':  12,
    })

    #header format
    header_format = workbook.add_format({
        'bold':       1,
        'align' : 'center'
    })

    #table format
    table_format = workbook.add_format({
        'align':       'center',
    })

    #table format
    fob_format = workbook.add_format({
        'align':       'justify',
    })

    # spec note format  # -- AC 8/17/2020
    ospeci_format = workbook.add_format({
      'align':       'left',
      'font_color' : 'blue',
    })
    
    worksheet.write_url('E3', "internal:'EC Table'!B3", link_format1,string='EC Table')
    worksheet.write_url('F3', "internal:'EC w Links'!B3",link_format2,string='EC w Links')
    for i in range(1, self.shape[0]):
      orig_spec_value = self.loc[i,'Originating specifier']
      ec_sheet = self.loc[i,'Plain']
      ecl_sheet = self.loc[i,'w Links']
      if orig_spec_value == 'Originating specifier': #if its a header or empty row, do not add links
          #set bold font
          worksheet.set_row(i + 2, 15, header_format) #15 row height
      else:
          worksheet.write_url('E' + str(i + 3), "internal:'" + ec_sheet + "'!B3", link_format1,string = ec_sheet)
          worksheet.write_url('F' + str(i + 3), "internal:'"+ ecl_sheet + "'!B3", link_format2,string = ecl_sheet)
          #add originating specifier text to individual sheets
          ws = writer.sheets[ec_sheet]
          ws.write(0,1,orig_spec_value + "   "  + "= " + str(self['VAR1'][i]) ,ospeci_format) 
          ws = writer.sheets[ecl_sheet]
          ws.write(0,1,orig_spec_value + "   "  + "= " + str(self['VAR1'][i]) ,ospeci_format)
      
          worksheet.set_column("C:F", 10, table_format)
          worksheet.set_column("C:C",30,fob_format)


    sheets_lst = ['Index'] + ['Corners'] + ['EC Table'] + self.ECList + ['EC w Links'] + self.ECLList
    workbook.worksheets_objs.sort(key=lambda x: sheets_lst.index(x.name))
    
  def UpdateECList(self, str):
    self.ECList.append(str)
  
  def UpdateECLList(self, str):
    self.ECLList.append(str)