#!/usr/bin/env python
import argparse
import unittest
from unittest.mock import MagicMock

from csvkit.dialect import (
    QUOTING_CHOICES,
    add_input_dialect_arguments,
    add_output_dialect_arguments,
    extract_input_dialect_kwargs,
    extract_output_dialect_kwargs,
)


class TestDialect(unittest.TestCase):

    def test_quoting_choices(self):
        self.assertIsInstance(QUOTING_CHOICES, list)
        self.assertTrue(len(QUOTING_CHOICES) > 0)


class TestAddInputDialectArguments(unittest.TestCase):

    def test_add_all_arguments(self):
        parser = argparse.ArgumentParser()
        add_input_dialect_arguments(parser, override_flags='')
        
        actions = {action.dest for action in parser._actions}
        self.assertIn('delimiter', actions)
        self.assertIn('tabs', actions)
        self.assertIn('quotechar', actions)
        self.assertIn('quoting', actions)
        self.assertIn('doublequote', actions)
        self.assertIn('escapechar', actions)
        self.assertIn('field_size_limit', actions)
        self.assertIn('skipinitialspace', actions)

    def test_override_flags_exclude_arguments(self):
        parser = argparse.ArgumentParser()
        add_input_dialect_arguments(parser, override_flags='dtq')
        
        actions = {action.dest for action in parser._actions}
        self.assertNotIn('delimiter', actions)
        self.assertNotIn('tabs', actions)
        self.assertNotIn('quotechar', actions)
        self.assertIn('quoting', actions)


class TestAddOutputDialectArguments(unittest.TestCase):

    def test_add_all_arguments(self):
        parser = argparse.ArgumentParser()
        add_output_dialect_arguments(parser)
        
        actions = {action.dest for action in parser._actions}
        self.assertIn('out_delimiter', actions)
        self.assertIn('out_tabs', actions)
        self.assertIn('out_asv', actions)
        self.assertIn('out_quotechar', actions)
        self.assertIn('out_quoting', actions)
        self.assertIn('out_doublequote', actions)
        self.assertIn('out_escapechar', actions)
        self.assertIn('out_lineterminator', actions)


class TestExtractInputDialectKwargs(unittest.TestCase):

    def _create_args(self, **kwargs):
        args = MagicMock()
        args.tabs = kwargs.get('tabs', False)
        args.delimiter = kwargs.get('delimiter', None)
        args.quotechar = kwargs.get('quotechar', None)
        args.quoting = kwargs.get('quoting', None)
        args.doublequote = kwargs.get('doublequote', None)
        args.escapechar = kwargs.get('escapechar', None)
        args.skipinitialspace = kwargs.get('skipinitialspace', None)
        args.field_size_limit = kwargs.get('field_size_limit', None)
        args.no_header_row = kwargs.get('no_header_row', None)
        return args

    def test_empty_args_returns_empty_kwargs(self):
        args = self._create_args()
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs, {})

    def test_tabs_priority_over_delimiter(self):
        args = self._create_args(tabs=True, delimiter=',')
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], '\t')

    def test_delimiter_when_tabs_false(self):
        args = self._create_args(tabs=False, delimiter=';')
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], ';')

    def test_quotechar(self):
        args = self._create_args(quotechar="'")
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['quotechar'], "'")

    def test_quoting(self):
        args = self._create_args(quoting=1)
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['quoting'], 1)

    def test_doublequote(self):
        args = self._create_args(doublequote=False)
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['doublequote'], False)

    def test_escapechar(self):
        args = self._create_args(escapechar='\\')
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['escapechar'], '\\')

    def test_skipinitialspace(self):
        args = self._create_args(skipinitialspace=True)
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['skipinitialspace'], True)

    def test_no_header_row(self):
        args = self._create_args(no_header_row=True)
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['header'], False)

    def test_no_header_row_false(self):
        args = self._create_args(no_header_row=False)
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertNotIn('header', kwargs)

    def test_full_input_dialect(self):
        args = self._create_args(
            tabs=False,
            delimiter='|',
            quotechar="'",
            quoting=2,
            doublequote=False,
            escapechar='\\',
            skipinitialspace=True,
            no_header_row=True,
            field_size_limit=None,
        )
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], '|')
        self.assertEqual(kwargs['quotechar'], "'")
        self.assertEqual(kwargs['quoting'], 2)
        self.assertEqual(kwargs['doublequote'], False)
        self.assertEqual(kwargs['escapechar'], '\\')
        self.assertEqual(kwargs['skipinitialspace'], True)
        self.assertEqual(kwargs['header'], False)


class TestExtractOutputDialectKwargs(unittest.TestCase):

    def _create_args(self, **kwargs):
        args = MagicMock()
        args.line_numbers = kwargs.get('line_numbers', None)
        args.out_asv = kwargs.get('out_asv', False)
        args.out_tabs = kwargs.get('out_tabs', False)
        args.out_delimiter = kwargs.get('out_delimiter', None)
        args.out_lineterminator = kwargs.get('out_lineterminator', None)
        args.out_quotechar = kwargs.get('out_quotechar', None)
        args.out_quoting = kwargs.get('out_quoting', None)
        args.out_doublequote = kwargs.get('out_doublequote', None)
        args.out_escapechar = kwargs.get('out_escapechar', None)
        return args

    def test_empty_args_returns_empty_kwargs(self):
        args = self._create_args()
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs, {})

    def test_line_numbers(self):
        args = self._create_args(line_numbers=True)
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['line_numbers'], True)

    def test_out_asv_priority_over_all(self):
        args = self._create_args(
            out_asv=True,
            out_tabs=True,
            out_delimiter=',',
            out_lineterminator='\r\n',
        )
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], '\x1f')
        self.assertEqual(kwargs['lineterminator'], '\x1e')

    def test_out_tabs_priority_over_delimiter(self):
        args = self._create_args(
            out_asv=False,
            out_tabs=True,
            out_delimiter=',',
            out_lineterminator=None,
        )
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], '\t')
        self.assertNotIn('lineterminator', kwargs)

    def test_out_delimiter(self):
        args = self._create_args(
            out_asv=False,
            out_tabs=False,
            out_delimiter=';',
        )
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], ';')

    def test_out_lineterminator(self):
        args = self._create_args(
            out_asv=False,
            out_lineterminator='\r\n',
        )
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['lineterminator'], '\r\n')

    def test_out_quotechar(self):
        args = self._create_args(out_quotechar="'")
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['quotechar'], "'")

    def test_out_quoting(self):
        args = self._create_args(out_quoting=1)
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['quoting'], 1)

    def test_out_doublequote(self):
        args = self._create_args(out_doublequote=False)
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['doublequote'], False)

    def test_out_escapechar(self):
        args = self._create_args(out_escapechar='\\')
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['escapechar'], '\\')

    def test_full_output_dialect(self):
        args = self._create_args(
            line_numbers=True,
            out_asv=False,
            out_tabs=False,
            out_delimiter='|',
            out_lineterminator='XYZ',
            out_quotechar="'",
            out_quoting=2,
            out_doublequote=False,
            out_escapechar='\\',
        )
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['line_numbers'], True)
        self.assertEqual(kwargs['delimiter'], '|')
        self.assertEqual(kwargs['lineterminator'], 'XYZ')
        self.assertEqual(kwargs['quotechar'], "'")
        self.assertEqual(kwargs['quoting'], 2)
        self.assertEqual(kwargs['doublequote'], False)
        self.assertEqual(kwargs['escapechar'], '\\')


class TestArgumentPriorityComprehensive(unittest.TestCase):

    def test_input_priority_tabs_over_delimiter(self):
        args = MagicMock()
        args.tabs = True
        args.delimiter = ';'
        args.quotechar = None
        args.quoting = None
        args.doublequote = None
        args.escapechar = None
        args.skipinitialspace = None
        args.field_size_limit = None
        args.no_header_row = None
        
        kwargs = extract_input_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], '\t')

    def test_output_priority_asv_over_tabs(self):
        args = MagicMock()
        args.out_asv = True
        args.out_tabs = True
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], '\x1f')
        self.assertEqual(kwargs['lineterminator'], '\x1e')

    def test_output_priority_tabs_over_delimiter(self):
        args = MagicMock()
        args.out_asv = False
        args.out_tabs = True
        args.out_delimiter = ';'
        
        kwargs = extract_output_dialect_kwargs(args)
        self.assertEqual(kwargs['delimiter'], '\t')


if __name__ == '__main__':
    unittest.main()
