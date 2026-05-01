#!/usr/bin/env python
import sys


class CustomException(Exception):
    """
    A base exception that handles pretty-printing errors for command-line tools.
    """

    def __init__(self, msg):
        self.msg = msg

    def __unicode__(self):
        return self.msg

    def __str__(self):
        return self.msg


class ColumnIdentifierError(CustomException):
    """
    Exception raised when the user supplies an invalid column identifier.
    """
    pass


class InvalidValueForTypeException(CustomException):
    """
    Exception raised when a value can not be normalized to a specified type.
    """

    def __init__(self, index, value, normal_type):
        self.index = index
        self.value = value
        self.normal_type = normal_type
        msg = 'Unable to convert "%s" to type %s (at index %i)' % (value, normal_type, index)
        super().__init__(msg)


class RequiredHeaderError(CustomException):
    """
    Exception raised when an operation requires a CSV file to have a header row.
    """
    pass


class ErrorHandler:
    """
    A unified error handler for I/O and related exceptions across all csvkit utilities.

    This handler provides consistent behavior for:
    - File not found errors (FileNotFoundError)
    - Permission errors (PermissionError)
    - Encoding errors (UnicodeDecodeError)
    - Pipe errors (BrokenPipeError)
    - Other I/O errors (OSError)

    The behavior is designed to be fully compatible with the original csvkit error handling:
    - Encoding errors show a user-friendly message suggesting --encoding flag
    - Other exceptions show the exception type name and message
    - Exit codes are preserved (1 for most errors, 2 for argparse errors)
    """

    EXIT_CODE_ERROR = 1
    EXIT_CODE_PIPE = 0

    def __init__(self, args=None, error_file=None):
        """
        Initialize the error handler.

        :param args: Parsed arguments from argparse (for access to encoding, verbose flags)
        :param error_file: File-like object to write error messages to (defaults to sys.stderr)
        """
        self.args = args
        self.error_file = error_file if error_file is not None else sys.stderr

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """
        Handle an exception and return the appropriate exit code.

        :return: Exit code to use
        """
        if self.args and getattr(self.args, 'verbose', False):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return self.EXIT_CODE_ERROR

        if exc_type == UnicodeDecodeError:
            encoding = getattr(self.args, 'encoding', 'utf-8-sig') if self.args else 'utf-8-sig'
            self.error_file.write(
                'Your file is not "%s" encoded. Please specify the correct encoding with the --encoding flag.'
                ' Use the -v flag to see the complete error.\n' % encoding
            )
        elif exc_type == BrokenPipeError:
            return self.EXIT_CODE_PIPE
        elif exc_type == FileNotFoundError:
            self.error_file.write(f'{exc_type.__name__}: {str(exc_value)}\n')
        elif exc_type == PermissionError:
            self.error_file.write(f'{exc_type.__name__}: {str(exc_value)}\n')
        elif exc_type == IsADirectoryError:
            self.error_file.write(f'{exc_type.__name__}: {str(exc_value)}\n')
        elif issubclass(exc_type, OSError):
            self.error_file.write(f'{exc_type.__name__}: {str(exc_value)}\n')
        else:
            self.error_file.write(f'{exc_type.__name__}: {str(exc_value)}\n')

        return self.EXIT_CODE_ERROR

    @staticmethod
    def is_io_exception(exc_type):
        """
        Check if an exception type is an I/O related exception that should be handled.

        :param exc_type: Exception type to check
        :return: True if it's an I/O related exception
        """
        io_exceptions = (
            UnicodeDecodeError,
            BrokenPipeError,
            FileNotFoundError,
            PermissionError,
            IsADirectoryError,
            OSError,
        )
        return issubclass(exc_type, io_exceptions)
