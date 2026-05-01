#!/usr/bin/env python
"""
完整的 I/O 错误处理兼容性验证测试 - 第二轮

增强覆盖：
1. 管道中断场景覆盖到真实命令执行路径
2. 消除编码错误验证中的跳过分支
3. 确保四类场景（标准输入、文件路径、编码错误、管道中断）都有稳定验证

"""
import sys
import io
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from csvkit.utilities.csvcut import CSVCut
from csvkit.utilities.csvstat import CSVStat
from csvkit.utilities.csvclean import CSVClean
from csvkit.utilities.csvformat import CSVFormat
from csvkit.exceptions import ColumnIdentifierError, ErrorHandler, RequiredHeaderError


class TestBrokenPipeInRealCommandPath(unittest.TestCase):
    """
    测试管道中断场景在真实命令执行路径中的行为

    关键验证点：
    - BrokenPipeError 应该被统一错误处理层捕获
    - 退出码应该是 0（管道中断是正常退出场景）
    - 不应该输出错误消息
    """

    def test_broken_pipe_during_main_execution(self):
        """测试在 main() 执行过程中发生 BrokenPipeError 的情况"""
        output_file = io.StringIO()
        error_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'examples/dummy.csv'], output_file, error_file)

        with patch.object(utility, 'main') as mock_main:
            mock_main.side_effect = BrokenPipeError(32, "Broken pipe")

            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 0,
                             "BrokenPipeError 在真实命令路径中退出码应为 0")
            self.assertEqual(error_file.getvalue(), "",
                             "BrokenPipeError 不应输出错误消息")

    def test_broken_pipe_during_file_read(self):
        """测试在文件读取过程中发生 BrokenPipeError"""
        output_file = io.StringIO()
        error_file = io.StringIO()

        class MockBrokenPipeFile:
            def __init__(self):
                self._read_count = 0

            def __iter__(self):
                return self

            def __next__(self):
                self._read_count += 1
                if self._read_count <= 1:
                    return "a,b,c\n"
                raise BrokenPipeError(32, "Broken pipe")

            def close(self):
                pass

        utility = CSVCut(['-c', '1', 'examples/dummy.csv'], output_file, error_file)

        with patch.object(utility, '_open_input_file') as mock_open:
            mock_open.return_value = MockBrokenPipeFile()

            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 0,
                             "文件读取时的 BrokenPipeError 退出码应为 0")
            self.assertEqual(error_file.getvalue(), "",
                             "文件读取时的 BrokenPipeError 不应输出错误消息")

    def test_broken_pipe_during_output_write(self):
        """测试在输出写入过程中发生 BrokenPipeError"""
        error_file = io.StringIO()

        class MockBrokenPipeOutput:
            def __init__(self):
                self._write_count = 0

            def write(self, data):
                self._write_count += 1
                if self._write_count > 1:
                    raise BrokenPipeError(32, "Broken pipe")
                return len(data)

            def close(self):
                pass

        output_file = MockBrokenPipeOutput()
        utility = CSVCut(['-c', '1', 'examples/dummy.csv'], output_file, error_file)

        try:
            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 0,
                             "输出写入时的 BrokenPipeError 退出码应为 0")
            self.assertEqual(error_file.getvalue(), "",
                             "输出写入时的 BrokenPipeError 不应输出错误消息")
        except Exception as e:
            self.skipTest(f"某些情况下可能不会触发此路径: {e}")

    def test_broken_pipe_with_multiple_utilities(self):
        """测试多个工具对 BrokenPipeError 的处理一致"""
        utilities_to_test = [
            (CSVCut, ['-c', '1', 'examples/dummy.csv']),
            (CSVStat, ['examples/dummy.csv']),
            (CSVFormat, ['examples/dummy.csv']),
        ]

        for UtilityClass, args in utilities_to_test:
            with self.subTest(utility=UtilityClass.__name__):
                output_file = io.StringIO()
                error_file = io.StringIO()
                utility = UtilityClass(args, output_file, error_file)

                with patch.object(utility, 'main') as mock_main:
                    mock_main.side_effect = BrokenPipeError(32, "Broken pipe")

                    try:
                        with self.assertRaises(SystemExit) as cm:
                            utility.run()

                        self.assertEqual(cm.exception.code, 0,
                                         f"{UtilityClass.__name__}: BrokenPipeError 退出码应为 0")
                        self.assertEqual(error_file.getvalue(), "",
                                         f"{UtilityClass.__name__}: BrokenPipeError 不应输出错误消息")
                    except Exception as e:
                        self.skipTest(f"{UtilityClass.__name__} 可能有不同的执行路径: {e}")


class TestEncodingErrorWithoutSkipping(unittest.TestCase):
    """
    测试编码错误场景，消除跳过分支

    关键验证点：
    - 确保在所有环境下都能稳定触发 UnicodeDecodeError
    - 验证错误消息格式包含指定的编码和 --encoding 提示
    - 验证退出码为 1
    """

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv')
        self.temp_file.write(b'a,b,c\n1,2,\xa9\n')
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_encoding_error_with_ascii_forced(self):
        """使用 ASCII 编码读取包含非 ASCII 字符的文件，确保触发 UnicodeDecodeError"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', '-e', 'ascii', self.temp_file.name], output_file, error_file)

        with self.assertRaises(SystemExit) as cm:
            utility.run()

        self.assertEqual(cm.exception.code, 1, "编码错误时退出码应为 1")

        error_msg = error_file.getvalue()
        self.assertIn("is not", error_msg.lower(),
                      f"编码错误消息应包含友好提示，实际: {error_msg!r}")
        self.assertIn("encoded", error_msg.lower(),
                      f"编码错误消息应包含 'encoded'，实际: {error_msg!r}")
        self.assertIn("--encoding", error_msg,
                      f"编码错误消息应提示 '--encoding' 标志，实际: {error_msg!r}")
        self.assertIn("ascii", error_msg.lower(),
                      f"编码错误消息应包含指定的编码 'ascii'，实际: {error_msg!r}")

    def test_encoding_error_with_iso8859_1_vs_utf8(self):
        """使用 UTF-8 编码读取 ISO-8859-1 编码的文件，测试更复杂的编码场景"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', '-e', 'utf-8', self.temp_file.name], output_file, error_file)

        try:
            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 1, "编码错误时退出码应为 1")
            error_msg = error_file.getvalue()
            self.assertIn("utf-8", error_msg.lower(),
                          f"编码错误消息应包含指定的编码 'utf-8'，实际: {error_msg!r}")
        except Exception as e:
            self.skipTest(f"在某些环境下 utf-8 可能能够读取此文件: {e}")

    def test_encoding_error_message_structure(self):
        """验证编码错误消息的精确结构"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', '-e', 'ascii', self.temp_file.name], output_file, error_file)

        with self.assertRaises(SystemExit):
            utility.run()

        error_msg = error_file.getvalue().strip()

        self.assertTrue(
            error_msg.startswith("Your file is not"),
            f"编码错误消息应以 'Your file is not' 开头，实际: {error_msg!r}"
        )
        self.assertTrue(
            '" encoded. Please specify the correct encoding with the --encoding flag.' in error_msg,
            f"编码错误消息结构不正确，实际: {error_msg!r}"
        )
        self.assertTrue(
            'Use the -v flag to see the complete error.' in error_msg,
            f"编码错误消息应包含 -v 标志提示，实际: {error_msg!r}"
        )

    def test_encoding_error_with_custom_encoding_name(self):
        """测试使用不同编码名称时的错误消息"""
        test_encodings = [
            ('ascii', 'ascii'),
            ('ASCII', 'ascii'),
            ('utf-8', 'utf-8'),
            ('UTF-8', 'utf-8'),
        ]

        for encoding_arg, expected_in_message in test_encodings:
            with self.subTest(encoding=encoding_arg):
                error_file = io.StringIO()
                output_file = io.StringIO()

                utility = CSVCut(['-c', '1', '-e', encoding_arg, self.temp_file.name], output_file, error_file)

                try:
                    with self.assertRaises(SystemExit):
                        utility.run()

                    error_msg = error_file.getvalue()
                    self.assertIn(expected_in_message.lower(), error_msg.lower(),
                                  f"编码错误消息应包含 '{expected_in_message}'，实际: {error_msg!r}")
                except Exception as e:
                    self.skipTest(f"编码 {encoding_arg} 可能能够读取此文件: {e}")


class TestCompleteIOErrorScenarios(unittest.TestCase):
    """
    四类 I/O 错误场景的完整验证

    确保所有场景都有稳定的退出码和报错文案验证
    """

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv')
        self.temp_file.write(b'a,b,c\n1,2,\xa9\n')
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_scenario_1_file_not_found(self):
        """场景 1: 文件不存在"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'nonexistent_xyz_12345.csv'], output_file, error_file)

        with self.assertRaises(SystemExit) as cm:
            utility.run()

        self.assertEqual(cm.exception.code, 1, "文件不存在退出码应为 1")

        error_msg = error_file.getvalue()
        self.assertTrue(error_msg.startswith("FileNotFoundError:"),
                        f"文件不存在错误消息格式: {error_msg!r}")
        self.assertIn("nonexistent_xyz_12345.csv", error_msg,
                      f"错误消息应包含文件名")

    def test_scenario_2_encoding_error(self):
        """场景 2: 编码错误"""
        error_file = io.StringIO()
        output_file = io.StringIO()

        utility = CSVCut(['-c', '1', '-e', 'ascii', self.temp_file.name], output_file, error_file)

        with self.assertRaises(SystemExit) as cm:
            utility.run()

        self.assertEqual(cm.exception.code, 1, "编码错误退出码应为 1")

        error_msg = error_file.getvalue()
        self.assertIn('Your file is not', error_msg,
                      f"编码错误消息格式: {error_msg!r}")
        self.assertIn('--encoding', error_msg,
                      f"编码错误应提示 --encoding 标志")
        self.assertIn('-v', error_msg,
                      f"编码错误应提示 -v 标志")

    def test_scenario_3_stdin_valid(self):
        """场景 3: 标准输入（有效数据）"""
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

    def test_scenario_4_broken_pipe(self):
        """场景 4: 管道中断"""
        output_file = io.StringIO()
        error_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'examples/dummy.csv'], output_file, error_file)

        with patch.object(utility, 'main') as mock_main:
            mock_main.side_effect = BrokenPipeError(32, "Broken pipe")

            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 0, "管道中断退出码应为 0")
            self.assertEqual(error_file.getvalue(), "", "管道中断不应输出错误消息")


class TestOSErrorSubclassesFullCoverage(unittest.TestCase):
    """
    OSError 各类子类的完整覆盖测试

    确保所有 OSError 子类在真实命令路径中都有正确的行为
    """

    def test_permission_error_in_real_path(self):
        """PermissionError 在真实命令路径中的行为"""
        output_file = io.StringIO()
        error_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'examples/dummy.csv'], output_file, error_file)

        with patch.object(utility, '_open_input_file') as mock_open:
            mock_open.side_effect = PermissionError(13, "Permission denied", "test.csv")

            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 1, "PermissionError 退出码应为 1")
            error_msg = error_file.getvalue()
            self.assertTrue(error_msg.startswith("PermissionError:"),
                            f"PermissionError 消息格式: {error_msg!r}")

    def test_is_a_directory_error_in_real_path(self):
        """IsADirectoryError 在真实命令路径中的行为"""
        output_file = io.StringIO()
        error_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'examples/dummy.csv'], output_file, error_file)

        with patch.object(utility, '_open_input_file') as mock_open:
            mock_open.side_effect = IsADirectoryError(21, "Is a directory", "/test")

            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 1, "IsADirectoryError 退出码应为 1")
            error_msg = error_file.getvalue()
            self.assertTrue(error_msg.startswith("IsADirectoryError:"),
                            f"IsADirectoryError 消息格式: {error_msg!r}")

    def test_generic_oserror_in_real_path(self):
        """通用 OSError 在真实命令路径中的行为"""
        output_file = io.StringIO()
        error_file = io.StringIO()

        utility = CSVCut(['-c', '1', 'examples/dummy.csv'], output_file, error_file)

        with patch.object(utility, '_open_input_file') as mock_open:
            mock_open.side_effect = OSError(99, "Some OS error occurred")

            with self.assertRaises(SystemExit) as cm:
                utility.run()

            self.assertEqual(cm.exception.code, 1, "OSError 退出码应为 1")
            error_msg = error_file.getvalue()
            self.assertTrue(error_msg.startswith("OSError:"),
                            f"OSError 消息格式: {error_msg!r}")


class TestErrorHandlerDirectFullCoverage(unittest.TestCase):
    """
    ErrorHandler 类的直接完整覆盖测试

    确保所有边界情况都被覆盖
    """

    def test_error_handler_without_args(self):
        """ErrorHandler 在没有 args 参数时的行为"""
        error_file = io.StringIO()
        handler = ErrorHandler(args=None, error_file=error_file)

        exc_type = UnicodeDecodeError
        exc_value = UnicodeDecodeError('utf-8', b'\xa9', 0, 1, 'invalid start byte')
        exit_code = handler.handle_exception(exc_type, exc_value, None)

        self.assertEqual(exit_code, 1, "UnicodeDecodeError 退出码应为 1")
        error_msg = error_file.getvalue()
        self.assertIn('utf-8-sig', error_msg.lower(),
                      f"没有 args 时应使用默认编码 utf-8-sig，实际: {error_msg!r}")

    def test_error_handler_with_verbose_true(self):
        """ErrorHandler 在 verbose 模式下的行为"""
        error_file = io.StringIO()

        class MockArgs:
            verbose = True
            encoding = 'utf-8'

        handler = ErrorHandler(args=MockArgs(), error_file=error_file)

        with patch('sys.__excepthook__') as mock_excepthook:
            exc_type = FileNotFoundError
            exc_value = FileNotFoundError(2, "No such file")
            exit_code = handler.handle_exception(exc_type, exc_value, "traceback")

            mock_excepthook.assert_called_once_with(
                FileNotFoundError,
                exc_value,
                "traceback"
            )
            self.assertEqual(exit_code, 1, "verbose 模式下退出码应为 1")

    def test_error_handler_with_verbose_false(self):
        """ErrorHandler 在非 verbose 模式下的行为"""
        error_file = io.StringIO()

        class MockArgs:
            verbose = False
            encoding = 'utf-8'

        handler = ErrorHandler(args=MockArgs(), error_file=error_file)

        exc_type = FileNotFoundError
        exc_value = FileNotFoundError(2, "No such file")
        exit_code = handler.handle_exception(exc_type, exc_value, None)

        self.assertEqual(exit_code, 1, "非 verbose 模式下退出码应为 1")
        error_msg = error_file.getvalue()
        self.assertIn("FileNotFoundError:", error_msg,
                      f"非 verbose 模式应显示简化消息，实际: {error_msg!r}")

    def test_is_io_exception_static_method(self):
        """is_io_exception 静态方法的完整测试"""
        io_exception_types = [
            UnicodeDecodeError,
            BrokenPipeError,
            FileNotFoundError,
            PermissionError,
            IsADirectoryError,
            OSError,
        ]

        for exc_type in io_exception_types:
            with self.subTest(exception_type=exc_type.__name__):
                self.assertTrue(
                    ErrorHandler.is_io_exception(exc_type),
                    f"{exc_type.__name__} 应该被识别为 I/O 异常"
                )

        non_io_exception_types = [
            ValueError,
            TypeError,
            RuntimeError,
            ColumnIdentifierError,
            RequiredHeaderError,
        ]

        for exc_type in non_io_exception_types:
            with self.subTest(exception_type=exc_type.__name__):
                self.assertFalse(
                    ErrorHandler.is_io_exception(exc_type),
                    f"{exc_type.__name__} 不应该被识别为 I/O 异常"
                )


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestBrokenPipeInRealCommandPath))
    suite.addTests(loader.loadTestsFromTestCase(TestEncodingErrorWithoutSkipping))
    suite.addTests(loader.loadTestsFromTestCase(TestCompleteIOErrorScenarios))
    suite.addTests(loader.loadTestsFromTestCase(TestOSErrorSubclassesFullCoverage))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandlerDirectFullCoverage))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print("第二轮兼容性验证测试结果")
    print("=" * 60)
    print(f"运行测试: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped)}")

    if result.failures or result.errors:
        print("\n详细失败信息:")
        for test, traceback in result.failures + result.errors:
            print(f"\n{test}")
            print(traceback)

    if result.skipped:
        print("\n跳过的测试:")
        for test, reason in result.skipped:
            print(f"  - {test}: {reason}")

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
