# -*- coding: utf-8 -*-
"""
# Excel to NGDS Service ArcGIS Tool
# Written by Jessica Good Alisdairi at the Arizona Geological Survey, May-June 2013
# This tool validates and converts a spreadsheet in an Excel file to a feature class 
# ready to be deployed as an NDGS service.
"""

# import required modules
import arcpy
from arcpy import env
import os
import sys
import datetime
import urllib2
import json
from xml.dom.minidom import parseString
try:
    import xlrd
except:
    arcpy.AddError("Import of XLRD module failed.\nThe XLRD module can be downloaded from: http://pypi.python.org/pypi/xlrd")

# Main function for the Excel to NGDS Feature ArcGIS Tool
def main(argv=None):
    # Don't allow overwriting
    arcpy.env.overwriteOutput = False

    # Get the parameters of the tool
    inExcel = arcpy.GetParameterAsText(0)
    sheetName = arcpy.GetParameterAsText(1)
    schemaFile = arcpy.GetParameterAsText(2)
    serviceName = arcpy.GetParameterAsText(3)
    validateOnly = arcpy.GetParameterAsText(4)
 
    # Get the path for the folder of the Excel file (used for output of GeoDB)
    path = os.path.dirname(inExcel) + "\\"    

    # Run it
    try:
        schemaFields, schemaTypes, schemaReq, layerNames = ReadSchema(schemaFile)
        sht, wb = GetExcelFile(inExcel, sheetName)
        data, longFields, srs = ValidateExcelFile(sht, wb, schemaFields, schemaTypes, schemaReq)
        
        if len(layerNames) > 1:
            layerName = "AllLayers"
        else:
            layerName = layerNames[0]
  
        if (validateOnly == "false"):
            CreateGeodatabase(path, serviceName)
            
            arcpy.env.workspace = path + serviceName + ".mdb"
            table = layerName + "Table"
                        
            MakeTable(table, longFields, schemaFields, schemaTypes)
            InsertData(table, data, schemaFields)
            CreateXYEventLayer(table, layerName + "Layer", srs)
            CreateFeatureClass(layerName + "Layer", layerName, srs)
            
            # Make sure the final feature class has the same number of rows as the orignial table
            rowsTemp = int(arcpy.GetCount_management(table).getOutput(0))
            rowsFinal = int(arcpy.GetCount_management(layerName).getOutput(0))
            if rowsTemp != rowsFinal:
                rowsDeleted = rowsTemp - rowsFinal
                if rowsDeleted == 1:
                    arcpy.AddMessage("  Error! " + str(rowsDeleted) + " row was deleted when converting the table to the feature class.")
                else:
                    arcpy.AddMessage("  Error! " + str(rowsDeleted) + " rows were deleted when converting the table to the feature class.")
                arcpy.AddMessage("Check the Lat & Long values for errors.")
                raise Exception ("Conversion Failed.")
            else:
                arcpy.Delete_management(table)
            
            # Deal with services that have multiple layers
            if len(layerNames) > 1:
                for layer in layerNames:
                    arcpy.CopyFeatures_management("AllLayers", layer)
                    arcpy.AddMessage("Created Feature Class " + layer)
                arcpy.Delete_management("AllLayers")
                      
                arcpy.AddMessage("  Warning! This is a service with multiple layers. All layers will be created having the same fields.") 
                arcpy.AddMessage("  Delete any layers not being used and for each layer use the schema to delete the fields that do not belong.")    
            
            arcpy.AddMessage("Conversion Successful!")
       
    except Exception as err:
        arcpy.AddError("Error: {0}".format(err))

# Get the schema from the web and read it
def ReadSchema(schemaFile):
    arcpy.AddMessage('Reading Schema ...')
    
    # Remove whitespaces in name of schema
    schemaFile = schemaFile.replace(" ","")
    
    # Get the info in json format about all the schemas on "http://schemas.usgin.org/contentmodels.json"
    url = "http://schemas.usgin.org/contentmodels.json"
    try:
        schemasInfo = json.load(urllib2.urlopen(url))
    except:
        arcpy.AddMessage("Unable to reach http://schemas.usgin.org/contentmodels.json to read content model schemas.")
        raise Exception ("Failed to Read Schema.")    
    
    # Read the json to get the name of the all the schemas + version number + .xsd location
    schemasList = {}
    for rec in schemasInfo:
        t = rec['title']
        for v in rec['versions']:
            schemaName = t + v['version']
            schemaName = schemaName.replace(" ","")
            schemasList[schemaName] = v['xsd_file_path']
            
#     for s in schemasList:
#         print s + "," + schemasList[s]
    
    # Get the .xsd schema location for the user inputed schema name and read the schema       
    schemaUrl = schemasList[schemaFile]
    schema = urllib2.urlopen(schemaUrl).read()    
    dom = parseString(schema)
    
    schemaFields = []
    schemaTypes = []
    schemaReq = []

    # Get the values of the name, type and minOccurs attributes from the schema
    for node in dom.getElementsByTagNameNS("http://www.w3.org/2001/XMLSchema", 'element'):
        schemaFields.append(node.getAttribute('name').encode('UTF-8'))
        schemaTypes.append(node.getAttribute('type'))
        schemaReq.append(node.getAttribute('minOccurs'))
    
    # Get the index of the OBJECTID field and remove that and any fields before it
    objectIDIndex = schemaFields.index("OBJECTID")
    layers = []
    i = 0
    while i < objectIDIndex:
        layers.append(schemaFields[0])
        schemaFields.pop(0)
        schemaTypes.pop(0)
        schemaReq.pop(0)
        i = i + 1
    del i
    
    # Remove the OBJECTID field
    schemaFields.pop(0)
    schemaTypes.pop(0)
    schemaReq.pop(0)
    
    # Remove any Shape fields
    foundAll = False
    while foundAll == False:
        try:
            shapeIndex = schemaFields.index("Shape")
            schemaFields.pop(shapeIndex)
            schemaTypes.pop(shapeIndex)
            schemaReq.pop(shapeIndex)
        except:
            foundAll = True
    del foundAll
    
    # Read the field types from the schema
    for i, t in enumerate(schemaTypes):
        if (t == "") or (t == "xs:string"):
            schemaTypes[i] = "Text"
        elif (t == "xs:double"):
            schemaTypes[i] = "Double"
        if "Date" in schemaFields[i]:
            schemaTypes[i] = "Date"
    del i, t
     
    arcpy.AddMessage('Finished Reading Schema.')   
    return schemaFields, schemaTypes, schemaReq, layers

# Get a list of sheet names for the selected Excel file
def sheet_names(inExcel):
    wb = xlrd.open_workbook(inExcel)
    potential_sheets = [sht.name for sht in wb.sheets()]
    return potential_sheets

# Open the Excel file
def GetExcelFile(inExcel, sheetName):
    arcpy.AddMessage('Getting Excel file ...')
    
    wb = xlrd.open_workbook(inExcel)
    if sheetName.upper() != "FIRST":
        try:
            sht = wb.sheet_by_name(sheetName)
            return sht, wb
        except:
            arcpy.AddError('Invalid Sheet Name')
            sys.exit()
    else:
        sht = wb.sheet_by_index(0)
        return sht, wb

# Check that the excel fields match the schema fields
def CheckFields(excelFields, schemaFields):
    arcpy.AddMessage("Validating Excel fields against the schema fields ...")
        
    # Check that all the field names are in Win-1252 then strip whitespace and carriage returns
    for i in range(len(excelFields)):
        if isinstance(excelFields[i], unicode):
            try:
                excelFields[i] = excelFields[i].encode("windows-1252")
            except:
                arcpy.AddMessage("  Found an unrecognized character in column #" + i + " of the field names.")
                raise Exception ("Data not in Win1252 encoding. Validation Failed")
            excelFields[i] = excelFields[i].replace(" ","")
            excelFields[i] = excelFields[i].replace("\n","")   
    del i
    
    # Variable to store whether an error has been found with the fields or not
    excep = False
    
    # Check if the Excel file has the name number of fields as the schema
    if (len(excelFields) != len(schemaFields)):
        arcpy.AddMessage("  Different number of fields.")
        arcpy.AddMessage("  " + str(len(excelFields)) + " fields in the Excel file (fields on the left below).")
        arcpy.AddMessage("  " + str(len(schemaFields)) + " fields in the schema (fields on the right below).")
        excep = True

    # Variable to store the name of the primary URI field whose items must be unique 
    primaryURIField = None

    # Check if the Excel file has the same exact fields in the same order as the schema
    for eF, sF in map(None, excelFields, schemaFields):
        if sF != None and "URI" in sF and primaryURIField == None:
            primaryURIField = sF
        if (excep == True) and (eF == sF):
            arcpy.AddMessage("  " + str(eF) + " == " + str(sF))
        if (eF != sF):
            arcpy.AddMessage("  " + str(eF) + " != " + str(sF))
            excep = True
    del eF, sF
    
    # If an error with the Excel fields has been found raise and Exception
    if (excep == True):
        raise Exception ("Schema Mismatch Error. Validation Failed")
    # Otherwise continue
    else:
        arcpy.AddMessage("Field Validation Successful.")
        
    del excep   
    return primaryURIField

# Check that the values for certain fields are within a specified domain
def CheckDomain(val, field, rowNum):

    # Make sure Latitude and Longitude are within bounds
    if field == "LatDegree" or field == "LatDegreeWGS84":
        if not (val >= -90 and val <= 90):
            arcpy.AddMessage("  " + field + ", row " + rowNum + ": Latitude is not between -90 and 90.")
            raise Exception ("Latitude Error")
    elif field == "LongDegreeWGS84" or field == "LongDegree":
        if not (val >= -180 and val <= 180):
            arcpy.AddMessage("  " + field + ", row " + rowNum + ": Longitude is not between -180 and 180.")
            raise Exception ("Longitude Error")
        
    return

# Perform validataion checks for values whose data type is supposed to be Text
def CheckTypeText(val, field, req, rowNum, warnMsgCount, maxWarnMsg):

    # If the value is not empty
    if val != "":
        
        # Remove demical and trailing zeros that were added on Excel import
        if isinstance(val, float):
            if val == int(val):
                val = '%d'%val
                        
        # Make sure the value can be represented as a string
        try:
            val = str(val)
        # If the value can't be represented as a string
        except:
            # If the field is required change the value to Missing
            if req != "0":
                if warnMsgCount <= maxWarnMsg:
                    arcpy.AddMessage("  " + field + ", row " + rowNum + ": Type should be Text. Changing \'" + val + "\' to \'Missing.\'")
                    warnMsgCount = warnMsgCount + 1
                val = "Missing"
            # If the field is not required change the value to the empty string
            else:
                if warnMsgCount <= maxWarnMsg:
                    arcpy.AddMessage("  " + field + ", row " + rowNum + ": Type should be Text. Field not required. Deleting \'" + val + ".\'")
                    warnMsgCount = warnMsgCount + 1
                val = ""
    # If the value is empty
    else:
        # If the field is required change the value to Missing 
        if req != "0":
            val = "Missing"
    return val, warnMsgCount 
                
# Perform validataion checks for values whose data type is supposed to be Double 
def CheckTypeDouble(val, field, req, rowNum, warnMsgCount, maxWarnMsg):           

    # If the value is not empty
    if val != "":
        # Make sure the value can be represented as a float
        try:
            val = float(val)
        # If the value can't be represented as a float
        except:
            # If the field is required change the value to -9999
            if req != "0":
                if warnMsgCount <= maxWarnMsg:
                    arcpy.AddMessage("  " + field + ", row " + rowNum + ": Type should be Double. Changing \'" + val + "\' to \'-9999.\'")
                    warnMsgCount = warnMsgCount + 1
                val = "-9999"
                if field == "LatDegree" or field == "LatDegreeWGS84" or field == "LongDegree" or field == "LongDegreeWGS84":
                    CheckDomain(val, field, rowNum)
            # If the field is not required change the value to the empty string
            else:
                if warnMsgCount <= maxWarnMsg:
                    arcpy.AddMessage("  " + field + ", row " + rowNum + ": Type should be Double. Field not required. Deleting \'" + val + ".\'")
                    warnMsgCount = warnMsgCount + 1
                val = None
        else:
            CheckDomain(val, field, rowNum)
    # If the value is empty
    else:
        # If the field is required change the value to -9999 
        if req != "0":
            val = "-9999"
            if field == "LatDegree" or field == "LatDegreeWGS84" or field == "LongDegree" or field == "LongDegreeWGS84":
                CheckDomain(val, field, rowNum)
        else:
            val = None
            
    return val, warnMsgCount 
                
# Perform validataion checks for values whose data type is supposed to be Date 
def CheckTypeDate(val, field, req, rowNum, warnMsgCount, maxWarnMsg, wb): 

    # If the value is not empty
    if val != "":
        # Make sure the value can be represented as a date
        # Try to convert strings or unicode text to a date
        if isinstance(val, str) or isinstance(val, unicode):
            try:                   
                val = datetime.datetime.strptime(val, "%Y-%m-%dT%H:%M:%S")
            except:
                try:
                    val = datetime.datetime.strptime(val, "%Y-%m-%dT%H:%M")  
                except:
                    try:
                        val = datetime.datetime.strptime(val, "%m/%d/%YT%H:%M:%S")
                    except:
                        try:
                            val = datetime.datetime.strptime(val, "%m/%d/%YT%H:%M")
                        except:
                            try:
                                val = datetime.datetime.strptime(val, "%Y-%m-%d")
                            except:
                                try:
                                    val = datetime.datetime.strptime(val, "%m/%d/%Y")
                                # If the value can't be converted
                                except:
                                    # If the field is required change the value to 1/1/1900T00:00  
                                    if (req != "0"):                                
                                        arcpy.AddMessage("  " + field + ", row " + rowNum + ": Not recognized as a date (" + val + ")")
                                        raise Exception ("Date Error. Validation Failed.")
                                    # Otherwise change the value to the empty string
                                    else:
                                        if warnMsgCount <= maxWarnMsg:
                                            arcpy.AddMessage("  " + field + ", row " + rowNum + ": Not recognized as a date. Field not required. Deleting \'" + val + ".\'")
                                            warnMsgCount = warnMsgCount + 1
                                        val = None                               
        # If the cell value is not a string or unicode
        else:
            # Try to see if it is a timestamp and convert it
            try:
                if val >= 61:
                    year, month, day, hour, minute, second = xlrd.xldate_as_tuple(val, wb.datemode)
                    val = datetime.datetime(year, month, day, hour, minute, second)
                # Excel treats the first 60 days of 1900 as ambiguous (see Microsoft documentation)
                # Assume the dates are what is indicated in the cell
                else:
                    val = datetime.datetime(1900, 1, 1, 0, 0, 0) + datetime.timedelta(days = val - 1)
            # If the value can't be converted to a date
            except:
                # If the field is required change the value to 1/1/1900T00:00  
                if (req != "0"):                                
                    arcpy.AddMessage("  " + field + ", row " + rowNum + ": Not recognized as a date (" + val + ")")
                    raise Exception ("Date Error. Validation Failed.")
                else:
                    # Otherwise change the value to the empty string
                    if warnMsgCount <= maxWarnMsg:
                        arcpy.AddMessage("  " + field + ", row " + rowNum + ": Not recognized as a date. Field not required. Deleting \'" + val + ".\'")
                        warnMsgCount = warnMsgCount + 1
                    val = None
    # If the value is empty
    else:
        # If the field is required change the value to 1/1/1900T00:00:00
        if req != "0":
            val = datetime.datetime(1900, 1, 1, 0, 0, 0)
        else:
            val = None
            
    return val, warnMsgCount 

# Check the URIs
def CheckURIs(val, field, row, uris, primaryURIField):

    val = val.replace(" ","")
    val = val.replace("\n","")
    
    # If the value is not blank or the word Missing
    if val != "" and val !="Missing":
        # If the value does not start with "http://resources.usgin.org/uri-gin/"
        if val.find("http://resources.usgin.org/uri-gin/") != 0:
            arcpy.AddMessage("  " + field + ", row " + row + ": URI needs to start with \'http://resources.usgin.org/uri-gin/\' (" + val + ")")
            raise Exception ("URI Error. Validation Failed.")
        # If the last character is not a backslash add one
        if val[len(val)-1] != "/":
            val = val + "/"
        # If the URI has less than 7 backslashes it does not have enough parts
        if val.count("/") < 7:
            arcpy.AddMessage("  " + field + ", row " + row + ": URI field does not have enough components.")
            raise Exception ("URI Error. Validation Failed.")
        # If the current field is the primary URI field there can be no duplicates        
        if field == primaryURIField:
            # If the current URI is already in the list of URIs there is an error
            if val in uris:
                arcpy.AddMessage("  " + field + ", row " + row + ": URI has already been used (" + val + ")")
                raise Exception ("URI Error. Validation Failed.")
            # If the current URI is not in the list of URIs add it
            else:
                uris.append(val)
                
    return val, uris

# Check the spatial reference - If no SRS column, assume the projection is WGS84
def CheckSRS(val, field, row, srs):

    # If the SRS column indicates WGS84 aka EPSG:4326
    if "4326" in val or "84" in val:
        val = "EPSG:4326"
        if row == 1: 
            srs = "WGS84"
        elif srs != "WGS84":   
            srs = "Mismatch"
    # If the SRS column indicates NAD83 aka EPSG:4269
    elif "4269" in val or "83" in val:
        val = "EPSG:4269"
        if row == 1:
            srs = "NAD83"
        elif srs != "NAD83":
            srs = "Mismatch"   
    # If the SRS column indicates NAD27 aka EPSG:4267       
    elif "4267" in val or "27" in val:
        val = "EPSG:4267"
        if row == 1:
            srs = "NAD27"
        elif srs != "NAD27":
            srs = "Mismatch"
    else:
        val = "EPSG:4326"
        if row == 1:
            srs = "Unknown"
        elif srs != "Unknown":
            srs = "Mismatch"
        
    if srs == "Mismatch":
        arcpy.AddMessage("  " + field + ", row " + str(row + 1) + ": Indicates a different coordinate system than previous row. Make SRS field values consistent.")
        raise Exception ("SRS Error. Validation Failed.")
        
    return val, srs

# Validate the Excel file against specified requirements
def ValidateExcelFile(sht, wb, schemaFields, schemaTypes, schemaReq):
    arcpy.AddMessage('Reading Excel file ...')
    
    # List of new rows
    newRows = []
    
    # Get the values for the first row of the Excel sheet
    excelFields = sht.row_values(0)
    # Check the excel fields against the schema fields
    primaryURIField = CheckFields(sht.row_values(0), schemaFields)

    # Create a boolean list for whether any row in the field contains a value
    # longer than 255 characters - Set to false initially 
    longFields = []
    for i in range(len(excelFields)):
        longFields.append(False)
    del i

    # Variable to store list of URIs in the primary URI field 
    uris = []
    
    # Warning message counts
    warnMsgCount = 0
    maxWarnMsg = 30
    
    # Default spatial reference system
    srs = "WGS84"
    
    arcpy.AddMessage("Validating Excel file data ...")
    # Loop through each row of the Excel file starting with the 2nd row (1st row was already read as the field names)
    for i in range(1, sht.nrows):
        # Get the current row
        row = sht.row_values(i)
        
        # Loop through each cell in the current row
        for x in range(0, sht.ncols):

            # Only show a given number of warning messages that are not errors
            if warnMsgCount == maxWarnMsg:
                arcpy.AddMessage("Not showing anymore messages that are not errors.")
                warnMsgCount = warnMsgCount + 1

            # Convert unicode to Win-1252 encoding (used by the server)
            if isinstance(row[x], unicode):
                try:
                    row[x] = row[x].encode("windows-1252")
                except:
                    arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Found an unrecognized character in \'"+ row[x] + ".\'")
                    raise Exception ("Data not in Windows 1252 encoding. Validation Failed.")
                # Remove leading and trailing whitespace
                row[x] = row[x].strip()

            # If the value is "nil:missing" change it to "Missing"
            if row[x] == "nil:missing":
                row[x] = "Missing"
            
            # Check data type of the value
            if schemaTypes[x] == "Text":
                row[x], warnMsgCount = CheckTypeText(row[x], schemaFields[x], schemaReq[x], str(i + 1), warnMsgCount, maxWarnMsg)
            elif schemaTypes[x] == "Double":
                row[x], warnMsgCount = CheckTypeDouble(row[x], schemaFields[x], schemaReq[x], str(i + 1), warnMsgCount, maxWarnMsg)
            elif schemaTypes[x] == "Date":
                row[x], warnMsgCount = CheckTypeDate(row[x], schemaFields[x], schemaReq[x], str(i + 1), warnMsgCount, maxWarnMsg, wb)
            else:
                arcpy.AddMessage("  " + schemaFields[x] + " does not indicate a Text, Double or Date type in the schema.")
                raise Exception ("Type Error. Validation Failed.")
            
            # If the field name indicates a URI field check the URIs
            if "URI" in schemaFields[x]:
                row[x], uris, = CheckURIs(row[x], schemaFields[x], str(i+1), uris, primaryURIField)                            

            # If the length of the value in the current cell is longer than 255 characters
            # put the value True in the longFields list for that field        
            if len(str(row[x])) > 255:
                longFields[x] = True                

            # If the field name indicates SRS field check the SRS
            if "SRS" in schemaFields[x]:
                row[x], srs = CheckSRS(row[x], schemaFields[x], i, srs) 

        # Append the row to the list of new rows
        newRows.append(row)
    
    arcpy.AddMessage("Validation Successful.")             
    return newRows, longFields, srs

# Create the personal Geodatabase (Access DB)
def CreateGeodatabase(path, name):
    arcpy.AddMessage("Creating Geodatabase ...")
    arcpy.CreatePersonalGDB_management(path, name)
    arcpy.AddMessage("Finished Creating Geodatabase.")
    return

# Create the output table, add all required fields for that table
def MakeTable(table, longFields, schemaFields, schemaTypes):
    arcpy.AddMessage("Creating Table in ArcGIS ...")
    arcpy.CreateTable_management(env.workspace, table)

    # Add the fields to the table
    for i in range(0, len(schemaFields)):
        if (longFields[i] == True):
#             arcpy.AddMessage("  " + schemaFields[i] + " contains data longer than 255 characters, adjusting max length for this field to 2,147,483,647")
            arcpy.AddField_management(table, schemaFields[i], "TEXT", "", "", 2147483647)
        else:
            arcpy.AddField_management(table, schemaFields[i], schemaTypes[i])
        arcpy.AddMessage("  " + schemaFields[i] + " added with type " + schemaTypes[i])
    
    arcpy.AddMessage("Finished Creating Table.")
    return

# Insert the data rows in the the table
def InsertData(table, data, schemaFields):
    arcpy.AddMessage("Inserting Rows ...")
 
    # If running on 10.1, use da insert cursor
    if arcpy.GetInstallInfo()['Version'] == '10.1':
        insertCur = arcpy.da.InsertCursor(table, schemaFields)
        for row in data:
            insertCur.insertRow(row)

    # Otherwise use original insert cursor
    else:
        insertCur = arcpy.InsertCursor(table)
        for d in data:
            row = insertCur.newRow()
            for x in range(len(d)):
                row.setValue(schemaFields[x], d[x])
            insertCur.insertRow(row)
    del row, insertCur
    
    arcpy.AddMessage("Finished Inserting Rows")
    return

# Convert the Table to an XY Event Layer in ArcGIS, using WGS84 as the projection    
def CreateXYEventLayer(table, layer, srs):
    arcpy.AddMessage("Converting Table to XY Event Layer ...")
    
    # Set the spatial reference
    if srs == "WGS84":
        spRef = os.path.dirname(__file__) + "\\WGS 1984.prj"
    elif srs == "NAD83":
        spRef = os.path.dirname(__file__) + "\\NAD 1983.prj"
    elif srs == "NAD27":
        spRef = os.path.dirname(__file__) + "\\NAD 1927.prj"
    else:
        arcpy.AddMessage("  Warning!! Unable to determine spatial reference system. The reference system for the data will need to be defined and then reprojected to WGS84.")
        spRef = os.path.dirname(__file__) + "\\WGS 1984.prj"
    arcpy.AddMessage("  Spatial Reference System of data is " + srs)
    
    try:
        testOpen = open(spRef)
    except:
        arcpy.AddMessage("  Unable to find the .prj files that should be located in the same folder as the script. Download the tool again.")
        raise Exception ("Missing Needed File.")
    
    # Create the XY Event Layer
    try:
        arcpy.MakeXYEventLayer_management(table, "LongDegreeWGS84", "LatDegreeWGS84", layer, spRef)
    except:
        try:
            arcpy.MakeXYEventLayer_management(table, "LongDegree", "LatDegree", layer, spRef)
        except:
            arcpy.AddMessage("Unable to determine Lat and Long fields.")
            raise Exception ("Conversion Failed.")
        
    arcpy.AddMessage("Finished Converting Table.")
    return

# Create the Feature Class in ArcGIS & reproject if SRS doesn't indicate WGS84
def CreateFeatureClass(layer, featureClass, srs):
    arcpy.AddMessage("Creating Feature Class ....")

    arcpy.CopyFeatures_management(layer, featureClass)
#     arcpy.MakeFeatureLayer_management(layerName + "Table Events", outLocation + "/" + layerName)
#     arcpy.FeatureClassToFeatureClass_conversion(layerName, outLocation, outFeatureClass)
#     arcpy.FeatureClassToGeodatabase_conversion(layerName, outLocation)
    
    if srs == "NAD27" or srs == "NAD83":      
        if srs == "NAD27":
            spRef = os.path.dirname(__file__) + "\\NAD 1927.prj"
            trans = "NAD_1927_To_WGS_1984_4"
        if srs == "NAD83":
            spRef = os.path.dirname(__file__) + "\\NAD 1983.prj"
            trans = "NAD_1983_To_WGS_1984_1"
            
        inCS = spRef
        outCS = os.path.dirname(__file__) + "\\WGS 1984.prj"
        
        # Determine if the input has a defined coordinate system, can't project it if it does not
#        dsc = arcpy.Describe(featureClass)
#        arcpy.AddMessage(dsc.spatialReference.Name)
        
        arcpy.AddMessage("  Reprojecting from " + srs + " to WGS84 using the transformation " + trans + "....")
        arcpy.AddMessage("  Warning! If the data indicates a region other than the continental US you may need to use a different transformation.")
        
        # Reproject the feature class to WGS 84 and save in a temporary feature class 
        featureClassTemp = featureClass + "Temp"
        arcpy.Project_management(featureClass, featureClassTemp, outCS, trans, inCS)
        
        # Delete the original feature class and rename the temporary feature class the same as the original
        arcpy.Delete_management(featureClass)
        arcpy.Rename_management(featureClassTemp, featureClass)

        # Calculate XY coordinates for the points in the feature class        
        arcpy.AddXY_management(featureClass)
        
        # Replace the value in the Lat & Long fields with the calculated XY coordinates
        # Update the SRS column to WGS 84
        rows = arcpy.UpdateCursor(featureClass)
        for row in rows:
            try:
                row.LatDegree = row.POINT_Y
                row.LongDegree = row.POINT_X
            except:
                try:
                    row.LatDegreeWGS84 = row.POINT_Y
                    row.LongDegreeWGS84 = row.POINT_X
                except:
                    raise Exception ("Unable to find Lat & Long columns. Conversion Failed.")
            row.SRS = "EPSG:4326"
            rows.updateRow(row)
            
        # Delete cursor and row objects to remove locks on the data 
        del row, rows
        
        arcpy.DeleteField_management(featureClass, ["POINT_Y", "POINT_X"])
        arcpy.AddMessage("  Finished Reprojecting.")

    arcpy.AddMessage("Finished Creating Feature Class.")
    return

if __name__ == "__main__":
    main()