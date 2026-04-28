#!/usr/bin/env python

import agate
from agate.data_types.base import DEFAULT_NULL_VALUES


def get_type_tester(
    blanks=False,
    null_values=None,
    no_inference=False,
    locale='en_US',
    no_leading_zeroes=None,
    date_format=None,
    datetime_format=None,
    quote_nonnumeric=False,
):
    """
    Create an agate.TypeTester for CSV column type inference.

    This is a centralized helper for consistent type inference across all csvkit utilities.

    :param blanks: If True, do not convert "", "na", "n/a", "none", "null", "." to NULL.
    :param null_values: Additional values to treat as NULL.
    :param no_inference: If True, disable type inference and treat all columns as Text.
    :param locale: Locale for number parsing (e.g., 'en_US', 'de_DE').
    :param no_leading_zeroes: If True, do not convert values with leading zeros to numbers.
    :param date_format: Strptime format string for date parsing.
    :param datetime_format: Strptime format string for datetime parsing.
    :param quote_nonnumeric: If True, use simplified type inference (Number, Text only)
                              for QUOTE_NONNUMERIC output mode (used by csvformat).
    :return: An agate.TypeTester instance.
    """
    if blanks:
        type_kwargs = {'null_values': []}
    else:
        type_kwargs = {'null_values': list(DEFAULT_NULL_VALUES)}

    if null_values:
        for nv in null_values:
            type_kwargs['null_values'].append(nv)

    text_type = agate.Text(**type_kwargs)

    if no_inference:
        return agate.TypeTester(types=[text_type])

    number_type = agate.Number(
        locale=locale,
        no_leading_zeroes=no_leading_zeroes,
        **type_kwargs
    )

    if quote_nonnumeric:
        return agate.TypeTester(types=[number_type, text_type])

    types = [
        agate.Boolean(**type_kwargs),
        agate.TimeDelta(**type_kwargs),
        agate.Date(date_format=date_format, **type_kwargs),
        agate.DateTime(datetime_format=datetime_format, **type_kwargs),
        text_type,
    ]

    if datetime_format:
        types.insert(-1, number_type)
    elif date_format:
        types.insert(-2, number_type)
    else:
        types.insert(1, number_type)

    return agate.TypeTester(types=types)
