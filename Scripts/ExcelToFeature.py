# -*- coding: utf-8 -*-
"""
# Excel to NGDS Feature ArcGIS Tool
# Written by Jessica Good Alisdairi at the Arizona Geological Survey, May 2013
# This tool validates and converts a spreadsheet in an Excel file to a Feature class 
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
    # Allow overwrite of tables
    arcpy.env.overwriteOutput = True

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
        sht = GetExcelFile(inExcel, sheetName)
        data, longFields, srs = ValidateExcelFile(sht, schemaFields, schemaTypes, schemaReq)
        
        if len(layerNames) > 1:
            layerName = "AllLayersTemp"
        else:
            layerName = layerNames[0]
  
        if (validateOnly == "false"):
            CreateGeodatabase(path, serviceName)
            
            outGeoDB = path + serviceName + ".mdb"         
            tempTable = outGeoDB + "\\" + layerName + "Table"
            
            MakeTable(tempTable, longFields, schemaFields, schemaTypes)
            InsertData(tempTable, data, schemaFields)
            CreateXYEventLayer(tempTable, layerName, srs)
            CreateFeatureClass(layerName, outGeoDB, srs)
            
            arcpy.Delete_management(tempTable)
            
            # Deal with services that have multiple layers
            if len(layerNames) > 1:
                for layerName in layerNames:
                    arcpy.FeatureClassToFeatureClass_conversion(outGeoDB + "\\AllLayersTemp", outGeoDB, layerName)
                    arcpy.AddMessage("Created Feature Class " + layerName)
                arcpy.Delete_management(outGeoDB + "\\AllLayersTemp")
                      
                arcpy.AddMessage("Warning! This is a service with multiple layers. All layers will be created having the same fields.") 
                arcpy.AddMessage("Delete any layers not being used and for each layer use the schema to delete the fields that do not belong.")
            
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
#     dom = parse(schemaFile)
    
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
    layerNames = []
    i = 0
    while i < objectIDIndex:
        layerNames.append(schemaFields[0])
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
    return schemaFields, schemaTypes, schemaReq, layerNames

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
            return sht
        except:
            arcpy.AddError('Invalid Sheet Name')
            sys.exit()
    else:
        sht = wb.sheet_by_index(0)
        return sht

# Validate the Excel file against specified requirements
def ValidateExcelFile(sht, schemaFields, schemaTypes, schemaReq):
    arcpy.AddMessage('Reading Excel file ...')
    
    values = []
    # Get the first row of the Excel file to use as the fieldnames
    excelFields = sht.row_values(0)

    # Check that all characters are UTF-8
    # Strip whitespace and carriage returns from excelFields because the fields
    # in some content models have an extra whitespace on the end of the field name
    # We need to remove this or the field won't match the schema fields
    for i, eF in enumerate(excelFields):
        try:
            excelFields[i] = eF.encode('UTF-8')
        except:
            arcpy.AddMessage("  Found an unrecognized character in column #" + i + " of the field names.")
            raise Exception ("Field Name Failure.")  
        excelFields[i] = excelFields[i].replace(" ","")
        excelFields[i] = excelFields[i].replace("\n","")    
    del i, eF
    
    arcpy.AddMessage("Validating Excel file fields against the schema ...")
    excep = False
    # Check if the Excel file has the name number of fields as the schema
    if (len(excelFields) != len(schemaFields)):
        arcpy.AddMessage("  Different number of fields.")
        arcpy.AddMessage("  " + str(len(excelFields)) + " fields in the Excel file.")
        arcpy.AddMessage("  " + str(len(schemaFields)) + " fields in the schema.")
        excep = True

    # Check if the Excel file has the same exact fields in the same order as the schema
    for eF, sF in map(None, excelFields, schemaFields):
        if (excep == True) and (eF == sF):
            arcpy.AddMessage("  " + str(eF) + " == " + str(sF))
        if (eF != sF):
            arcpy.AddMessage("  " + str(eF) + " != " + str(sF))
            excep = True
    del eF, sF
    
    if (excep == True):
        raise Exception ("Schema Mismatch")
    else:
        arcpy.AddMessage("Field Name Validation Successful.")
    del excep

    # Create a boolean list to for whether any row in the field contains a value
    # longer than 255 characters - Set to false initially 
    longFields = []
    for i in range(len(excelFields)):
        longFields.append(False)
    del i
    
#     errMessages = ["URI fields need to have http://resources.usgin.org/uri-gin/ in the URI", 
#                    "URI fields not in the correct format",
#                    "Reference System Incorrect"]   
#     errs = [False, False, False, False, False]

    errURI = False
    
    errMsgCount = 0
    maxErrMsg = 30
    warnMsgCount = 0
    maxWarnMsg = 20
    
    srs = "WGS84"
    
#     # Create a list of special characters
#     specialChars = {"δ": "delta", "°": "degree", "μ": "mu", "*": ""}
    
    # get all rows after the first one (was already read as the field names)
    arcpy.AddMessage("Validating Excel file data ...")
    for i in range(1, sht.nrows):
        row = sht.row_values(i)
        
        # Loop through each cell in the current row
        for x in range(0, sht.ncols):

            # Only show a given number of error messages and then quit
            if errMsgCount == maxErrMsg:
                arcpy.AddMessage("Fix some of the errors and then run again.")
                raise Exception ("Too Many Errors.")
            
            # Only show a given number of warning messages that are not errors
            if warnMsgCount == maxWarnMsg:
                arcpy.AddMessage("Not showing anymore messages that are not errors.")
                warnMsgCount = warnMsgCount + 1
            
#             print row[x]
            # Get the value of the current cell
            val = (sht.cell(i,x).value)
            
            # Convert unicode to UTF-8 encoding
            if isinstance(val, unicode):
                try:
                    val = val.encode('UTF-8')
                    row[x] = val
                except:
                    arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Found an unrecognized character.")
                    raise Exception ("Conversion Failed.")   

            # Search for and replace special characters
#             if isinstance(val, str):
#                 for c in specialChars.keys():
#                     if val.find(c) != -1:
#                         arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Found a special character. Changing \'" + c + "\' to \'" + specialChars[c] + ".\'")
#                         warnMsgCount = warnMsgCount + 1
#                         val = val.replace(c, specialChars[c])
#                         row[x] = val 

            #print schemaFields[x] + ": " + val
            #print type(val)

            # Check that the URI fields have the required beginning and end
            if "URI" in schemaFields[x]:
                val = val.replace(" ","")
                val = val.replace("\n","")
                row[x] = val
                if val == "nil:missing":
                    val = "Missing"
                    row[x] = "Missing"
                if val != "" and val !="Missing":
                    if val.find("http://resources.usgin.org/uri-gin/"):
                        arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1)+ ": URI needs to start with \'http://resources.usgin.org/uri-gin/\' (" + val + ")")
                        errMsgCount = errMsgCount + 1
                        errURI = True
                    if errURI == False:
                        if val[len(val)-1] != "/":
#                             if warnMsgCount <= maxWarnMsg:                            
#                                 arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1)+ ": URI fields need to end with a '\/.\' Adding a '\/.\'")
#                                 warnMsgCount = warnMsgCount + 1
                            val = val + "/"
                            row[x] = row[x] + "/"
                        if val.count("/") < 7:
                            arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1)+ ": URI field does not have enough components.")
                            errMsgCount = errMsgCount + 1
                            errURI = True
                            

            # If the length of the value in the current cell is longer than 255 characters
            # put the value True in the longFields list for that field        
            if len(str(val)) > 255:
                longFields[x] = True 
#                 if warnMsgCount <= maxWarnMsg:
#                     arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Contains more than 255 characters (" + val + ")")
#                     warnMsgCount = warnMsgCount + 1   
                
            # Check the spatial reference - If no SRS column, assume the projection is WGS84
            if "SRS" in schemaFields[x]:
                v = val.replace(" ","")
                v = v.replace(":","")
                v = v.replace("-","")     
                if v == "EPSG4326" or v == "4326" or v == "WGS84" or v == "WGS1984":
                    if i == 1: 
                        srs = "WGS84"
                    elif srs != "WGS84":   
                        srs = "Mismatch"
                elif v == "EPSG4269" or v == "4269" or v == "NAD83" or v == "NAD1983":
                    if i == 1:
                        srs = "NAD83"
                    elif srs != "NAD83":
                        srs = "Mismatch"   
                elif v == "EPSG4267" or v == "4267" or v == "NAD27" or v == "NAD1927":
                    if i == 1:
                        srs = "NAD27"
                    elif srs != "NAD27":
                        srs = "Mismatch"
                else:
                    if i == 1:
                        srs = "Unknown"
                    elif srs != "Unkown":
                        srs = "Mismatch"
#                     if warnMsgCount <= maxWarnMsg:
#                         arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": WGS 84 spatial reference system not indicated (" + val + ")")
#                         warnMsgCount = warnMsgCount + 1
#                     errMsgCount = errMsgCount + 1
#                     errs[2] = True
                
            if srs == "Mismatch":
                arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Indicates a different coordinate system than previous row. Make SRS field values consistent.")
                raise Exception ("Validation Failed.")  
            
            # If the cell value is empty
            if (val == ""):
                # If the field is required change the value to a placeholder value 
                if (schemaReq[x] != "0"):
                    if (schemaTypes[x] == "Text"):
                        if warnMsgCount <= maxWarnMsg:
                            arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Required Text field empty. Changing to \'Missing.\'")
                            warnMsgCount = warnMsgCount + 1
                        row[x] = "Missing"
                    elif (schemaTypes[x] == "Double"):
                        if warnMsgCount <= maxWarnMsg:
                            arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Required Double field empty. Changing to \'-9999.\'")
                            warnMsgCount = warnMsgCount + 1
                        row[x] = float("-9999")
                    elif (schemaTypes[x] == "Date"):
                        if warnMsgCount <= maxWarnMsg:
                            arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Required Date field empty. Changing to \'1/1/1900T00:00.\'")
                            warnMsgCount = warnMsgCount + 1
                        row[x] = datetime.datetime.strptime("1/1/1900T00:00", "%m/%d/%YT%H:%M")
                # If the field is not required change the value to None
                else:
                    row[x] = None
            # If cell value is not empty check the data type
            else:
                # If the data type is supposed to be Text
                if (schemaTypes[x] == "Text"):
                    # Make sure the cell value is text
                    try:
                        val
                    # If the value of the cell is not text
                    except:
                        # If the field is required change the value to a placeholder value
                        if (schemaReq[x] != "0"):
                            if warnMsgCount <= maxWarnMsg:
                                arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Type should be Text. Changing \'" + val + "\' to \'Missing.\'")
                                warnMsgCount = warnMsgCount + 1
                            row[x] = "Missing"
                        # Otherwise change the value to None
                        else:
                            if warnMsgCount <= maxWarnMsg:
                                arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Type should be Text. Field not required. Changing \'" + val + "\' to Null.")
                                warnMsgCount = warnMsgCount + 1
                            row[x] = None
                # If the data type is supposed to be Double
                elif (schemaTypes[x] == "Double"):
                    # Try to cast the data as a float
                    try:
                        float(val)
                    # If the value can't be cast as a float
                    except:
                        # If the field is required change the value to a placeholder value 
                        if (schemaReq[x] != "0"):
                            if warnMsgCount <= maxWarnMsg:
                                arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Type should be Double. Changing \'" + val + "\' to \'-9999.\'")
                                warnMsgCount = warnMsgCount + 1
                            row[x] = "-9999"
                        # Otherwise change the value to None
                        else:
                            if warnMsgCount <= maxWarnMsg:
                                arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Type should be Double. Field not required. Changing \'" + val + "\' to Null.")
                                warnMsgCount = warnMsgCount + 1
                            row[x] = None
                # If the data type is supposed to be Double     
                elif (schemaTypes[x] == "Date"):
                    # Try to convert strings or unicode text to a date
                    if isinstance(val, str) or isinstance(val, unicode):
                        try:                   
                            date = datetime.datetime.strptime(row[x], "%Y-%m-%dT%H:%M:%S")
                        except:
                            try:
                                date = datetime.datetime.strptime(row[x], "%Y-%m-%dT%H:%M")  
                            except:
                                try:
                                    date = datetime.datetime.strptime(row[x], "%m/%d/%YT%H:%M:%S")
                                except:
                                    try:
                                        date = datetime.datetime.strptime(row[x], "%m/%d/%YT%H:%M")
                                    # If the value can't be converted
                                    except:
                                        # If the field is required change the value to a placeholder value  
                                        if (schemaReq[x] != "0"):                                
                                            arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Not recognized as a date (" + val + ")")
                                            raise Exception ("Validation Failed.")
                                        # Otherwise change the value to None
                                        else:
                                            if warnMsgCount <= maxWarnMsg:
                                                arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Type should be Date. Field not required. Changing \'" + val + "\' to Null.")
                                                warnMsgCount = warnMsgCount + 1
                                            row[x] = None                                
                    # If the cell value is not a string or unicode
                    else:
                        # Try to see if it is a timestamp and convert it
                        try:
                            date = datetime.datetime.fromtimestamp(row[x])
                        # If the value can't be converted to a date
                        except:
                            # If the field is required change the value to a placeholder value  
                            if (schemaReq[x] != "0"):                                
                                arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Not recognized as a date (" + val + ")")
                                raise Exception ("Validation Failed.")
                            else:
                                # Otherwise change the value to None
                                if warnMsgCount <= maxWarnMsg:
                                    arcpy.AddMessage("  " + schemaFields[x] + ", row " + str(i+1) + ": Type should be Date. Field not required. Changing \'" + val + "\' to Null.")
                                    warnMsgCount = warnMsgCount + 1
                                row[x] = None
                    # Set the value in the list of items in the row to date
                    row[x] = date
       
        # Append the row to the list of rows
        values.append(row)
    
    if errURI == True:
        raise Exception ("Validation Failed.") 
    
    arcpy.AddMessage("Validation Successful.")             
    return values, longFields, srs

# Create the personal Geodatabase (Access DB)
def CreateGeodatabase(outPath, outName):
    arcpy.AddMessage("Creating Geodatabase ...")
    arcpy.CreatePersonalGDB_management(outPath, outName)
    arcpy.AddMessage("Finished Creating Geodatabase.")
    return

# Create the output table, add all required fields for that table
def MakeTable(outTable, longFields, schemaFields, schemaTypes):
    arcpy.AddMessage("Creating Table in ArcGIS ...")
    arcpy.CreateTable_management(os.path.dirname(outTable), os.path.basename(outTable))

    # Add the fields to the table
    for i in range(0, len(schemaFields)):
        if (longFields[i] == True):
            arcpy.AddMessage("  " + schemaFields[i] + " contains data longer than 255 characters, adjusting max length for this field to 2,147,483,647")
            arcpy.AddField_management(outTable, schemaFields[i], "TEXT", "", "", 2147483647)
        else:
            arcpy.AddField_management(outTable, schemaFields[i], schemaTypes[i])
        arcpy.AddMessage("  " + schemaFields[i] + " added with type " + schemaTypes[i])
    
    arcpy.AddMessage("Finished Creating Table.")
    return

# Insert the data rows in the the table
def InsertData(outTable, data, schemaFields):
    arcpy.AddMessage("Inserting Rows ...")
 
    # if running on 10.1, use da insert cursor
    if arcpy.GetInstallInfo()['Version'] == '10.1':
        insertCur = arcpy.da.InsertCursor(outTable, schemaFields)
        for row in data:
            insertCur.insertRow(row)

    # otherwise use original insert cursor
    else:
        insertCur = arcpy.InsertCursor(outTable)
        for d in data:
            row = insertCur.newRow()
            for x in range(len(d)):
                row.setValue(schemaFields[x], d[x])
            insertCur.insertRow(row)
    del row, insertCur
    
    arcpy.AddMessage("Finished Inserting Rows")
    return

# Convert the Table to an XY Event Layer in ArcGIS, using WGS84 as the projection    
def CreateXYEventLayer(table, layerName, srs):
    arcpy.AddMessage("Converting Table to XY Event Layer ...")
    
    # Set the spatial reference
    if srs == "WGS84":
        spRef = r"Coordinate Systems\Geographic Coordinate Systems\World\WGS 1984.prj"
    elif srs == "NAD83":
        spRef = r"Coordinate Systems\Geographic Coordinate Systems\North America\NAD 1983.prj"
    elif srs == "NAD27":
        spRef = r"Coordinate Systems\Geographic Coordinate Systems\North America\NAD 1927.prj"
    else:
        arcpy.AddMessage("Warning!! Unable to determine spatial reference system so using WGS84. Reprojection of the feature class will be required.")
        spRef = r"Coordinate Systems\Geographic Coordinate Systems\World\WGS 1984.prj"
    
    # Creat the XY Event Layer
    try:
        arcpy.MakeXYEventLayer_management(table, "LongDegreeWGS84", "LatDegreeWGS84", layerName, spRef)
    except:
        try:
            arcpy.MakeXYEventLayer_management(table, "LongDegree", "LatDegree", layerName, spRef)
        except:
            arcpy.AddMessage("Unable to determine Lat and Long fields.")
            raise Exception ("Conversion Failed.")
        
    arcpy.AddMessage("Finished Coverting Table.")
    return

# Create the Feature Class in ArcGIS & reproject if SRS doesn't indicate WGS84
def CreateFeatureClass(layerName, outGeoDB, srs):
    arcpy.AddMessage("Creating Feature Class ....")
    
    outFeatureClass = outGeoDB + "\\" + layerName
    arcpy.CopyFeatures_management(layerName, outFeatureClass)
#     arcpy.MakeFeatureLayer_management(layerName + "Table Events", outLocation + "/" + layerName)
#     arcpy.FeatureClassToFeatureClass_conversion(layerName, outLocation, outFeatureClass)
#     arcpy.FeatureClassToGeodatabase_conversion(layerName, outLocation)
    
    if srs == "NAD27" or srs == "NAD83":
        install_dir = arcpy.GetInstallInfo()['InstallDir']
        
        if srs == "NAD27":
            spRef = r"Coordinate Systems\Geographic Coordinate Systems\North America\NAD 1927.prj"
            trans = "NAD_1927_To_WGS_1984_4"
        if srs == "NAD83":
            spRef = r"Coordinate Systems\Geographic Coordinate Systems\North America\NAD 1983.prj"
            trans = "NAD_1983_To_WGS_1984_1"
            
        inCS = os.path.join(install_dir, spRef)
        outCS = os.path.join(install_dir, r"Coordinate Systems\Geographic Coordinate Systems\World\WGS 1984.prj")
        
        arcpy.AddMessage("Reprojecting from " + srs + " to WGS84 ....")
        arcpy.AddMessage("If data indicates Hawaii or Alaska double-check reprojection. May need to use a different transformation.")
        
        # Reproject the feature class to WGS 84 and saving in a temporary feature class 
        outFeatureClassTemp = outGeoDB + "\\" + layerName + "Temp"
        arcpy.Project_management(outFeatureClass, outFeatureClassTemp, outCS, trans, inCS)
        
        # Delete the original feature class and rename the temporary feature class as the original
        arcpy.Delete_management(outFeatureClass)
        arcpy.Rename_management(outFeatureClassTemp, outFeatureClass)

        # Calculate XY coordinates to the feature class        
        arcpy.AddXY_management(outFeatureClass)
        
        # Replace the value in the Lat & Long fields with the calculated XY coordinates
        # Update the SRS column to WGS 84
        rows = arcpy.UpdateCursor(outFeatureClass)
        for row in rows:
            try:
                row.LatDegree = row.POINT_Y
                row.LongDegree = row.POINT_X
            except:
                try:
                    row.LatDegreeWGS84 = row.POINT_Y
                    row.LongDegreeWGS84 = row.POINT_X
                except:
                    raise Exception ("Unable to find Lat & Long columns Failure.")
            row.SRS = "WGS 84"
            rows.updateRow(row)
            
        # Delete cursor and row objects to remove locks on the data 
        del row, rows
        
        arcpy.DeleteField_management(outFeatureClass, ["POINT_Y", "POINT_X"])
        arcpy.AddMessage("Finished Reprojecting.")
    
    arcpy.AddMessage("Finished Creating Feature Class.")
    return

if __name__ == "__main__":
    main()