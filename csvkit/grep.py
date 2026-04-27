#!/usr/bin/env python

import re
from csvkit.exceptions import ColumnIdentifierError


class ExpressionError(Exception):
    pass


class TokenType:
    AND = 'AND'
    OR = 'OR'
    NOT = 'NOT'
    EQ = 'EQ'
    NE = 'NE'
    GT = 'GT'
    LT = 'LT'
    GE = 'GE'
    LE = 'LE'
    LIKE = 'LIKE'
    RLIKE = 'RLIKE'
    LPAREN = 'LPAREN'
    RPAREN = 'RPAREN'
    IDENTIFIER = 'IDENTIFIER'
    STRING = 'STRING'
    NUMBER = 'NUMBER'
    EOF = 'EOF'


class Token:
    def __init__(self, type_, value):
        self.type = type_
        self.value = value

    def __repr__(self):
        return f'Token({self.type}, {self.value!r})'


class Lexer:
    RESERVED = {
        'and': TokenType.AND,
        'or': TokenType.OR,
        'not': TokenType.NOT,
        'like': TokenType.LIKE,
        'rlike': TokenType.RLIKE,
    }

    def __init__(self, text):
        self.text = text
        self.pos = 0

    def error(self, message):
        raise ExpressionError(f'Lexical error at position {self.pos}: {message}')

    def peek(self):
        if self.pos >= len(self.text):
            return None
        return self.text[self.pos]

    def advance(self):
        char = self.peek()
        self.pos += 1
        return char

    def skip_whitespace(self):
        while self.peek() is not None and self.peek().isspace():
            self.advance()

    def read_identifier(self):
        start = self.pos
        while self.peek() is not None and (self.peek().isalnum() or self.peek() in '_-'):
            self.advance()
        value = self.text[start:self.pos]
        token_type = self.RESERVED.get(value.lower(), TokenType.IDENTIFIER)
        return Token(token_type, value)

    def read_string(self, quote_char):
        self.advance()
        start = self.pos
        while self.peek() is not None and self.peek() != quote_char:
            if self.peek() == '\\':
                self.advance()
            self.advance()
        if self.peek() is None:
            self.error('Unterminated string')
        value = self.text[start:self.pos]
        value = value.replace(f'\\{quote_char}', quote_char).replace('\\\\', '\\')
        self.advance()
        return Token(TokenType.STRING, value)

    def read_number(self):
        start = self.pos
        has_dot = False
        while self.peek() is not None and (self.peek().isdigit() or self.peek() == '.'):
            if self.peek() == '.':
                if has_dot:
                    break
                has_dot = True
            self.advance()
        value = self.text[start:self.pos]
        if has_dot:
            return Token(TokenType.NUMBER, float(value))
        return Token(TokenType.NUMBER, int(value))

    def get_next_token(self):
        while self.peek() is not None:
            self.skip_whitespace()
            if self.peek() is None:
                break

            char = self.peek()

            if char.isalpha() or char == '_':
                return self.read_identifier()

            if char in '"\'':
                quote_char = char
                self.advance()
                start = self.pos
                while self.peek() is not None and self.peek() != quote_char:
                    if self.peek() == '\\':
                        self.advance()
                    self.advance()
                if self.peek() is None:
                    self.error('Unterminated string')
                value = self.text[start:self.pos]
                value = value.replace(f'\\{quote_char}', quote_char).replace('\\\\', '\\')
                self.advance()
                if quote_char == '"':
                    return Token(TokenType.IDENTIFIER, value)
                return Token(TokenType.STRING, value)

            if char.isdigit():
                return self.read_number()

            if char == '(':
                self.advance()
                return Token(TokenType.LPAREN, '(')

            if char == ')':
                self.advance()
                return Token(TokenType.RPAREN, ')')

            if char == '=':
                self.advance()
                return Token(TokenType.EQ, '=')

            if char == '!':
                self.advance()
                if self.peek() == '=':
                    self.advance()
                    return Token(TokenType.NE, '!=')
                self.error(f"Unexpected character: '!' (did you mean '!='?)")

            if char == '<':
                self.advance()
                if self.peek() == '=':
                    self.advance()
                    return Token(TokenType.LE, '<=')
                if self.peek() == '>':
                    self.advance()
                    return Token(TokenType.NE, '<>')
                return Token(TokenType.LT, '<')

            if char == '>':
                self.advance()
                if self.peek() == '=':
                    self.advance()
                    return Token(TokenType.GE, '>=')
                return Token(TokenType.GT, '>')

            self.error(f"Unexpected character: {char!r}")

        return Token(TokenType.EOF, None)


class ASTNode:
    pass


class BinaryOp(ASTNode):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

    def __repr__(self):
        return f'BinaryOp({self.left}, {self.op}, {self.right})'


class UnaryOp(ASTNode):
    def __init__(self, op, operand):
        self.op = op
        self.operand = operand

    def __repr__(self):
        return f'UnaryOp({self.op}, {self.operand})'


class Literal(ASTNode):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f'Literal({self.value!r})'


class ColumnRef(ASTNode):
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f'ColumnRef({self.name!r})'


class Parser:
    def __init__(self, lexer):
        self.lexer = lexer
        self.current_token = self.lexer.get_next_token()

    def error(self, message):
        raise ExpressionError(f'Parse error: {message}')

    def eat(self, token_type):
        if self.current_token.type == token_type:
            self.current_token = self.lexer.get_next_token()
        else:
            self.error(f'Expected {token_type}, got {self.current_token.type}')

    def parse(self):
        node = self.or_expr()
        if self.current_token.type != TokenType.EOF:
            self.error(f'Unexpected token: {self.current_token}')
        return node

    def or_expr(self):
        node = self.and_expr()
        while self.current_token.type == TokenType.OR:
            op = self.current_token
            self.eat(TokenType.OR)
            node = BinaryOp(node, op, self.and_expr())
        return node

    def and_expr(self):
        node = self.not_expr()
        while self.current_token.type == TokenType.AND:
            op = self.current_token
            self.eat(TokenType.AND)
            node = BinaryOp(node, op, self.not_expr())
        return node

    def not_expr(self):
        if self.current_token.type == TokenType.NOT:
            op = self.current_token
            self.eat(TokenType.NOT)
            return UnaryOp(op, self.not_expr())
        return self.comparison()

    def comparison(self):
        node = self.atom()
        while self.current_token.type in (
            TokenType.EQ, TokenType.NE, TokenType.GT, TokenType.LT,
            TokenType.GE, TokenType.LE, TokenType.LIKE, TokenType.RLIKE
        ):
            op = self.current_token
            self.eat(self.current_token.type)
            node = BinaryOp(node, op, self.atom())
        return node

    def atom(self):
        token = self.current_token
        if token.type == TokenType.LPAREN:
            self.eat(TokenType.LPAREN)
            node = self.or_expr()
            self.eat(TokenType.RPAREN)
            return node
        elif token.type == TokenType.IDENTIFIER:
            self.eat(TokenType.IDENTIFIER)
            return ColumnRef(token.value)
        elif token.type == TokenType.STRING:
            self.eat(TokenType.STRING)
            return Literal(token.value)
        elif token.type == TokenType.NUMBER:
            self.eat(TokenType.NUMBER)
            return Literal(token.value)
        else:
            self.error(f'Unexpected token: {token}')


class Evaluator:
    def __init__(self, column_names):
        self.column_names = column_names
        self.column_index_map = {name.lower(): i for i, name in enumerate(column_names)} if column_names else {}

    def get_column_value(self, row, column_name):
        if not self.column_names:
            try:
                idx = int(column_name) - 1
                if idx < 0:
                    raise ExpressionError(f'Invalid column index: {column_name}')
                return row[idx] if idx < len(row) else ''
            except ValueError:
                raise ExpressionError(f'Column name {column_name!r} not found (no header row)')
        
        idx = self.column_index_map.get(column_name.lower())
        if idx is None:
            try:
                idx = int(column_name) - 1
                if idx < 0 or idx >= len(self.column_names):
                    raise ExpressionError(f'Column index out of range: {column_name}')
                return row[idx] if idx < len(row) else ''
            except ValueError:
                raise ExpressionError(f'Column {column_name!r} not found in columns: {self.column_names}')
        return row[idx] if idx < len(row) else ''

    def evaluate(self, node, row):
        if isinstance(node, Literal):
            return node.value
        elif isinstance(node, ColumnRef):
            return self.get_column_value(row, node.name)
        elif isinstance(node, UnaryOp):
            if node.op.type == TokenType.NOT:
                return not self._to_bool(self.evaluate(node.operand, row))
            raise ExpressionError(f'Unknown unary operator: {node.op}')
        elif isinstance(node, BinaryOp):
            return self._evaluate_binary(node, row)
        else:
            raise ExpressionError(f'Unknown node type: {type(node)}')

    def _to_bool(self, value):
        if isinstance(value, str):
            return value.lower() not in ('', '0', 'false', 'no', 'off')
        return bool(value)

    def _to_number(self, value):
        if isinstance(value, (int, float)):
            return value
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            return None

    def _evaluate_binary(self, node, row):
        left_val = self.evaluate(node.left, row)
        right_val = self.evaluate(node.right, row)
        op = node.op.type

        if op == TokenType.AND:
            return self._to_bool(left_val) and self._to_bool(right_val)
        elif op == TokenType.OR:
            return self._to_bool(left_val) or self._to_bool(right_val)
        elif op == TokenType.EQ:
            return self._compare_eq(left_val, right_val)
        elif op == TokenType.NE:
            return not self._compare_eq(left_val, right_val)
        elif op in (TokenType.GT, TokenType.LT, TokenType.GE, TokenType.LE):
            left_num = self._to_number(left_val)
            right_num = self._to_number(right_val)
            if left_num is not None and right_num is not None:
                if op == TokenType.GT:
                    return left_num > right_num
                elif op == TokenType.LT:
                    return left_num < right_num
                elif op == TokenType.GE:
                    return left_num >= right_num
                elif op == TokenType.LE:
                    return left_num <= right_num
            else:
                left_str = str(left_val)
                right_str = str(right_val)
                if op == TokenType.GT:
                    return left_str > right_str
                elif op == TokenType.LT:
                    return left_str < right_str
                elif op == TokenType.GE:
                    return left_str >= right_str
                elif op == TokenType.LE:
                    return left_str <= right_str
        elif op == TokenType.LIKE:
            pattern = self._like_to_regex(str(right_val))
            return re.match(pattern, str(left_val), re.IGNORECASE) is not None
        elif op == TokenType.RLIKE:
            try:
                return re.search(str(right_val), str(left_val)) is not None
            except re.error as e:
                raise ExpressionError(f'Invalid regular expression: {e}')
        
        raise ExpressionError(f'Unknown binary operator: {op}')

    def _compare_eq(self, left_val, right_val):
        if left_val == right_val:
            return True
        left_num = self._to_number(left_val)
        right_num = self._to_number(right_val)
        if left_num is not None and right_num is not None:
            return left_num == right_num
        return str(left_val) == str(right_val)

    def _like_to_regex(self, pattern):
        regex_parts = []
        i = 0
        while i < len(pattern):
            if pattern[i] == '%':
                regex_parts.append('.*')
                i += 1
            elif pattern[i] == '_':
                regex_parts.append('.')
                i += 1
            elif pattern[i] == '\\' and i + 1 < len(pattern):
                regex_parts.append(re.escape(pattern[i + 1]))
                i += 2
            else:
                regex_parts.append(re.escape(pattern[i]))
                i += 1
        return '^' + ''.join(regex_parts) + '$'


def parse_expression(expression_str, column_names=None):
    lexer = Lexer(expression_str)
    parser = Parser(lexer)
    ast = parser.parse()
    evaluator = Evaluator(column_names)
    return lambda row: evaluator.evaluate(ast, row)


class FilteringCSVReader:
    r"""
    Given any row iterator, only return rows which pass the filter.
    If 'header' is False, then all rows must pass the filter; by default, the first row will be passed
    through untested.

    The value of patterns may be either a sequence or a dictionary.  Items in the sequence and values in the
    dictionary may be strings, regular expressions, or functions.  For each row in the wrapped iterator,
    these values will be used as tests, and the row will only be yielded by the filter if all values pass
    their corresponding tests.  This behavior can be toggled so that all rows which pass any of the tests
    will be yielded by specifying "any_match=True" in the constructor.

    Empty values (the blank string or None) not be tested; the value in that position will not affect whether
    or not the filtering reader yields a prospective row.  To test for explicitly blank, use a regular
    expression such as "^$" or "^\s*$"

    If patterns is a dictionary, the keys can be integers identifying indices in the input rows, or, if 'header'
    is True (as it is by default), they can be strings matching column names in the first row of the reader.

    If patterns is a sequence, then it is assumed that they will be applied to the
    equivalently positioned values in the test rows.

    Alternatively, you can pass an 'expression' which is a string containing a SQL-like WHERE clause expression,
    or a callable that takes a row and returns True/False. The expression supports:
    - Logical operators: AND, OR, NOT
    - Comparison operators: =, !=, <>, >, <, >=, <=
    - Pattern matching: LIKE (with % and _ wildcards), RLIKE (regular expressions)
    - Parentheses for grouping
    - Column names can be identifiers or strings
    - String literals in single or double quotes

    By specifying 'inverse=True', only rows which do not match the patterns will be passed by the filter. The header,
    if there is one, will always be returned regardless of the value for 'inverse'.
    """
    returned_header = False
    column_names = None

    def __init__(self, reader, patterns=None, header=True, any_match=False, inverse=False, expression=None, column_names=None):
        super().__init__()

        self.reader = reader
        self.header = header

        if column_names is not None:
            self.column_names = column_names
        elif self.header:
            self.column_names = next(reader)
        else:
            self.column_names = None

        self.any_match = any_match
        self.inverse = inverse
        self.patterns = None
        self.expression_func = None

        if expression is not None:
            if callable(expression):
                self.expression_func = expression
            else:
                self.expression_func = parse_expression(expression, self.column_names)
        elif patterns is not None:
            self.patterns = standardize_patterns(self.column_names, patterns)
        else:
            raise ValueError('Either patterns or expression must be provided')

    def __iter__(self):
        return self

    def __next__(self):
        if self.header and self.column_names and not self.returned_header:
            self.returned_header = True
            return self.column_names

        while True:
            row = next(self.reader)

            if self.test_row(row):
                return row

        raise StopIteration()

    def test_row(self, row):
        if self.expression_func is not None:
            result = self.expression_func(row)
            return result if not self.inverse else not result

        for idx, test in self.patterns.items():
            try:
                value = row[idx]
            except IndexError:
                value = ''
            result = test(value)
            if self.any_match:
                if result:
                    return not self.inverse
            else:
                if not result:
                    return self.inverse

        if self.any_match:
            return self.inverse
        return not self.inverse


def standardize_patterns(column_names, patterns):
    """
    Given patterns in any of the permitted input forms, return a dict whose keys
    are column indices and whose values are functions which return a boolean value whether the value passes.
    If patterns is a dictionary and any of its keys are values in column_names, the returned dictionary will
    have those keys replaced with the integer position of that value in column_names
    """
    try:
        patterns = {k: pattern_as_function(v) for k, v in patterns.items() if v}
        if not column_names:
            return patterns
        p2 = {}
        for k in patterns:
            if k in column_names:
                idx = column_names.index(k)
                if idx in patterns:
                    raise ColumnIdentifierError("Column %s has index %i which already has a pattern." % (k, idx))
                p2[idx] = patterns[k]
            else:
                p2[k] = patterns[k]
        return p2
    except AttributeError:
        return {i: pattern_as_function(x) for i, x in enumerate(patterns)}


def pattern_as_function(obj):
    if callable(obj):
        return obj

    if hasattr(obj, 'match'):
        return regex_callable(obj)

    return lambda x: obj in x


class regex_callable:

    def __init__(self, pattern):
        self.pattern = pattern

    def __call__(self, arg):
        return self.pattern.search(arg)
