#!/usr/bin/env python

import re
import sys
from argparse import FileType

import agate

from csvkit.cli import CSVKitUtility
from csvkit.grep import FilteringCSVReader, ExpressionError


class CSVGrep(CSVKitUtility):
    description = 'Search CSV files. Like the Unix "grep" command, but for tabular data.'
    override_flags = ['L', 'I']

    def add_arguments(self):
        self.argparser.add_argument(
            '-n', '--names', dest='names_only', action='store_true',
            help='Display column names and indices from the input CSV and exit.')
        self.argparser.add_argument(
            '-c', '--columns', dest='columns',
            help='A comma-separated list of column indices, names or ranges to be searched, e.g. "1,id,3-5".')
        self.argparser.add_argument(
            '-m', '--match', dest="pattern", action='store',
            help='A string to search for.')
        self.argparser.add_argument(
            '-r', '--regex', dest='regex', action='store',
            help='A regular expression to match.')
        self.argparser.add_argument(
            '-f', '--file', dest='matchfile', type=FileType('r'), action='store',
            help='A path to a file. For each row, if any line in the file (stripped of line separators) is an exact '
                 'match of the cell value, the row matches.')
        self.argparser.add_argument(
            '-i', '--invert-match', dest='inverse', action='store_true',
            help='Select non-matching rows, instead of matching rows.')
        self.argparser.add_argument(
            '-a', '--any-match', dest='any_match', action='store_true',
            help='Select rows in which any column matches, instead of all columns.')
        self.argparser.add_argument(
            '-w', '--where', dest='where_expr', action='store',
            help='A SQL-like WHERE clause expression for complex filtering. '
                 'All operators are case-insensitive. '
                 'Supported operators and syntax:\n'
                 '\n'
                 'LOGICAL OPERATORS:\n'
                 '  AND           - Logical AND\n'
                 '  OR            - Logical OR\n'
                 '  NOT           - Logical NOT\n'
                 '\n'
                 'COMPARISON OPERATORS:\n'
                 '  =             - Equal to (e.g., column = \'value\')\n'
                 '  !=, <>        - Not equal to\n'
                 '  >, >=         - Greater than / Greater than or equal\n'
                 '  <, <=         - Less than / Less than or equal\n'
                 '\n'
                 'PATTERN MATCHING:\n'
                 '  LIKE          - Pattern matching with wildcards\n'
                 '                  %% matches 0 or more characters\n'
                 '                  _ matches exactly 1 character\n'
                 '                  e.g., name LIKE \'A%%\'\n'
                 '  RLIKE         - Regular expression matching\n'
                 '                  e.g., name RLIKE \'^A.*$\'\n'
                 '\n'
                 'SET MEMBERSHIP:\n'
                 '  IN (...)      - Value in a list (e.g., category IN (\'a\', \'b\', \'c\'))\n'
                 '  NOT IN (...)  - Value NOT in a list\n'
                 '\n'
                 'NULL CHECKING:\n'
                 '  IS NULL       - Value is empty or blank\n'
                 '  IS NOT NULL   - Value is not empty or blank\n'
                 '\n'
                 'GROUPING:\n'
                 '  ( ... )       - Parentheses to group expressions\n'
                 '\n'
                 'LITERALS:\n'
                 '  \'string\'    - String values in single quotes\n'
                 '  123, 123.45   - Numeric values\n'
                 '  \"column name\" - Column names with spaces in double quotes\n'
                 '\n'
                 'EXAMPLES:\n'
                 '  -w "a = 1 AND b LIKE \'%%test%%\'"'
                 '  -w "category IN (\'fruit\', \'vegetable\') AND price > 10"'
                 '  -w "name IS NOT NULL OR description IS NULL"'
                 '  -w "(status = \'active\') OR (id IN (1, 2, 3))"'
                 '\n'
                 'When using --where, the -c, -m, -r, -f, and -a options are ignored.')

    def main(self):
        if self.args.names_only:
            self.print_column_names()
            return

        if self.additional_input_expected():
            sys.stderr.write('No input file or piped data provided. Waiting for standard input:\n')

        if self.args.where_expr:
            self._main_with_where()
        else:
            self._main_legacy()

    def _main_with_where(self):
        reader_kwargs = self.reader_kwargs
        writer_kwargs = self.writer_kwargs
        if writer_kwargs.pop('line_numbers', False):
            reader_kwargs['line_numbers'] = True

        rows, column_names, _ = self.get_rows_and_column_names_and_column_ids(**reader_kwargs)

        try:
            filter_reader = FilteringCSVReader(
                rows, header=False, expression=self.args.where_expr,
                inverse=self.args.inverse, column_names=column_names)
        except ExpressionError as e:
            self.argparser.error(f'Invalid expression: {e}')

        output = agate.csv.writer(self.output_file, **writer_kwargs)
        output.writerow(column_names)

        for row in filter_reader:
            output.writerow(row)

    def _main_legacy(self):
        if not self.args.columns:
            self.argparser.error('You must specify at least one column to search using the -c option.')

        if self.args.regex is None and self.args.pattern is None and self.args.matchfile is None:
            self.argparser.error('One of -r, -m or -f must be specified, unless using the -n option.')

        reader_kwargs = self.reader_kwargs
        writer_kwargs = self.writer_kwargs
        if writer_kwargs.pop('line_numbers', False):
            reader_kwargs['line_numbers'] = True

        rows, column_names, column_ids = self.get_rows_and_column_names_and_column_ids(**reader_kwargs)

        if self.args.regex:
            pattern = re.compile(self.args.regex)
        elif self.args.matchfile:
            lines = {line.rstrip() for line in self.args.matchfile}
            self.args.matchfile.close()

            def pattern(x):
                return x in lines
        else:
            pattern = self.args.pattern

        patterns = {column_id: pattern for column_id in column_ids}
        filter_reader = FilteringCSVReader(rows, header=False, patterns=patterns,
                                           inverse=self.args.inverse, any_match=self.args.any_match)

        output = agate.csv.writer(self.output_file, **writer_kwargs)
        output.writerow(column_names)

        for row in filter_reader:
            output.writerow(row)


def launch_new_instance():
    utility = CSVGrep()
    utility.run()


if __name__ == '__main__':
    launch_new_instance()
