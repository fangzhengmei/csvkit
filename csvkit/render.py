#!/usr/bin/env python

import json

import agate

from csvkit.cli import default_float_decimal, default_str_decimal

BOM_UTF8 = '\ufeff'


def _strip_bom_from_string(s):
    if isinstance(s, str) and s.startswith(BOM_UTF8):
        return s[1:]
    return s


def _strip_bom_from_sequence(seq):
    if seq:
        return tuple(_strip_bom_from_string(s) for s in seq)
    return seq


def _strip_bom_from_dict_keys(d):
    if isinstance(d, dict):
        return {_strip_bom_from_string(k): v for k, v in d.items()}
    return d


def make_csv_writer(output_file, writer_kwargs=None, fieldnames=None):
    writer_kwargs = writer_kwargs or {}
    
    if fieldnames:
        fieldnames = _strip_bom_from_sequence(fieldnames)
        return agate.csv.DictWriter(output_file, fieldnames=fieldnames, **writer_kwargs)
    return agate.csv.writer(output_file, **writer_kwargs)


def write_csv_rows(output_file, rows, header=None, writer_kwargs=None):
    writer_kwargs = writer_kwargs or {}
    writer = agate.csv.writer(output_file, **writer_kwargs)
    
    if header:
        header = _strip_bom_from_sequence(header)
        writer.writerow(header)
    
    for row in rows:
        writer.writerow(row)


def write_csv_from_table(output_file, table, writer_kwargs=None):
    writer_kwargs = writer_kwargs or {}
    
    if table.column_names and any(isinstance(cn, str) and cn.startswith(BOM_UTF8) for cn in table.column_names):
        new_column_names = _strip_bom_from_sequence(table.column_names)
        table = table.rename(column_names=new_column_names)
    
    table.to_csv(output_file, **writer_kwargs)


def write_csv_dict_rows(output_file, rows, fieldnames, writer_kwargs=None, transform_row=None):
    writer_kwargs = writer_kwargs or {}
    
    has_bom_in_fieldnames = any(isinstance(fn, str) and fn.startswith(BOM_UTF8) for fn in fieldnames)
    fieldnames = _strip_bom_from_sequence(fieldnames)
    
    writer = agate.csv.DictWriter(output_file, fieldnames=fieldnames, **writer_kwargs)
    writer.writeheader()
    
    for row in rows:
        if has_bom_in_fieldnames:
            row = _strip_bom_from_dict_keys(row)
        if transform_row:
            row = transform_row(row)
        writer.writerow(row)


def dump_json(output_file, data, indent=None, use_float=False, newline=False, **kwargs):
    default_func = default_float_decimal if use_float else default_str_decimal
    json_kwargs = {'default': default_func, 'ensure_ascii': False}
    if indent is not None:
        json_kwargs['indent'] = indent
    json_kwargs.update(kwargs)
    
    json.dump(data, output_file, **json_kwargs)
    if newline:
        output_file.write("\n")


def print_markdown_table(table, output_file, max_rows=None, max_columns=None, max_column_width=None, **kwargs):
    if table.column_names and any(isinstance(cn, str) and cn.startswith(BOM_UTF8) for cn in table.column_names):
        new_column_names = _strip_bom_from_sequence(table.column_names)
        table = table.rename(column_names=new_column_names)
    
    table.print_table(
        output=output_file,
        max_rows=max_rows,
        max_columns=max_columns,
        max_column_width=max_column_width,
        **kwargs,
    )
