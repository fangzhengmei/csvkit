#!/usr/bin/env python
import csv

QUOTING_CHOICES = sorted(getattr(csv, name) for name in dir(csv) if name.startswith('QUOTE_'))


def add_input_dialect_arguments(parser, override_flags=''):
    if 'd' not in override_flags:
        parser.add_argument(
            '-d', '--delimiter', dest='delimiter',
            help='Delimiting character of the input CSV file.')
    if 't' not in override_flags:
        parser.add_argument(
            '-t', '--tabs', dest='tabs', action='store_true',
            help='Specify that the input CSV file is delimited with tabs. Overrides "-d".')
    if 'q' not in override_flags:
        parser.add_argument(
            '-q', '--quotechar', dest='quotechar',
            help='Character used to quote strings in the input CSV file.')
    if 'u' not in override_flags:
        parser.add_argument(
            '-u', '--quoting', dest='quoting', type=int, choices=QUOTING_CHOICES,
            help='Quoting style used in the input CSV file: 0 quote minimal, 1 quote all, '
                 '2 quote non-numeric, 3 quote none.')
    if 'b' not in override_flags:
        parser.add_argument(
            '-b', '--no-doublequote', dest='doublequote', action='store_false',
            help='Whether or not double quotes are doubled in the input CSV file.')
    if 'p' not in override_flags:
        parser.add_argument(
            '-p', '--escapechar', dest='escapechar',
            help='Character used to escape the delimiter if --quoting 3 ("quote none") is specified and to escape '
                 'the QUOTECHAR if --no-doublequote is specified.')
    if 'z' not in override_flags:
        parser.add_argument(
            '-z', '--maxfieldsize', dest='field_size_limit', type=int,
            help='Maximum length of a single field in the input CSV file.')
    if 'S' not in override_flags:
        parser.add_argument(
            '-S', '--skipinitialspace', dest='skipinitialspace', action='store_true',
            help='Ignore whitespace immediately following the delimiter.')


def add_output_dialect_arguments(parser):
    parser.add_argument(
        '-D', '--out-delimiter', dest='out_delimiter',
        help='Delimiting character of the output file.')
    parser.add_argument(
        '-T', '--out-tabs', dest='out_tabs', action='store_true',
        help='Specify that the output file is delimited with tabs. Overrides "-D".')
    parser.add_argument(
        '-A', '--out-asv', dest='out_asv', action='store_true',
        help='Specify that the output file is delimited with the ASCII unit separator and record separator. '
             'Overrides "-T", "-D" and "-M".')
    parser.add_argument(
        '-Q', '--out-quotechar', dest='out_quotechar',
        help='Character used to quote strings in the output file.')
    parser.add_argument(
        '-U', '--out-quoting', dest='out_quoting', type=int, choices=QUOTING_CHOICES,
        help='Quoting style used in the output file: 0 quote minimal, 1 quote all, '
             '2 quote non-numeric, 3 quote none.')
    parser.add_argument(
        '-B', '--out-no-doublequote', dest='out_doublequote', action='store_false',
        help='Whether or not double quotes are doubled in the output file.')
    parser.add_argument(
        '-P', '--out-escapechar', dest='out_escapechar',
        help='Character used to escape the delimiter in the output file if --quoting 3 ("Quote None") is '
             'specified and to escape the QUOTECHAR if --out-no-doublequote is specified.')
    parser.add_argument(
        '-M', '--out-lineterminator', dest='out_lineterminator',
        help='Character used to terminate lines in the output file.')


def extract_input_dialect_kwargs(args):
    kwargs = {}

    field_size_limit = getattr(args, 'field_size_limit')
    if field_size_limit is not None:
        csv.field_size_limit(field_size_limit)

    if args.tabs:
        kwargs['delimiter'] = '\t'
    elif args.delimiter:
        kwargs['delimiter'] = args.delimiter

    for arg in ('quotechar', 'quoting', 'doublequote', 'escapechar', 'skipinitialspace'):
        value = getattr(args, arg)
        if value is not None:
            kwargs[arg] = value

    if getattr(args, 'no_header_row', None):
        kwargs['header'] = not args.no_header_row

    return kwargs


def extract_output_dialect_kwargs(args):
    kwargs = {}

    if getattr(args, 'line_numbers', None):
        kwargs['line_numbers'] = True

    if getattr(args, 'out_asv', None):
        kwargs['delimiter'] = '\x1f'
    elif getattr(args, 'out_tabs', None):
        kwargs['delimiter'] = '\t'
    elif getattr(args, 'out_delimiter', None):
        kwargs['delimiter'] = args.out_delimiter

    if getattr(args, 'out_asv', None):
        kwargs['lineterminator'] = '\x1e'
    elif getattr(args, 'out_lineterminator', None):
        kwargs['lineterminator'] = args.out_lineterminator

    for arg in ('quotechar', 'quoting', 'doublequote', 'escapechar'):
        value = getattr(args, f'out_{arg}', None)
        if value is not None:
            kwargs[arg] = value

    return kwargs
