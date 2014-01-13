# contentmodels

A library defining an API for working with [USGIN Content Models](http://schemas.usgin.org/models) in Python.

## Usage

Start by importing the module

```python
import usginmodels
```

This exposes several important functions:

### usginmodels.refresh

Checks http://schemas.usgin.org/contentmodels.json for the most up-to-date description of available content models

Example Usage:

```python
usginmodels.refresh()
```

### usginmodels.get_models

Returns a list of [ContentModel](#contentmodels) objects that represent the models available from USGIN. See below
for a description of the capabilities of [ContentModel](#contentmodels) objects.

Example Usage:

```python
models = usginmodels.get_models
```

### usginmodels.get_uris(uri)

Pass in a URI as a string and a model URI and a version URI are returned. If a version URI can't be determined an empty string will be returned.

Example Usage:

```python
model_uri, version_uri = usginmodels.get_uris("http://schemas.usgin.org/uri-gin/ngds/dataschema/activefault")
model_uri, version_uri = usginmodels.get_uris("http://schemas.usgin.org/uri-gin/ngds/dataschema/activefault/1.2")
```

### usginmodels.get_model(uri)

Pass in a URI as a string and a model object will be returned. If the URI is invalid, an InvalidUri exception will be thrown.

```python
model = usginmodels.get_model("http://schemas.usgin.org/uri-gin/ngds/dataschema/activefault/1.1")
model = usginmodels.get_model("http://schemas.usgin.org/uri-gin/ngds/dataschema/activefault")
```

### usginmodels.get_version(uri)

Pass in a URI as a string and a version object will be returned. If the version is not specified in the URI the latest version will be returned. If the URI is invalid, an InvalidUri exception will be thrown.

```python
version = usginmodels.get_version("http://schemas.usgin.org/uri-gin/ngds/dataschema/activefault/1.1")
version = usginmodels.get_version("http://schemas.usgin.org/uri-gin/ngds/dataschema/activefault")
```

### usginmodels.get_layer(uri, layer_name = "")

Pass in a URI as a string and optionally, a layer name, and a layer object will be returned. If the version is not specified in the URI the latest version will be used. If the layer is not specified and a multilayer model is being requested, an exception will be thrown.

```python
layer = usginmodels.get_layer("http://schemas.usgin.org/uri-gin/ngds/dataschema/activefault/1.1")
layer = usginmodels.get_layer("http://schemas.usgin.org/uri-gin/ngds/dataschema/activefault")
layer = usginmodels.get_layer("http://schemas.usgin.org/uri-gin/ngds/dataschema/rockchemistry/0.4", 'USeries')
layer = usginmodels.get_layer("http://schemas.usgin.org/uri-gin/ngds/dataschema/rockchemistry", 'USeries')
```

### usginmodels.validate_file(csv_file, uri, layer_name = "")

Pass in a URI as a string, and a **file-like object** that represents a CSV file. The layer name is **optional** but will error if the model is multi-layered.

Returned:
 1. a boolean specifying if the data is Valid* or not
 2. a list of messages**
 3. a list of lists with the data corrected to conform to NGDS parameters
 4. a dictionary with field names as the key and True or False as the value representing whether or not any data in that field is over 255 characters in length
 5. a string indicating the spatial reference system of the dataset

\* If a file is returned as Valid but the messages list is not empty, the file is valid only if the corrected data is used.

\** The messages list returns three types of messages, differentiated by the the words Notice!, Warning! and Error!.
- **Notice!**: These are messages which indicate basic formatting changes made by the validation routine to the data, such as whitespace removed or the required / added to the end of a resource URI.
- **Warning!**: These are messages which indicate issues that the validation routine attempts to correct programmatically. For example, if a field is supposed to be double and is a required field, but the data is blank, the placeholder -9999 will be inserted as the data. The user will need to review these message to verify that the changes made by the validation routine are acceptable. If not, manual changes will need to be made and the validation routine run again.
- **Error!**: These are messages which indicate issues which will cause the file to be invalid and which need manual correction by the user before running the validation routine again.

Example Usage:

```python
import csv

csv_file = open("AZRockChemistryUSeries.csv", "r")
valid, messages, dataCorrected, long_fields, srs = usginmodels.validate_file(
    csv_file,
    "http://schemas.usgin.org/uri-gin/ngds/dataschema/rockchemistry",
    "USeries"
)

if valid and messages:
    print "The document is valid if the changes below are acceptable."
elif valid and not messages:
    print "The document is valid."
else:
   print "Not Valid! Error messages:"
   
for m in messages:
    if "Warning!" in m:
        print "* " + m
    elif "Error!" in m:
        print m
    elif "Notice!" in m:
        print m
    else:
        print m
```