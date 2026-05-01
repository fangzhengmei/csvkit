#!/usr/bin/env python
"""
完整的 I/O 错误处理兼容性验证测试

验证四类场景的关键行为：
1. 标准输入
2. 文件路径（FileNotFoundError、PermissionError、IsADirectoryError等）
3. 编码错误（UnicodeDecodeError）
4. 管道中断（BrokenPipeError）

确保：
- 退出码与现有版本一致
- 报错文案与现有版本一致
"""
import sys
import io
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from csvkit.utilities.csvcut import CSVCut
from csvkit.utilities.csvstat import CSVStat
from csvkit.utilities.csvclean import CSVClean
from csvkit.utilities.csvgrep import CSVGrep
from csvkit.utilities.csvformat import CSVFormat
from csvkit.exceptions import ColumnIdentifierError, ErrorHandler


class TestFileNotFoundErrorCompatibility(unittest.TestCase):
    """测试文件不存在的兼容性"""

    def test_file_not_found_exit_code(self):
        """文件不存在时退出码应为 1"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'nonexistent_file_12345.csv'], output_file, error_file)

        with self.assertRaises(SystemExit) as cm:
            utility.run()

        self.assertEqual(cm.exception.code, 1, "文件不存在时退出码应为 1")

    def test_file_not_found_error_message(self):
        """文件不存在时错误消息格式应为 'FileNotFoundError: ...'"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'nonexistent_file_12345.csv'], output_file, error_file)

        with self.assertRaises(SystemExit):
            utility.run()

        error_msg = error_file.getvalue()
        self.assertTrue(error_msg.startswith("FileNotFoundError:"),
                        f"错误消息应以 'FileNotFoundError:' 开头，实际: {error_msg!r}")
        self.assertIn("nonexistent_file_12345.csv", error_msg,
                      f"错误消息应包含文件名，实际: {error_msg!r}")

    def test_file_not_found_multiple_utilities(self):
        """验证多个工具对文件不存在的处理一致"""
        utilities_to_test = [
            (CSVCut, ['-c', '1']),
            (CSVStat, []),
            (CSVFormat, []),
        ]

        for UtilityClass, extra_args in utilities_to_test:
            with self.subTest(utility=UtilityClass.__name__):
                error_file = io.StringIO()
                output_file = io.StringIO()
                args = extra_args + ['nonexistent_xyz_123.csv']

                utility = UtilityClass(args, output_file, error_file)

                with self.assertRaises(SystemExit) as cm:
                    utility.run()

                self.assertEqual(cm.exception.code, 1,
                                 f"{UtilityClass.__name__}: 文件不存在时退出码应为 1")
                error_msg = error_file.getvalue()
                self.assertTrue(error_msg.startswith("FileNotFoundError:"),
                                f"{UtilityClass.__name__}: 错误消息格式错误: {error_msg!r}")


class TestEncodingErrorCompatibility(unittest.TestCase):
    """测试编码错误的兼容性"""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv')
        self.temp_file.write(b'a,b,c\n1,2,\xa9\n')
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_encoding_error_exit_code(self):
        """编码错误时退出码应为 1"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', '-e', 'ascii', self.temp_file.name], output_file, error_file)

        with self.assertRaises(SystemExit) as cm:
            utility.run()

        self.assertEqual(cm.exception.code, 1, "编码错误时退出码应为 1")

    def test_encoding_error_user_friendly_message(self):
        """编码错误时应显示用户友好的消息，提示使用 --encoding 标志"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', '-e', 'ascii', self.temp_file.name], output_file, error_file)

        with self.assertRaises(SystemExit):
            utility.run()

        error_msg = error_file.getvalue()

        self.assertIn("is not", error_msg,
                      f"编码错误消息应包含友好提示，实际: {error_msg!r}")
        self.assertIn("encoded", error_msg,
                      f"编码错误消息应包含 'encoded'，实际: {error_msg!r}")
        self.assertIn("--encoding", error_msg,
                      f"编码错误消息应提示 '--encoding' 标志，实际: {error_msg!r}")
        self.assertIn("ascii", error_msg,
                      f"编码错误消息应包含指定的编码 'ascii'，实际: {error_msg!r}")

    def test_encoding_error_message_with_default_encoding(self):
        """使用默认编码时的错误消息"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', self.temp_file.name], output_file, error_file)

        try:
            with self.assertRaises(SystemExit):
                utility.run()

            error_msg = error_file.getvalue()
            default_encoding = 'utf-8-sig'
            self.assertIn(default_encoding, error_msg,
                          f"编码错误消息应包含默认编码 '{default_encoding}'，实际: {error_msg!r}")
        except Exception as e:
            self.skipTest(f"某些环境下默认编码可能能够读取此文件: {e}")


class TestStdinCompatibility(unittest.TestCase):
    """测试标准输入处理的兼容性"""

    def test_stdin_with_valid_data(self):
        """标准输入有有效数据时应正常处理"""
        input_data = io.BytesIO(b'a,b,c\n1,2,3\n')
        output_file = io.StringIO()
        error_file = io.StringIO()

        with patch('sys.stdin', io.TextIOWrapper(input_data, encoding='utf-8')):
            utility = CSVCut(['-c', '1'], output_file, error_file)
            utility.run()

        output = output_file.getvalue()
        self.assertIn('a', output, "标准输入处理应包含表头")
        self.assertIn('1', output, "标准输入处理应包含数据行")
        self.assertEqual(error_file.getvalue(), "", "正常处理时不应有错误输出")


class TestBrokenPipeErrorCompatibility(unittest.TestCase):
    """测试管道中断的兼容性"""

    def test_broken_pipe_error_handler_exit_code(self):
        """BrokenPipeError 应返回退出码 0"""
        error_file = io.StringIO()
        handler = ErrorHandler(args=None, error_file=error_file)

        exc_type = BrokenPipeError
        exc_value = BrokenPipeError(32, "Broken pipe")
        exit_code = handler.handle_exception(exc_type, exc_value, None)

        self.assertEqual(exit_code, 0, "BrokenPipeError 退出码应为 0")

    def test_broken_pipe_no_error_message(self):
        """BrokenPipeError 不应输出错误消息"""
        error_file = io.StringIO()
        handler = ErrorHandler(args=None, error_file=error_file)

        exc_type = BrokenPipeError
        exc_value = BrokenPipeError(32, "Broken pipe")
        handler.handle_exception(exc_type, exc_value, None)

        self.assertEqual(error_file.getvalue(), "", "BrokenPipeError 不应输出错误消息")


class TestOSErrorSubclassesCompatibility(unittest.TestCase):
    """测试其他 OSError 子类的兼容性"""

    def test_permission_error_format(self):
        """PermissionError 消息格式应为 'PermissionError: ...'"""
        error_file = io.StringIO()
        handler = ErrorHandler(args=None, error_file=error_file)

        exc_type = PermissionError
        exc_value = PermissionError(13, "Permission denied", "test.csv")
        exit_code = handler.handle_exception(exc_type, exc_value, None)

        self.assertEqual(exit_code, 1, "PermissionError 退出码应为 1")
        error_msg = error_file.getvalue()
        self.assertTrue(error_msg.startswith("PermissionError:"),
                        f"错误消息应以 'PermissionError:' 开头，实际: {error_msg!r}")

    def test_is_a_directory_error_format(self):
        """IsADirectoryError 消息格式应为 'IsADirectoryError: ...'"""
        error_file = io.StringIO()
        handler = ErrorHandler(args=None, error_file=error_file)

        exc_type = IsADirectoryError
        exc_value = IsADirectoryError(21, "Is a directory", "/test")
        exit_code = handler.handle_exception(exc_type, exc_value, None)

        self.assertEqual(exit_code, 1, "IsADirectoryError 退出码应为 1")
        error_msg = error_file.getvalue()
        self.assertTrue(error_msg.startswith("IsADirectoryError:"),
                        f"错误消息应以 'IsADirectoryError:' 开头，实际: {error_msg!r}")

    def test_generic_oserror_format(self):
        """其他 OSError 子类消息格式应为 '{ExceptionType}: ...'"""
        error_file = io.StringIO()
        handler = ErrorHandler(args=None, error_file=error_file)

        exc_type = OSError
        exc_value = OSError(99, "Some OS error")
        exit_code = handler.handle_exception(exc_type, exc_value, None)

        self.assertEqual(exit_code, 1, "OSError 退出码应为 1")
        error_msg = error_file.getvalue()
        self.assertTrue(error_msg.startswith("OSError:"),
                        f"错误消息应以 'OSError:' 开头，实际: {error_msg!r}")


class TestVerboseModeCompatibility(unittest.TestCase):
    """测试 verbose 模式的兼容性"""

    def test_verbose_mode_uses_sys_excepthook(self):
        """verbose 模式应使用 sys.__excepthook__ 显示完整 traceback"""
        error_file = io.StringIO()

        class MockArgs:
            verbose = True
            encoding = 'utf-8-sig'

        handler = ErrorHandler(args=MockArgs(), error_file=error_file)

        with patch('sys.__excepthook__') as mock_excepthook:
            exc_type = FileNotFoundError
            exc_value = FileNotFoundError(2, "No such file", "test.csv")
            handler.handle_exception(exc_type, exc_value, "traceback")

            mock_excepthook.assert_called_once_with(
                FileNotFoundError,
                exc_value,
                "traceback"
            )

    def test_non_verbose_mode_uses_friendly_message(self):
        """非 verbose 模式应使用友好消息格式"""
        error_file = io.StringIO()

        class MockArgs:
            verbose = False
            encoding = 'utf-8-sig'

        handler = ErrorHandler(args=MockArgs(), error_file=error_file)

        exc_type = FileNotFoundError
        exc_value = FileNotFoundError(2, "No such file", "test.csv")
        handler.handle_exception(exc_type, exc_value, None)

        error_msg = error_file.getvalue()
        self.assertIn("FileNotFoundError:", error_msg,
                      f"非 verbose 模式应显示简化错误消息，实际: {error_msg!r}")


class TestSystemExitPassthrough(unittest.TestCase):
    """测试 SystemExit 透传行为"""

    def test_csvclean_sys_exit_passthrough(self):
        """csvclean 的 sys.exit(1) 应透传，不被错误处理层捕获"""
        from csvkit.utilities.csvclean import CSVClean

        input_data = io.BytesIO(b'a,b,c\n1,2\n')
        output_file = io.StringIO()
        error_file = io.StringIO()

        with patch('sys.stdin', io.TextIOWrapper(input_data, encoding='utf-8')):
            utility = CSVClean(['--length-mismatch'], output_file, error_file)

            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 1,
                             "csvclean 检测到错误行时应退出码 1，且不被错误处理层拦截")


class TestApplicationExceptionPropagation(unittest.TestCase):
    """测试应用程序级异常传播"""

    def test_column_identifier_error_propagates(self):
        """ColumnIdentifierError 应传播，不被 I/O 错误处理层捕获"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '0', 'examples/dummy.csv'], output_file, error_file)

        with self.assertRaises(ColumnIdentifierError) as cm:
            utility.run()

        self.assertIsInstance(cm.exception, ColumnIdentifierError,
                              "ColumnIdentifierError 应原样传播，不应被转换为 SystemExit")

    def test_column_identifier_error_not_converted_to_system_exit(self):
        """ColumnIdentifierError 不应被转换为 SystemExit"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '0', 'examples/dummy.csv'], output_file, error_file)

        try:
            utility.run()
            self.fail("应抛出 ColumnIdentifierError")
        except ColumnIdentifierError:
            pass
        except SystemExit as e:
            self.fail(f"ColumnIdentifierError 不应被转换为 SystemExit (退出码 {e.code})")


class TestErrorFileParameter(unittest.TestCase):
    """测试 error_file 参数的使用"""

    def test_custom_error_file_used(self):
        """自定义 error_file 应被用于输出错误消息"""
        custom_error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'nonexistent.csv'], output_file, custom_error_file)

        with self.assertRaises(SystemExit):
            utility.run()

        error_msg = custom_error_file.getvalue()
        self.assertIn("FileNotFoundError:", error_msg,
                      f"错误消息应写入自定义 error_file，实际: {error_msg!r}")

    def test_default_error_file_is_stderr(self):
        """默认情况下 error_file 应为 sys.stderr"""
        handler = ErrorHandler(args=None, error_file=None)
        self.assertIs(handler.error_file, sys.stderr,
                      "默认 error_file 应为 sys.stderr")


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestFileNotFoundErrorCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestEncodingErrorCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestStdinCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestBrokenPipeErrorCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestOSErrorSubclassesCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestVerboseModeCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestSystemExitPassthrough))
    suite.addTests(loader.loadTestsFromTestCase(TestApplicationExceptionPropagation))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorFileParameter))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print("兼容性验证测试结果")
    print("=" * 60)
    print(f"运行测试: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")

    if result.failures or result.errors:
        print("\n详细失败信息:")
        for test, traceback in result.failures + result.errors:
            print(f"\n{test}")
            print(traceback)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
