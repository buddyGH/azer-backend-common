import inspect
import os
import time


def dprint(*args):
    """
    调试打印函数，只有在开发环境中才会输出调试信息。

    :param args: 任意数量的参数，支持多个值的调试信息打印
    """

    # 读取环境变量 SERVER_ENVIRONMENT，无值则返回None
    server_env = os.getenv("SERVER__ENVIRONMENT")

    # 读取不到环境变量：打印提示到控制台，不执行后续逻辑
    if server_env is None:
        print("[WARNING] 未读取到环境变量 SERVER_ENVIRONMENT，跳过调试打印")
        return

    # 仅在开发环境下打印调试信息
    if server_env == "development":
        # 获取当前时间戳，并格式化为 年-月-日 时:分:秒 的形式
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        # 获取调用该函数上一层栈帧信息
        frame = inspect.currentframe().f_back
        file_name = frame.f_code.co_filename  # 获取文件名
        line_number = frame.f_lineno  # 获取行号
        function_name = frame.f_code.co_name  # 获取函数名

        # 将传入的所有参数组合为字符串形式
        message = " ".join(map(str, args))

        # 打印详细的调试信息，包括时间、文件名、函数名、行号和调试信息
        print(
            f"[DEBUG] {current_time} | File: {file_name}, Function: {function_name}, "
            f"Line: {line_number} | Message: {message}"
        )
