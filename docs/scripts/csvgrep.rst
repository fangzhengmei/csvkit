=======
csvgrep
=======

Description
===========

Filter tabular data to only those rows where certain columns contain a given value or match a regular expression:

.. code-block:: none

   usage: csvgrep [-h] [-d DELIMITER] [-t] [-q QUOTECHAR] [-u {0,1,2,3}] [-b]
                  [-p ESCAPECHAR] [-z FIELD_SIZE_LIMIT] [-e ENCODING] [-S] [-H]
                  [-K SKIP_LINES] [-v] [-l] [--zero] [-V] [-n] [-c COLUMNS]
                  [-m PATTERN] [-r REGEX] [-f MATCHFILE] [-i] [-a] [-w WHERE_EXPR]
                  [FILE]

   Search CSV files. Like the Unix "grep" command, but for tabular data.

   positional arguments:
     FILE                  The CSV file to operate on. If omitted, will accept
                           input as piped data via STDIN.

   optional arguments:
     -h, --help            show this help message and exit
     -n, --names           Display column names and indices from the input CSV
                           and exit.
     -c COLUMNS, --columns COLUMNS
                           A comma-separated list of column indices, names or
                           ranges to be searched, e.g. "1,id,3-5".
     -m PATTERN, --match PATTERN
                           A string to search for.
     -r REGEX, --regex REGEX
                           A regular expression to match.
     -f MATCHFILE, --file MATCHFILE
                           A path to a file. For each row, if any line in the
                           file (stripped of line separators) is an exact match
                           of the cell value, the row matches.
     -i, --invert-match    Select non-matching rows, instead of matching rows.
     -a, --any-match       Select rows in which any column matches, instead of
                           all columns.
     -w WHERE_EXPR, --where WHERE_EXPR
                           A SQL-like WHERE clause expression for complex filtering.
                           All operators are case-insensitive.

                           LOGICAL OPERATORS:
                             AND           - Logical AND
                             OR            - Logical OR
                             NOT           - Logical NOT

                           COMPARISON OPERATORS:
                             =             - Equal to (e.g., column = 'value')
                             !=, <>        - Not equal to
                             >, >=         - Greater than / Greater than or equal
                             <, <=         - Less than / Less than or equal

                           PATTERN MATCHING:
                             LIKE          - Pattern matching with wildcards
                                             % matches 0 or more characters
                                             _ matches exactly 1 character
                                             e.g., name LIKE 'A%'
                             RLIKE         - Regular expression matching
                                             e.g., name RLIKE '^A.*$'

                           SET MEMBERSHIP:
                             IN (...)      - Value in a list
                                             e.g., category IN ('a', 'b', 'c')
                             NOT IN (...)  - Value NOT in a list

                           NULL CHECKING:
                             IS NULL       - Value is empty or blank
                             IS NOT NULL   - Value is not empty or blank

                           GROUPING:
                             ( ... )       - Parentheses to group expressions

                           LITERALS:
                             'string'      - String values in single quotes
                             123, 123.45   - Numeric values
                             "column name" - Column names with spaces in double quotes

                           When using --where, the -c, -m, -r, -f, and -a options are ignored.

See also: :doc:`../common_arguments`.

NOTE: Even though '-m', '-r', and '-f' are listed as "optional" arguments, you must specify one of them (or use --where).

Examples
========

Search for the row relating to Illinois:

.. code-block:: bash

   csvgrep -c 1 -m ILLINOIS examples/realdata/FY09_EDU_Recipients_by_State.csv

Search for rows relating to states with names beginning with the letter "I":

.. code-block:: bash

   csvgrep -c 1 -r "^I" examples/realdata/FY09_EDU_Recipients_by_State.csv

Search for rows that do not contain an empty state cell:

.. code-block:: bash

   csvgrep -c 1 -r "^$" -i examples/realdata/FY09_EDU_Recipients_by_State.csv

Perform a case-insensitive search:

.. code-block:: bash

   csvgrep -c 1 -r "(?i)illinois" examples/realdata/FY09_EDU_Recipients_by_State.csv

Remove comment rows:

.. code-block:: bash

   printf "a,b\n1,2\n# a comment\n3,4" | csvgrep --invert-match -c1 -r '^#'

Get the indices of the columns that contain matching text (``\x1e`` is the `Record Separator (RS) character <https://en.wikipedia.org/wiki/C0_and_C1_control_codes#Field_separators>`_):

.. code-block::

   csvgrep -m 22 -a -c 1- examples/realdata/FY09_EDU_Recipients_by_State.csv | csvformat -M $'\x1e' | xargs -d $'\x1e' -n1 sh -c 'echo $0 | csvcut -n' | grep 22

.. note::

   This last example is not performant.

Complex filtering with --where
------------------------------

Use :code:`--where` for complex multi-column filtering with SQL-like syntax:

Filter rows where sepal_length is greater than 5 and species is "Iris-setosa":

.. code-block:: bash

   csvgrep -w "sepal_length > 5 AND species = 'Iris-setosa'" examples/iris.csv

Filter rows where species is either "Iris-setosa" or "Iris-virginica":

.. code-block:: bash

   csvgrep -w "species IN ('Iris-setosa', 'Iris-virginica')" examples/iris.csv

Filter rows where species is NOT "Iris-versicolor":

.. code-block:: bash

   csvgrep -w "species NOT IN ('Iris-versicolor')" examples/iris.csv

Filter rows with pattern matching (names starting with "A"):

.. code-block:: bash

   csvgrep -w "species LIKE 'Iris-s%'" examples/iris.csv

Filter rows with regular expressions:

.. code-block:: bash

   csvgrep -w "species RLIKE '^Iris-(setosa|virginica)$'" examples/iris.csv

Combine multiple conditions with grouping:

.. code-block:: bash

   csvgrep -w "(sepal_length > 5 AND sepal_width < 3.5) OR species = 'Iris-virginica'" examples/iris.csv

Filter rows with empty or blank values:

.. code-block:: bash

   csvgrep -w "name IS NULL" data.csv

Filter rows with non-empty values:

.. code-block:: bash

   csvgrep -w "name IS NOT NULL AND description IS NOT NULL" data.csv
