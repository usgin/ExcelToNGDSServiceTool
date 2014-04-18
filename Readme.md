# Excel To NGDS Service Tool

This tool validates and converts a spreadsheet in an Excel content model to a geodatabase ready to be deployed as a NGDS Service.

### Requirements:
- ArcGIS 10.1 or 10.2 (See notes below if you have ArcGIS 10.0)
- Python 2.6

### Installation:
- Download the Zip file.
- Save the entire unzipped folder to C:\Users\[user]\Documents\ArcGIS\
- Open ArcMap
- Open the Catalog window (within ArcMap)
- Navigate in Catalog to your Home directory, then choose the Documents\ArcGIS folder
- Open the ‘ExcelToNGDSServiceTool’ folder saved in Step 2
- Open the Toolbox ‘ExcelToNGDSService’
- Double-click the script ‘Excel to Service’ to start the tool

Follow the instructions in the pdf included in the folder or at:
https://docs.google.com/document/d/1H08dObu5pWze7g3sSap3uDcI4DwYzuIEMfcP0V7Xj9s/edit?usp=sharing

#### ArcGIS 10.0 Suggestions:
The previous version of the tool for ArcGIS 10.0 is no longer supported. If you only have access to ArcGIS 10.0 there are two options:
- Download a copy of the tool with the tag [v4.1-forArcGIS10.0](https://github.com/usgin/ExcelToNGDSServiceTool/tree/v4.1-forArcGIS10.0). This version is outdated and while it will run and validate properly, data following a newer content model will not not be able to be run through the tool.
- A better alternative might be to validate the data through the online [CM Validator tool] (http://schemas.usgin.org/validate/cm) and then make your geodatabase manually.

Developed by Jessica Good Alisdairi at the Arizona Geological Survey.
May 2013