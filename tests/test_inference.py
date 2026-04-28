import unittest

import agate

from csvkit.inference import get_type_tester


class TestGetTypeTester(unittest.TestCase):
    def test_default_types_order(self):
        t = get_type_tester()
        types = [type(x).__name__ for x in t._possible_types]
        self.assertEqual(types, ['Boolean', 'Number', 'TimeDelta', 'Date', 'DateTime', 'Text'])

    def test_no_inference_early_return(self):
        t = get_type_tester(no_inference=True)
        types = [type(x).__name__ for x in t._possible_types]
        self.assertEqual(types, ['Text'])

    def test_quote_nonnumeric_path(self):
        t = get_type_tester(quote_nonnumeric=True)
        types = [type(x).__name__ for x in t._possible_types]
        self.assertEqual(types, ['Number', 'Text'])

    def test_blanks_false_null_values(self):
        t = get_type_tester(blanks=False)
        text_type = t._possible_types[-1]
        self.assertIsInstance(text_type, agate.Text)
        self.assertEqual(
            text_type.null_values,
            ['', 'na', 'n/a', 'none', 'null', '.']
        )

    def test_blanks_true_null_values(self):
        t = get_type_tester(blanks=True)
        text_type = t._possible_types[-1]
        self.assertIsInstance(text_type, agate.Text)
        self.assertEqual(text_type.null_values, [])

    def test_extra_null_values(self):
        t = get_type_tester(null_values=['na', 'missing'])
        text_type = t._possible_types[-1]
        self.assertIn('na', text_type.null_values)
        self.assertIn('missing', text_type.null_values)

    def test_blanks_and_extra_null_values_combination(self):
        t = get_type_tester(blanks=True, null_values=['na', 'missing'])
        text_type = t._possible_types[-1]
        self.assertEqual(text_type.null_values, ['na', 'missing'])

    def test_default_number_type_insert_position(self):
        t = get_type_tester()
        types = [type(x).__name__ for x in t._possible_types]
        self.assertEqual(types[1], 'Number')

    def test_date_format_number_type_insert_position(self):
        t = get_type_tester(date_format='%d/%m/%Y')
        types = [type(x).__name__ for x in t._possible_types]
        self.assertEqual(
            types,
            ['Boolean', 'TimeDelta', 'Date', 'Number', 'DateTime', 'Text']
        )

    def test_datetime_format_number_type_insert_position(self):
        t = get_type_tester(datetime_format='%d/%m/%Y %H:%M')
        types = [type(x).__name__ for x in t._possible_types]
        self.assertEqual(
            types,
            ['Boolean', 'TimeDelta', 'Date', 'DateTime', 'Number', 'Text']
        )

    def test_no_leading_zeroes_none(self):
        t = get_type_tester(no_leading_zeroes=None)
        for typ in t._possible_types:
            if isinstance(typ, agate.Number):
                self.assertIsNone(typ.no_leading_zeroes)
                break
        else:
            self.fail('Number type not found')

    def test_no_leading_zeroes_true(self):
        t = get_type_tester(no_leading_zeroes=True)
        for typ in t._possible_types:
            if isinstance(typ, agate.Number):
                self.assertTrue(typ.no_leading_zeroes)
                break
        else:
            self.fail('Number type not found')

    def test_locale_parameter(self):
        t = get_type_tester(locale='de_DE')
        for typ in t._possible_types:
            if isinstance(typ, agate.Number):
                self.assertIsNotNone(typ.locale)
                self.assertEqual(str(typ.locale), 'de_DE')
                break
        else:
            self.fail('Number type not found')

    def test_date_format_parameter(self):
        t = get_type_tester(date_format='%d/%m/%Y')
        for typ in t._possible_types:
            if isinstance(typ, agate.Date):
                self.assertEqual(typ.date_format, '%d/%m/%Y')
                break
        else:
            self.fail('Date type not found')

    def test_datetime_format_parameter(self):
        t = get_type_tester(datetime_format='%d/%m/%Y %H:%M')
        for typ in t._possible_types:
            if isinstance(typ, agate.DateTime):
                self.assertEqual(typ.datetime_format, '%d/%m/%Y %H:%M')
                break
        else:
            self.fail('DateTime type not found')

    def test_all_types_have_null_values(self):
        t = get_type_tester()
        for typ in t._possible_types:
            self.assertTrue(hasattr(typ, 'null_values'))

    def test_quote_nonnumeric_with_other_parameters(self):
        t = get_type_tester(
            quote_nonnumeric=True,
            locale='de_DE',
            no_leading_zeroes=True,
            null_values=['na']
        )
        types = [type(x).__name__ for x in t._possible_types]
        self.assertEqual(types, ['Number', 'Text'])
        for typ in t._possible_types:
            if isinstance(typ, agate.Number):
                self.assertIsNotNone(typ.locale)
                self.assertEqual(str(typ.locale), 'de_DE')
                self.assertTrue(typ.no_leading_zeroes)
            if isinstance(typ, agate.Text):
                self.assertIn('na', typ.null_values)

    def test_no_inference_with_other_parameters(self):
        t = get_type_tester(
            no_inference=True,
            blanks=True,
            null_values=['na'],
            date_format='%d/%m/%Y'
        )
        types = [type(x).__name__ for x in t._possible_types]
        self.assertEqual(types, ['Text'])
        text_type = t._possible_types[0]
        self.assertEqual(text_type.null_values, ['na'])


if __name__ == '__main__':
    unittest.main()
