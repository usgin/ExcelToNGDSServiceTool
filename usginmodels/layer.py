from itertools import count, groupby
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

        # Remove trailing and leading whitespace from field names in csv file
        for i, field in enumerate(csv_text.fieldnames):
            csv_text.fieldnames[i] = field.strip()

        for i, row in enumerate(csv_text):
            rowCorrected = []
            for f in self.fields[1:][:-1]:

                # Check required fields. Immediately return when a required field is not found.
                try:
                    data = row[f.field_name]
                except:
                    if f.field_optional == False:
                        msg = "Error! " + f.field_name + " is a required field but was not found in the imported file."
                        valid, messages = addMessage(-1, False, msg, messages)
                        messages = format_messages(messages)
                        return valid, messages, [], {}, ""
                    else:
                        msg = "Warning! " + f.field_name + " was not found in the imported file but this is not a required field so ignoring."
                        valid, messages = addMessage(-1, valid, msg, messages)
                        data = ""

                # Check encoding of data
                encoding_error = f.check_encoding(data)
                valid, messages = addMessage(i, valid, encoding_error, messages)

                if not encoding_error:
                    # Fix minor formatting issues
                    format_error, data = f.fix_format(data)
                    valid, messages = addMessage(i, valid, format_error, messages)

                    # Check data types
                    type_error, data = f.validate_field(data)
                    valid, messages = addMessage(i,valid, type_error, messages)

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

        messages = format_messages(messages)
        return valid, messages, dataCorrected, long_fields, srs

def get_primary_uri_field(fields):
    """Find the first field name containing URI"""

    for f in fields:
        if "URI" in f.field_name:
            return f

    return None

def addMessage(row_num, valid, new_msg, messages):
    """ Add error message to the list of errors and set the validity"""

    if new_msg:
        if "Error" in new_msg:
            valid = False
        match = False

        for msg in messages:
            if new_msg == msg[1]:
                match = True
                if row_num + 1 != msg[0][-1]:
                    msg[0].append(row_num + 1)
                    return valid, messages

        if match == False:
            messages.append([[row_num + 1], new_msg])

    return valid, messages

def format_messages(messages):
    """ Format the error messages by turing a list into a range where appropriate
        For example: 1,2,3,4,7,8,9 becomes 1-4,7,8-9 """

    messages_formatted = []
    for msg in messages:
        G = (list(x) for _,x in groupby(msg[0], lambda x,c=count(): next(c)-x))
        rows_list = ",".join("-".join(map(str,(g[0],g[-1])[:len(g)])) for g in G)

        if "," in rows_list or "-" in rows_list:
            messages_formatted.append("Rows " + rows_list + " " + msg[1])
        else:
            messages_formatted.append("Row " + rows_list + " " + msg[1])

    return messages_formatted