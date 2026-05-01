#!/usr/bin/env python

import re

import agate

from csvkit.cli import CSVKitUtility, parse_column_identifiers


class NullOrderFirst:
    def __eq__(self, other):
        return isinstance(other, NullOrderFirst)

    def __gt__(self, other):
        return False

    def __lt__(self, other):
        return True


class NullOrderLast(agate.NullOrder):
    pass


def _natural_sort_key(s):
    if not isinstance(s, str):
        return s
    return tuple(int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s))


def ignore_case_sort(key, null_order=None, natural_sort=False):
    if null_order is None:
        null_order = ['last'] * len(key)
    if len(null_order) < len(key):
        null_order = null_order + ['last'] * (len(key) - len(null_order))

    def inner(row):
        result = []
        for i, n in enumerate(key):
            if row[n] is None:
                if null_order[i] == 'first':
                    result.append(NullOrderFirst())
                else:
                    result.append(NullOrderLast())
            elif natural_sort and isinstance(row[n], str):
                if isinstance(row[n], str):
                    val = row[n].upper() if row[n] else row[n]
                else:
                    val = row[n]
                result.append(_natural_sort_key(val))
            elif isinstance(row[n], str):
                result.append(row[n].upper() if row[n] else row[n])
            else:
                result.append(row[n])
        return tuple(result)

    return inner


def natural_sort(key, null_order=None):
    if null_order is None:
        null_order = ['last'] * len(key)
    if len(null_order) < len(key):
        null_order = null_order + ['last'] * (len(key) - len(null_order))

    def inner(row):
        result = []
        for i, n in enumerate(key):
            if row[n] is None:
                if null_order[i] == 'first':
                    result.append(NullOrderFirst())
                else:
                    result.append(NullOrderLast())
            else:
                result.append(_natural_sort_key(row[n]))
        return tuple(result)

    return inner


def standard_sort(key, null_order=None):
    if null_order is None:
        null_order = ['last'] * len(key)
    if len(null_order) < len(key):
        null_order = null_order + ['last'] * (len(key) - len(null_order))

    def inner(row):
        result = []
        for i, n in enumerate(key):
            if row[n] is None:
                if null_order[i] == 'first':
                    result.append(NullOrderFirst())
                else:
                    result.append(NullOrderLast())
            else:
                result.append(row[n])
        return tuple(result)

    return inner


class CSVSort(CSVKitUtility):
    description = 'Sort CSV files. Like the Unix "sort" command, but for tabular data.'

    def add_arguments(self):
        self.argparser.add_argument(
            '-n', '--names', dest='names_only', action='store_true',
            help='Display column names and indices from the input CSV and exit.')
        self.argparser.add_argument(
            '-c', '--columns', dest='columns',
            help='A comma-separated list of column indices, names or ranges to sort by, e.g. "1,id,3-5". '
                 'Defaults to all columns.')
        self.argparser.add_argument(
            '-r', '--reverse', dest='reverse', action='store_true',
            help='Sort in descending order.')
        self.argparser.add_argument(
            '-i', '--ignore-case', dest='ignore_case', action='store_true',
            help='Perform case-independent sorting.')
        self.argparser.add_argument(
            '-N', '--natural-sort', dest='natural_sort', action='store_true',
            help='Perform natural sort (human-friendly sorting of strings with numbers, e.g. "file2" before "file10").')
        self.argparser.add_argument(
            '--null-order', dest='null_order',
            help='A comma-separated list of null handling strategies for each sort key. '
                 'Use "first" to place nulls at the beginning, "last" to place nulls at the end. '
                 'e.g. "first,last" for two sort keys. Defaults to "last" for all keys.')
        self.argparser.add_argument(
            '-y', '--snifflimit', dest='sniff_limit', type=int, default=1024,
            help='Limit CSV dialect sniffing to the specified number of bytes. '
                 'Specify "0" to disable sniffing entirely, or "-1" to sniff the entire file.')
        self.argparser.add_argument(
            '-I', '--no-inference', dest='no_inference', action='store_true',
            help='Disable type inference (and --locale, --date-format, --datetime-format, --no-leading-zeroes) '
                 'when parsing the input.')

    def _parse_null_order(self, null_order_str, num_keys, columns=None):
        if not null_order_str:
            return ['last'] * num_keys

        null_order = []
        for item in null_order_str.split(','):
            item = item.strip().lower()
            if item not in ('first', 'last'):
                self.argparser.error(f'Invalid null order value: "{item}". Must be "first" or "last".')
            null_order.append(item)

        num_null_order = len(null_order)
        if num_null_order != num_keys:
            if columns:
                columns_str = ', '.join([f'"{c}"' for c in columns])
                self.argparser.error(
                    f'Number of null-order values ({num_null_order}) does not match number of sort keys ({num_keys}). '
                    f'Sort keys are: {columns_str}. '
                    f'Please provide {num_keys} null-order values (e.g. "--null-order {",".join(["first"]*num_keys)}").'
                )
            else:
                self.argparser.error(
                    f'Number of null-order values ({num_null_order}) does not match number of sort keys ({num_keys}). '
                    f'Please provide {num_keys} null-order values (e.g. "--null-order {",".join(["first"]*num_keys)}").'
                )

        return null_order

    def main(self):
        if self.args.names_only:
            self.print_column_names()
            return

        if self.additional_input_expected():
            self.argparser.error('You must provide an input file or piped data.')

        sniff_limit = self.args.sniff_limit if self.args.sniff_limit != -1 else None
        table = agate.Table.from_csv(
            self.input_file,
            skip_lines=self.args.skip_lines,
            sniff_limit=sniff_limit,
            column_types=self.get_column_types(),
            **self.reader_kwargs,
        )

        key = parse_column_identifiers(
            self.args.columns,
            table.column_names,
            self.get_column_offset(),
        )

        key_list = list(key)
        key_names = [table.column_names[idx] for idx in key_list]
        null_order = self._parse_null_order(self.args.null_order, len(key_list), key_names)

        if self.args.ignore_case and self.args.natural_sort:
            key = ignore_case_sort(key_list, null_order=null_order, natural_sort=True)
        elif self.args.ignore_case:
            key = ignore_case_sort(key_list, null_order=null_order, natural_sort=False)
        elif self.args.natural_sort:
            key = natural_sort(key_list, null_order=null_order)
        elif self.args.null_order:
            key = standard_sort(key_list, null_order=null_order)

        table = table.order_by(key, reverse=self.args.reverse)
        table.to_csv(self.output_file, **self.writer_kwargs)


def launch_new_instance():
    utility = CSVSort()
    utility.run()


if __name__ == '__main__':
    launch_new_instance()
