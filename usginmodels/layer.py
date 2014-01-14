import re
from field import Field

class Layer():

    layer_name = ""
    fields = []

    def __init__(self, layer, fields_dict):
        self.layer_name = layer
        self.fields = [Field(f) for f in fields_dict]


    def validate_file(self, csv_text):
        messages = []
        valid = True

        # Create the object for the corrected data and don't include the first field (OBJECTID) or last field (Shape)
        dataCorrected = []
        dataCorrected.append([f.field_name for f in self.fields[1:][:-1]])

        used_uris = []
        primary_uri_field = get_primary_uri_field(self.fields[1:][:-1])

        temp_units = ""
        srs = ""
        long_fields = {}

        for i, row in enumerate(csv_text):
            rowCorrected = []
            for f in self.fields[1:][:-1]:

                # Check required fields. Immediately return when a required field is not found.
                try:
                    data = row[f.field_name]
                except:
                    if f.field_optional == False:
                        messages.append("Error! " + f.field_name + " is a required field but was not found in the imported file.")
                        return False, messages, [], {}, ""
                    else:
                        msg = "Warning! " + f.field_name + " was not found in the imported file but this is not a required field so ignoring."
                        if not msg in messages:
                            messages.append(msg)
                        data = ""

                # Check encoding of data
                encoding_error = check_encoding(data)
                valid, messages = addMessage(i, valid, encoding_error, messages)

                if not encoding_error:
                    # Check data types
                    type_error, data = f.validate_field(data)
                    valid, messages = addMessage(i,valid, type_error, messages)

                    # Fix minor formatting issues
                    format_error, data = f.fix_format(data)
                    valid, messages = addMessage(i, valid, format_error, messages)

                    # Check URIs
                    uri_error, data, used_uris = f.check_uri(data, primary_uri_field, used_uris)
                    valid, messages = addMessage(i, valid, uri_error, messages)

                    # Check temperature units
                    temp_units_error, data, temp_units = f.check_temp_units(data, temp_units)
                    valid, messages = addMessage(i, valid, temp_units_error, messages)

                    # Check SRS
                    srs_error, data, srs = f.check_srs(data, srs)
                    valid, messages = addMessage(i, valid, srs_error, messages)

                    # Check Domain
                    domain_error, data = f.check_domain(data)
                    valid, messages = addMessage(i, valid, domain_error, messages)

                    # Check length of data
                    long_fields = f.check_field_length(data, long_fields)

                rowCorrected.append(data)
            dataCorrected.append(rowCorrected)

        return valid, messages, dataCorrected, long_fields, srs

def get_primary_uri_field(fields):
    """Find the first field name containing URI"""

    for f in fields:
        if "URI" in f.field_name:
            return f

    return None

def check_encoding(data):
    """Check that conversion to utf-8 and Win-1252 encoding (used by the server) is possible"""
    msg = None

    try:
        data = data.encode("utf-8")
        data = data.encode("windows-1252")
    except:
        msg = "Encoding Error! Found an unrecognized character in " + data + "."

    return msg

def addMessage(row_num, valid, new_msg, messages):
    """ Add error message to the list of errors and set the validity"""

    if new_msg:
        if "Error" in new_msg:
            valid = False

        # If the message is already in the messages list add the row number to the current message
        match = None
        for i, msg in enumerate(messages):
            match = re.search("Rows? ([\d,?]*) " + new_msg, msg)
            if match:
                messages[i] = "Rows " + match.group(1) + "," + str(row_num + 1) + " " + new_msg
                return valid, messages
        # If the message is not already in the messages list add it
        if not match:
            messages.append("Row " + str(row_num + 1) + " " + new_msg)
    return valid, messages