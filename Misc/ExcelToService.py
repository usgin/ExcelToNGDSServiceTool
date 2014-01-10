# -*- coding: utf-8 -*-
"""
# Excel to NGDS Service ArcGIS Tool
# Written by Jessica Good Alisdairi at the Arizona Geological Survey, May-Aug 2013
# This tool validates and converts a spreadsheet in an Excel file to a feature class 
# ready to be deployed as an NDGS service.
"""

# import required modules
import csv
import arcpy
from arcpy import env
import os
import datetime
import dateutil.parser
try:
    import usginmodels
except:
    arcpy.AddError("There was a problem with the usginmodels. Check that http://schemas.usgin.org/contentmodels.json is up and running.")
    raise Exception
try:
    import xlrd
except:
    arcpy.AddError("Import of XLRD module failed.\nThe XLRD module can be downloaded from: http://pypi.python.org/pypi/xlrd")
    raise Exception

# Main function for the Excel to NGDS Feature ArcGIS Tool
def main(argv=None):
    # Don't allow overwriting
    arcpy.env.overwriteOutput = False

    # Get the parameters of the tool
    in_file = arcpy.GetParameterAsText(0)
    sheet_name = arcpy.GetParameterAsText(1)
    schema_name = arcpy.GetParameterAsText(2)
    service_name = arcpy.GetParameterAsText(3)
    layer_name = arcpy.GetParameterAsText(4)
    validate_only = arcpy.GetParameterAsText(5)
	
	# Get the path for the folder of the Excel file (used for output of GeoDB)
    path = os.path.dirname(in_file) + "\\"
	
    schema_uri = get_schema_uri(schema_name)
    layer_info = usginmodels.get_layer(schema_uri, layer_name)

    # If data is in a sheet in an Excel file convert to CSV, otherwise just read
    if sheet_name != "N/A":
        csv_text = excel_to_csv(in_file, sheet_name)
    else:
        csv_text = open(in_file)
    csv_dict = csv.DictReader(csv_text)

    if csv_dict:
        # Pass in the the CSV as a dictionary, the schema to validate against and the layer name
        valid, errors, dataCorrected, long_fields, srs = usginmodels.validate_file(csv_dict, schema_uri, layer_name)
        print_errors(valid, errors, dataCorrected)

        try:
            if (validate_only == "false" and valid == True):
                CreateGeodatabase(path, service_name)

                arcpy.env.workspace = path + service_name + ".mdb"
                table = layer_name + "Table"

                MakeTable(table, layer_info.fields[1:][:-1], long_fields)
                InsertData(table, dataCorrected[1:], layer_info.fields[1:][:-1])
                CreateXYEventLayer(table, layer_name + "Layer", srs)
                CreateFeatureClass(layer_name + "Layer", layer_name, srs)

                # Make sure the final feature class has the same number of rows as the original table
                rowsTemp = int(arcpy.GetCount_management(table).getOutput(0))
                rowsFinal = int(arcpy.GetCount_management(layer_name).getOutput(0))
                if rowsTemp != rowsFinal:
                    rowsDeleted = rowsTemp - rowsFinal
                    if rowsDeleted == 1:
                        arcpy.AddError(str(rowsDeleted) + " row was deleted when converting the table to the feature class.")
                    else:
                        arcpy.AddError(str(rowsDeleted) + " rows were deleted when converting the table to the feature class.")
                    arcpy.AddError("Check the Lat & Long values for errors.")
                    raise Exception ("Conversion Failed.")
                else:
                    arcpy.Delete_management(table)

                arcpy.AddMessage("Conversion Successful!")

        except Exception as err:
            arcpy.AddError("Error: {0}".format(err))

    return

# Get a list of sheet names for the selected Excel file
def sheet_names(inExcel):
    wb = xlrd.open_workbook(inExcel)
    potential_sheets = [sht.name for sht in wb.sheets()]
    return potential_sheets

# Get the uri for the schema
def get_schema_uri(schema_name):
    versions_dict = {}
    models = usginmodels.get_models()
    for m in models:
      for v in m.versions:
        versions_dict[m.title + " " + v.version] = v.uri
    return versions_dict[schema_name]

# Convert the Excel sheet to CSV
def excel_to_csv(in_file, sheet_name):

    # Get the path for the folder of the Excel file (used for output of GeoDB)
    path = os.path.dirname(in_file) + "/"
    wb = xlrd.open_workbook(in_file)
    try:
        sht = wb.sheet_by_name(sheet_name)
    except:
        arcpy.AddError("Invalid Sheet Name")
        return None

    csv_rows = []
    for rownum in xrange(sht.nrows):
        row = sht.row_values(rownum)
        for colnum, col in enumerate(xrange(sht.ncols)):
            cell = sht.cell(rownum, colnum)

            # Check that conversion from unicode to utf-8 and Win-1252 encoding (used by the server) is possible
            if isinstance(cell.value, unicode):
                try:
                    cell.value = cell.value.encode("utf-8")
                    cell.value = cell.value.encode("windows-1252")
                except:
                    arcpy.AddError("Encoding Error! Found an unrecognized character in row " + str(rownum+1) + ", column " + str(colnum+1) + ": " + str(cell.value))
                    arcpy.AddError("CSV conversion failed")
                    return None

            # Excel stores #N/A with the internal code 42, change it back to #N/A
            if isinstance(cell.value, int):
                if cell.value == 42:
                    cell.value = "#N/A"

            # If the cell contains a date timestamp convert it to an iso date
            if cell.ctype == 3:
                if cell.value >= 61:
                    year, month, day, hour, minute, second = xlrd.xldate_as_tuple(cell.value, wb.datemode)
                    cell.value = datetime.datetime(year, month, day, hour, minute, second).isoformat()
                # Excel treats the first 60 days of 1900 as ambiguous (see Microsoft documentation)
                # Assume the dates are what is indicated in the cell
                else:
                    cell.value = datetime.datetime(1900, 1, 1, 0, 0, 0) + datetime.timedelta(days = cell.value - 1)
                    cell.value = cell.value.isoformat()

            # Remove decimal and trailing zeros that were added on Excel import
            if isinstance(cell.value, float):
                if cell.value == int(cell.value):
                    cell.value = '%d'%cell.value

            row[colnum] = "\""+ str(cell.value) + "\""
        csv_rows.append(','.join(row))

    return csv_rows

# Print the error messages
def print_errors(valid, errors, dataCorrected):
    # Message counts
    msgs = {'warnCount': 0, 'warnMax': 25, 'errCount': 0, 'errMax': 25, 'noteCount': 0, 'noteMax': 5}

    if valid and errors:
        arcpy.AddMessage("The document is valid if the changes below are acceptable.")
    elif valid and not errors:
        arcpy.AddMessage("The document is valid.")
    else:
        arcpy.AddMessage("Not Valid! Error messages:")

    # Only print warnings and error messages
    for e in errors:
        if "Warning!" in e:
            if msgs['warnCount'] < msgs['warnMax']:
                arcpy.AddWarning(e)
                msgs['warnCount'] += 1
            elif msgs['warnCount'] == msgs['warnMax']:
                arcpy.AddWarning("Max number of warning messages reached (" + str(msgs['warnMax']) + "). Not showing anymore warnings that are not errors.")
                msgs['warnCount'] += 1
        elif "Error!" in e:
            if msgs['errCount'] < msgs['errMax']:
                arcpy.AddError(e)
                msgs['errCount'] += 1
            elif msgs['errCount'] == msgs['errMax']:
                arcpy.AddError("Max number of error messages reached (" + str(msgs['errMax']) + "). Fix indicated errors and import again.")
                msgs['errCount'] += 1
        elif "Notice!" in e:
            if msgs['noteCount'] < msgs['noteMax']:
                arcpy.AddMessage(e)
                msgs['noteCount'] += 1
            elif msgs['noteCount'] == msgs['noteMax']:
                arcpy.AddMessage("Max number of notices reached (" + str(msgs['noteMax']) + "). Not showing anymore messages that are not warnings or errors.")
                msgs['noteCount'] += 1
        else:
            print e
    return

# Create the personal Geodatabase (Microsoft Access DB)
def CreateGeodatabase(path, name):
    arcpy.AddMessage("Creating Geodatabase ...")
    arcpy.CreatePersonalGDB_management(path, name)
    arcpy.AddMessage("Finished Creating Geodatabase.")
    return

# Create the output table, add all required fields for that table
def MakeTable(table, fields_info, long_fields):
    arcpy.AddMessage("Creating Table in ArcGIS ...")
    arcpy.CreateTable_management(env.workspace, table)

    # Add the fields to the table
    for i in range(0, len(fields_info)):
        if (long_fields[fields_info[i].field_name] == True):
           arcpy.AddField_management(table, fields_info[i].field_name, "TEXT", "", "", 2147483647)
        else:
            if fields_info[i].field_type == "string":
                arcpy.AddField_management(table, fields_info[i].field_name, "TEXT")
                arcpy.AddMessage("  " + fields_info[i].field_name + " added with type TEXT")
            elif fields_info[i].field_type == "double":
                arcpy.AddField_management(table, fields_info[i].field_name, "DOUBLE")
                arcpy.AddMessage("  " + fields_info[i].field_name + " added with type DOUBLE")
            elif fields_info[i].field_type == "dateTime":
                arcpy.AddField_management(table, fields_info[i].field_name, "DATE")
                arcpy.AddMessage("  " + fields_info[i].field_name + " added with type DATE")
            else:
                arcpy.Error(fields_info[i].field_type + " is not a valid field type for " + fields_info[i].field_name)
                return
    
    arcpy.AddMessage("Finished Creating Table.")
    return

# Insert the data rows in the the table
def InsertData(table, data, fields_info):
    arcpy.AddMessage("Inserting Rows ...")

    field_names = []
    field_types = []
    for field in fields_info:
        field_names.append(field.field_name)
        field_types.append(field.field_type)

    # If running on 10.1, use da insert cursor
    if arcpy.GetInstallInfo()['Version'] == '10.1':
        insertCur = arcpy.da.InsertCursor(table, field_names)
        for row in data:
            insertCur.insertRow(row)

    # Otherwise use original insert cursor
    else:
        insertCur = arcpy.InsertCursor(table)
        for d in data:
            row = insertCur.newRow()
            for x in range(len(d)):
                if field_types[x] == "dateTime":
                    row.setValue(field_names[x], dateutil.parser.parse(d[x]))
                elif field_types[x] == "double":
                    if d[x] == "":
                        row.setValue(field_names[x], None)
                    else:
                        row.setValue(field_names[x], d[x])
                else:
                    row.setValue(field_names[x], d[x])
            insertCur.insertRow(row)
    del row, insertCur
    
    arcpy.AddMessage("Finished Inserting Rows")
    return

# Convert the Table to an XY Event Layer in ArcGIS, using EPSG:4326 (WGS84) as the projection    
def CreateXYEventLayer(table, layer, srs):
    arcpy.AddMessage("Converting Table to XY Event Layer ...")

    # Set the spatial reference
    if srs == "EPSG:4326":
        spRef = os.path.dirname(__file__) + "\\WGS 1984.prj"
    elif srs == "EPSG:4269":
        spRef = os.path.dirname(__file__) + "\\NAD 1983.prj"
    elif srs == "EPSG:4267":
        spRef = os.path.dirname(__file__) + "\\NAD 1927.prj"
    else:
        arcpy.AddWarning("Unable to determine spatial reference system. The reference system for the data will need to be defined and then reprojected to EPSG:4326 (WGS84).")
        spRef = os.path.dirname(__file__) + "\\WGS 1984.prj"
    arcpy.AddMessage("Spatial Reference System of data is " + srs)
    
    try:
        testOpen = open(spRef)
    except:
        arcpy.AddError("Unable to find the .prj files that should be located in the same folder as the script. Download the tool again.")
        raise Exception ("Missing Needed File.")
    
    # Create the XY Event Layer
    try:
        arcpy.MakeXYEventLayer_management(table, "LongDegreeWGS84", "LatDegreeWGS84", layer, spRef)
    except:
        try:
            arcpy.MakeXYEventLayer_management(table, "LongDegree", "LatDegree", layer, spRef)
        except:
            arcpy.AddError("Unable to determine Lat and Long fields.")
            raise Exception ("Conversion Failed.")
        
    arcpy.AddMessage("Finished Converting Table.")
    return

# Create the Feature Class in ArcGIS & reproject if SRS doesn't indicate EPSG:4326 (WGS84)
def CreateFeatureClass(layer, featureClass, srs):
    arcpy.AddMessage("Creating Feature Class ....")

    arcpy.CopyFeatures_management(layer, featureClass)
    
    if srs == "EPSG:4267" or srs == "EPSG:4269":      
        if srs == "EPSG:4267":
            spRef = os.path.dirname(__file__) + "\\NAD 1927.prj"
            trans = "NAD_1927_To_WGS_1984_4"
        if srs == "EPSG:4269":
            spRef = os.path.dirname(__file__) + "\\NAD 1983.prj"
            trans = "NAD_1983_To_WGS_1984_1"
            
        inCS = spRef
        outCS = os.path.dirname(__file__) + "\\WGS 1984.prj"
        
        arcpy.AddMessage("Reprojecting from " + srs + " to EPSG:4326 (WGS84) using the transformation " + trans + "....")
        arcpy.AddWarning("If the data indicates a region other than the continental US you may need to use a different transformation.")
        
        # Reproject the feature class to WGS 84 and save in a temporary feature class 
        featureClassTemp = featureClass + "Temp"
        arcpy.Project_management(featureClass, featureClassTemp, outCS, trans, inCS)

        try:
            # Calculate XY coordinates for the points in the feature class        
            arcpy.AddXY_management(featureClassTemp)

        except:
            # Delete the temporary feature class since the calculation of the new X & Y values failed
            arcpy.Delete_management(featureClassTemp)
            
            # The default maximum number of records on which calculations can be performed is 9500.
            # Upon failure ouptut a message telling the user how to increase this number.
            installDir = arcpy.GetInstallInfo()['InstallDir']
            arcpy.AddError("The MaxLocksPerFile value needs to be increased before reprojection.")
            arcpy.AddError("Open the ArcMap Advanced Settings utility in " + installDir + "Utilities\\AdvancedArcMapSettings.exe.") 
            arcpy.AddError("Click the Editor tab and update the 'Jet Engine max # of records to calculate' value to any number larger than the number of records in the current dataset.")
            arcpy.AddError("Run the tool again.")
            raise Exception ("Reprojection Failed.")
        
        # Replace the value in the Lat & Long fields with the calculated XY coordinates
        # Update the SRS column to WGS 84
        rows = arcpy.UpdateCursor(featureClassTemp)
        for row in rows:
            try:
                row.LatDegree = row.POINT_Y
                row.LongDegree = row.POINT_X
            except:
                try:
                    row.LatDegreeWGS84 = row.POINT_Y
                    row.LongDegreeWGS84 = row.POINT_X
                except:
                    raise Exception ("Unable to determine Lat & Long columns. Conversion Failed.")
            row.SRS = "EPSG:4326"
            rows.updateRow(row)
            
        # Delete cursor and row objects to remove locks on the data 
        del row, rows
        
        arcpy.DeleteField_management(featureClassTemp, ["POINT_Y", "POINT_X"])
        arcpy.AddMessage("Finished Reprojecting.")
        
        # Delete the original feature class and rename the temporary feature class the same as the original
        arcpy.Delete_management(featureClass)
        arcpy.Rename_management(featureClassTemp, featureClass)
       
    arcpy.AddMessage("Finished Creating Feature Class.")
    return

if __name__ == "__main__":
    main()