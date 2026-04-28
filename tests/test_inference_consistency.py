#!/usr/bin/env python
"""
Cross-tool type inference consistency tests.

Verifies that csvsql, csvstat, and csvjson produce consistent type inference
results for the same CSV input with the same parameters.
"""
import io
import json
import re
import unittest

from csvkit.utilities.csvstat import CSVStat
from csvkit.utilities.csvsql import CSVSQL
from csvkit.utilities.csvjson import CSVJSON

from tests.utils import CSVKitTestCase


AGATE_TO_SQL_MAP = {
    'Text': 'VARCHAR',
    'Date': 'DATE',
    'Number': 'DECIMAL',
    'Boolean': 'BOOLEAN',
    'TimeDelta': 'DATETIME',
    'DateTime': 'TIMESTAMP',
}


def get_csvstat_types(csv_file, args=None):
    """Get column types from csvstat --csv output."""
    args = args or []
    output_file = io.StringIO()
    utility = CSVStat(['--csv', csv_file] + args, output_file)
    utility.run()
    output = output_file.getvalue()
    output_file.close()

    lines = output.strip().split('\n')
    header = lines[0].split(',')
    type_idx = header.index('type')
    name_idx = header.index('column_name')

    types = {}
    for line in lines[1:]:
        row = line.split(',')
        col_name = row[name_idx]
        col_type = row[type_idx]
        types[col_name] = col_type

    return types


def get_csvsql_types(csv_file, args=None):
    """Get column types from csvsql --tables output."""
    args = args or []
    output_file = io.StringIO()
    utility = CSVSQL(['--tables', 'test_table', csv_file] + args, output_file)
    utility.run()
    output = output_file.getvalue()
    output_file.close()

    types = {}
    lines = output.strip().split('\n')
    for line in lines[1:-1]:
        line = line.strip().rstrip(',')
        if not line or 'CREATE TABLE' in line:
            continue
        parts = line.split(None, 1)
        if len(parts) >= 2:
            col_name = parts[0]
            rest = parts[1]
            sql_type = rest.split()[0]
            if 'NOT NULL' in rest:
                sql_type = rest.split('NOT NULL')[0].strip()
            types[col_name] = sql_type

    return types


def get_csvjson_value_types(csv_file, args=None):
    """Get inferred types from csvjson output by checking value types."""
    args = args or []
    output_file = io.StringIO()
    utility = CSVJSON([csv_file] + args, output_file)
    utility.run()
    output = output_file.getvalue()
    output_file.close()

    data = json.loads(output)
    if not data:
        return {}

    types = {}
    first_row = data[0]
    for key, value in first_row.items():
        if value is None:
            types[key] = 'None'
        elif isinstance(value, bool):
            types[key] = 'Boolean'
        elif isinstance(value, (int, float)):
            types[key] = 'Number'
        else:
            types[key] = 'TextOrDate'

    return types


class TestTypeInferenceConsistency(unittest.TestCase):
    def test_default_types_consistency(self):
        """Test that all tools infer the same types with default parameters."""
        csv_file = 'examples/testfixed_converted.csv'

        csvstat_types = get_csvstat_types(csv_file)
        csvsql_types = get_csvsql_types(csv_file)
        csvjson_types = get_csvjson_value_types(csv_file)

        self.assertEqual(set(csvstat_types.keys()), set(csvsql_types.keys()))

        for col_name, agate_type in csvstat_types.items():
            expected_sql_type = AGATE_TO_SQL_MAP[agate_type]
            actual_sql_type = csvsql_types[col_name]
            self.assertEqual(
                actual_sql_type, expected_sql_type,
                f"Column '{col_name}': csvstat says {agate_type}, csvsql says {actual_sql_type}"
            )

        for col_name, agate_type in csvstat_types.items():
            if agate_type == 'Number':
                if csvjson_types[col_name] == 'None':
                    continue
                self.assertEqual(
                    csvjson_types[col_name], 'Number',
                    f"Column '{col_name}': csvstat says Number, csvjson value is {csvjson_types[col_name]}"
                )
            elif agate_type == 'Boolean':
                if csvjson_types[col_name] == 'None':
                    continue
                self.assertEqual(
                    csvjson_types[col_name], 'Boolean',
                    f"Column '{col_name}': csvstat says Boolean, csvjson value is {csvjson_types[col_name]}"
                )

    def test_no_leading_zeroes_consistency(self):
        """Test --no-leading-zeroes parameter consistency across tools."""
        csv_file = 'examples/test_no_leading_zeroes.csv'

        csvstat_types = get_csvstat_types(csv_file, ['--no-leading-zeroes'])
        csvsql_types = get_csvsql_types(csv_file, ['--no-leading-zeroes'])
        csvjson_types = get_csvjson_value_types(csv_file, ['--no-leading-zeroes'])

        self.assertEqual(csvstat_types['a'], 'Text')
        self.assertEqual(csvstat_types['b'], 'Text')
        self.assertEqual(csvstat_types['c'], 'Number')

        self.assertEqual(csvsql_types['a'], 'VARCHAR')
        self.assertEqual(csvsql_types['b'], 'VARCHAR')
        self.assertEqual(csvsql_types['c'], 'DECIMAL')

        self.assertEqual(csvjson_types['a'], 'TextOrDate')
        self.assertEqual(csvjson_types['b'], 'TextOrDate')
        self.assertEqual(csvjson_types['c'], 'Number')

    def test_no_leading_zeroes_vs_default(self):
        """Verify --no-leading-zeroes changes behavior compared to default."""
        csv_file = 'examples/test_no_leading_zeroes.csv'

        csvstat_types_default = get_csvstat_types(csv_file, [])
        csvstat_types_no_leading = get_csvstat_types(csv_file, ['--no-leading-zeroes'])

        csvsql_types_default = get_csvsql_types(csv_file, [])
        csvsql_types_no_leading = get_csvsql_types(csv_file, ['--no-leading-zeroes'])

        csvjson_types_default = get_csvjson_value_types(csv_file, [])
        csvjson_types_no_leading = get_csvjson_value_types(csv_file, ['--no-leading-zeroes'])

        self.assertEqual(csvstat_types_default['a'], 'Number')
        self.assertEqual(csvstat_types_no_leading['a'], 'Text')

        self.assertEqual(csvsql_types_default['a'], 'DECIMAL')
        self.assertEqual(csvsql_types_no_leading['a'], 'VARCHAR')

        self.assertEqual(csvjson_types_default['a'], 'Number')
        self.assertEqual(csvjson_types_no_leading['a'], 'TextOrDate')

    def test_blanks_consistency(self):
        """Test --blanks parameter consistency across tools."""
        csv_file = 'examples/blanks.csv'

        csvstat_types_no_blanks = get_csvstat_types(csv_file, [])
        csvstat_types_blanks = get_csvstat_types(csv_file, ['--blanks'])

        csvsql_types_no_blanks = get_csvsql_types(csv_file, [])
        csvsql_types_blanks = get_csvsql_types(csv_file, ['--blanks'])

        for col_name in csvstat_types_no_blanks:
            if csvstat_types_no_blanks[col_name] == 'Boolean':
                self.assertEqual(csvstat_types_blanks[col_name], 'Text')
                self.assertEqual(csvsql_types_no_blanks[col_name], 'BOOLEAN')
                self.assertEqual(csvsql_types_blanks[col_name], 'VARCHAR')

    def test_date_format_consistency(self):
        """Test --date-format parameter consistency across tools."""
        csv_file = 'examples/test_date_format.csv'

        csvstat_types_default = get_csvstat_types(csv_file, [])
        csvstat_types_with_format = get_csvstat_types(csv_file, ['--date-format', '%d/%m/%Y'])

        csvsql_types_default = get_csvsql_types(csv_file, [])
        csvsql_types_with_format = get_csvsql_types(csv_file, ['--date-format', '%d/%m/%Y'])

        for col_name in csvstat_types_default:
            default_type = csvstat_types_default[col_name]
            formatted_type = csvstat_types_with_format[col_name]

            self.assertEqual(csvsql_types_default[col_name], AGATE_TO_SQL_MAP[default_type])
            self.assertEqual(csvsql_types_with_format[col_name], AGATE_TO_SQL_MAP[formatted_type])


if __name__ == '__main__':
    unittest.main()
