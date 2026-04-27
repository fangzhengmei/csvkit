import re
import unittest

from csvkit.exceptions import ColumnIdentifierError
from csvkit.grep import FilteringCSVReader, parse_expression, ExpressionError, Lexer, Parser, Evaluator


class TestGrep(unittest.TestCase):

    def setUp(self):
        self.tab1 = [
            ['id', 'name', 'i_work_here'],
            ['1', 'Chicago Reader', 'first'],
            ['2', 'Chicago Sun-Times', 'only'],
            ['3', 'Chicago Tribune', 'only'],
            ['1', 'Chicago Reader', 'second']]

        self.tab2 = [
            ['id', 'age', 'i_work_here'],
            ['1', 'first', '0'],
            ['4', 'only', '0'],
            ['1', 'second', '0'],
            ['2', 'only', '0', '0']]  # Note extra value in this column

    def test_pattern(self):
        fcr = FilteringCSVReader(iter(self.tab1), patterns=['1'])
        self.assertEqual(self.tab1[0], next(fcr))
        self.assertEqual(self.tab1[1], next(fcr))
        self.assertEqual(self.tab1[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_no_header(self):
        fcr = FilteringCSVReader(iter(self.tab1), patterns={2: 'only'}, header=False)
        self.assertEqual(self.tab1[2], next(fcr))
        self.assertEqual(self.tab1[3], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_regex(self):
        pattern = re.compile(".*(Reader|Tribune).*")
        fcr = FilteringCSVReader(iter(self.tab1), patterns={1: pattern})

        self.assertEqual(self.tab1[0], next(fcr))
        self.assertEqual(self.tab1[1], next(fcr))
        self.assertEqual(self.tab1[3], next(fcr))
        self.assertEqual(self.tab1[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_inverse(self):
        fcr = FilteringCSVReader(iter(self.tab2), patterns=['1'], inverse=True)
        self.assertEqual(self.tab2[0], next(fcr))
        self.assertEqual(self.tab2[2], next(fcr))
        self.assertEqual(self.tab2[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_column_names_in_patterns(self):
        fcr = FilteringCSVReader(iter(self.tab2), patterns={'age': 'only'})
        self.assertEqual(self.tab2[0], next(fcr))
        self.assertEqual(self.tab2[2], next(fcr))
        self.assertEqual(self.tab2[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_mixed_indices_and_column_names_in_patterns(self):
        fcr = FilteringCSVReader(iter(self.tab2), patterns={'age': 'only', 0: '2'})
        self.assertEqual(self.tab2[0], next(fcr))
        self.assertEqual(self.tab2[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_duplicate_column_ids_in_patterns(self):
        try:
            FilteringCSVReader(iter(self.tab2), patterns={'age': 'only', 1: 'second'})
            self.fail("Should be an exception.")
        except ColumnIdentifierError:
            pass

    def test_index_out_of_range(self):
        fcr = FilteringCSVReader(iter(self.tab2), patterns={3: '0'})
        self.assertEqual(self.tab2[0], next(fcr))
        self.assertEqual(self.tab2[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_any_match(self):
        fcr = FilteringCSVReader(iter(self.tab2), patterns={'age': 'only', 0: '2'}, any_match=True)
        self.assertEqual(self.tab2[0], next(fcr))
        self.assertEqual(self.tab2[2], next(fcr))
        self.assertEqual(self.tab2[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_any_match_and_inverse(self):
        fcr = FilteringCSVReader(iter(self.tab2), patterns={'age': 'only', 0: '2'}, any_match=True, inverse=True)
        self.assertEqual(self.tab2[0], next(fcr))
        self.assertEqual(self.tab2[1], next(fcr))
        self.assertEqual(self.tab2[3], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_multiline(self):
        table = [
            ['a', 'b'],
            ['1', 'foo\nbar'],
        ]
        fcr = FilteringCSVReader(iter(table), patterns={'b': re.compile('bar')})
        self.assertEqual(table[0], next(fcr))
        self.assertEqual(table[1], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass


class TestExpressionParsing(unittest.TestCase):

    def setUp(self):
        self.column_names = ['id', 'name', 'value', 'category']
        self.row1 = ['1', 'apple', '10', 'fruit']
        self.row2 = ['2', 'banana', '20', 'fruit']
        self.row3 = ['3', 'carrot', '30', 'vegetable']
        self.row4 = ['4', 'Apple Pie', '100', 'dessert']

    def test_simple_equality(self):
        expr = parse_expression("id = '1'", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertFalse(expr(self.row2))

    def test_equality_with_number(self):
        expr = parse_expression("id = 1", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertFalse(expr(self.row2))

    def test_inequality(self):
        expr = parse_expression("id != '1'", self.column_names)
        self.assertFalse(expr(self.row1))
        self.assertTrue(expr(self.row2))

    def test_inequality_alt(self):
        expr = parse_expression("id <> '1'", self.column_names)
        self.assertFalse(expr(self.row1))
        self.assertTrue(expr(self.row2))

    def test_logical_and(self):
        expr = parse_expression("category = 'fruit' AND value = '10'", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertFalse(expr(self.row2))
        self.assertFalse(expr(self.row3))

    def test_logical_or(self):
        expr = parse_expression("category = 'fruit' OR category = 'vegetable'", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertTrue(expr(self.row2))
        self.assertTrue(expr(self.row3))
        self.assertFalse(expr(self.row4))

    def test_logical_not(self):
        expr = parse_expression("NOT category = 'fruit'", self.column_names)
        self.assertFalse(expr(self.row1))
        self.assertFalse(expr(self.row2))
        self.assertTrue(expr(self.row3))
        self.assertTrue(expr(self.row4))

    def test_comparison_greater_than(self):
        expr = parse_expression("value > 15", self.column_names)
        self.assertFalse(expr(self.row1))
        self.assertTrue(expr(self.row2))
        self.assertTrue(expr(self.row3))

    def test_comparison_less_than(self):
        expr = parse_expression("value < 25", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertTrue(expr(self.row2))
        self.assertFalse(expr(self.row3))

    def test_comparison_greater_equal(self):
        expr = parse_expression("value >= 20", self.column_names)
        self.assertFalse(expr(self.row1))
        self.assertTrue(expr(self.row2))
        self.assertTrue(expr(self.row3))

    def test_comparison_less_equal(self):
        expr = parse_expression("value <= 20", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertTrue(expr(self.row2))
        self.assertFalse(expr(self.row3))

    def test_like_pattern(self):
        expr = parse_expression("name LIKE 'app%'", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertFalse(expr(self.row2))
        self.assertTrue(expr(self.row4))

    def test_like_single_char(self):
        expr = parse_expression("name LIKE 'c_rr_t'", self.column_names)
        self.assertFalse(expr(self.row1))
        self.assertTrue(expr(self.row3))

    def test_rlike_regex(self):
        expr = parse_expression("name RLIKE '^a.*e$'", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertFalse(expr(self.row2))

    def test_parentheses(self):
        expr = parse_expression("(category = 'fruit' AND value > 15) OR category = 'vegetable'", self.column_names)
        self.assertFalse(expr(self.row1))
        self.assertTrue(expr(self.row2))
        self.assertTrue(expr(self.row3))
        self.assertFalse(expr(self.row4))

    def test_case_insensitive_operators(self):
        expr = parse_expression("id = '1' AnD name = 'apple'", self.column_names)
        self.assertTrue(expr(self.row1))

    def test_column_names_with_spaces(self):
        column_names = ['First Name', 'Last Name', 'Age']
        row = ['John', 'Doe', '30']
        expr = parse_expression("\"First Name\" = 'John'", column_names)
        self.assertTrue(expr(row))

    def test_numeric_comparison(self):
        expr = parse_expression("value > 5 AND value < 25", self.column_names)
        self.assertTrue(expr(self.row1))
        self.assertTrue(expr(self.row2))
        self.assertFalse(expr(self.row3))

    def test_invalid_expression_error(self):
        with self.assertRaises(ExpressionError):
            parse_expression("invalid expression", self.column_names)

    def test_unknown_column(self):
        with self.assertRaises(ExpressionError):
            expr = parse_expression("unknown_col = 'test'", self.column_names)
            expr(self.row1)


class TestFilteringCSVReaderWithExpression(unittest.TestCase):

    def setUp(self):
        self.table = [
            ['id', 'name', 'value', 'category'],
            ['1', 'apple', '10', 'fruit'],
            ['2', 'banana', '20', 'fruit'],
            ['3', 'carrot', '30', 'vegetable'],
            ['4', 'date', '15', 'fruit'],
        ]

    def test_expression_filter(self):
        fcr = FilteringCSVReader(iter(self.table), expression="category = 'fruit'")
        self.assertEqual(self.table[0], next(fcr))
        self.assertEqual(self.table[1], next(fcr))
        self.assertEqual(self.table[2], next(fcr))
        self.assertEqual(self.table[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_expression_with_and(self):
        fcr = FilteringCSVReader(iter(self.table), expression="category = 'fruit' AND value > 15")
        self.assertEqual(self.table[0], next(fcr))
        self.assertEqual(self.table[2], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_expression_with_inverse(self):
        fcr = FilteringCSVReader(iter(self.table), expression="category = 'fruit'", inverse=True)
        self.assertEqual(self.table[0], next(fcr))
        self.assertEqual(self.table[3], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_expression_with_callable(self):
        filter_func = lambda row: row[3] == 'fruit'
        fcr = FilteringCSVReader(iter(self.table), expression=filter_func)
        self.assertEqual(self.table[0], next(fcr))
        self.assertEqual(self.table[1], next(fcr))
        self.assertEqual(self.table[2], next(fcr))
        self.assertEqual(self.table[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass

    def test_complex_expression(self):
        fcr = FilteringCSVReader(
            iter(self.table),
            expression="(category = 'fruit' AND value > 10) OR name LIKE 'c%'"
        )
        self.assertEqual(self.table[0], next(fcr))
        self.assertEqual(self.table[2], next(fcr))
        self.assertEqual(self.table[3], next(fcr))
        self.assertEqual(self.table[4], next(fcr))
        try:
            next(fcr)
            self.fail("Should be no more rows left.")
        except StopIteration:
            pass
