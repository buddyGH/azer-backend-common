import inspect
import json
import logging
import os
import time
import tempfile
from logging.handlers import TimedRotatingFileHandler
from typing import List, Union, Optional
from urllib.parse import parse_qs
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp
from azer_common.configs.base import LoggingConfig


def get_microservice_default_log_path(log_type: str) -> str:
    """
    动态生成微服务侧的默认日志路径（核心：归属微服务，而非公共包）
    :param log_type: 日志类型（service/task）
    :return: 微服务运行目录下的日志路径，兜底用系统临时目录
    """
    # 步骤1：获取微服务的运行目录（而非公共包目录）
    # __main__ 是微服务的启动文件，其所在目录即为微服务根目录
    try:
        import __main__

        microservice_root = os.path.dirname(os.path.abspath(__main__.__file__))
    except (ImportError, AttributeError):
        # 兜底：无__main__时，用当前工作目录
        microservice_root = os.getcwd()

    # 步骤2：微服务根目录下的logs目录（优先）
    default_log_dir = os.path.join(microservice_root, "logs")
    os.makedirs(default_log_dir, exist_ok=True)

    # 步骤3：生成具体日志文件路径
    default_log_path = os.path.join(default_log_dir, f"{log_type}.log")

    # 容错：若微服务目录无写入权限，降级到系统临时目录
    try:
        with open(default_log_path, "a", encoding="utf-8"):
            pass  # 测试写入权限
    except (PermissionError, OSError):
        default_log_path = os.path.join(
            tempfile.gettempdir(), f"azer_{log_type}.log"  # 系统临时目录（如Linux:/tmp，Windows:%TEMP%）
        )

    return default_log_path


def get_effective_log_path(config_path: Optional[str], log_type: str) -> str:
    """
    获取最终生效的日志路径（优先级：微服务显式配置 > 微服务默认路径 > 系统临时目录）
    :param config_path: 微服务配置的路径（None则用默认）
    :param log_type: 日志类型（service/task）
    :return: 最终日志路径
    """
    if config_path:
        return config_path
    return get_microservice_default_log_path(log_type)


# 公共日志配置函数
def setup_logger(
    log_name: str, log_config: LoggingConfig, log_file_path: Optional[str] = None  # 注入通用配置（核心解耦点）
) -> logging.Logger:
    """
    设置日志记录器，动态决定日志输出到文件或标准输出
    :param log_name: 日志记录器名称
    :param log_config: 通用日志配置模型（微服务侧注入）
    :param log_file_path: 日志文件路径（可选，优先级高于配置中的路径）
    :return: 配置好的Logger
    """

    # 解析日志级别（兼容字符串/枚举）
    log_level = getattr(logging, log_config.level.upper(), logging.INFO)

    # 定义日志格式
    log_formatter = logging.Formatter(log_config.format)

    # 如果提供了日志文件路径，则输出到文件，否则输出到stdout
    if log_file_path:
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        log_handler = TimedRotatingFileHandler(
            log_file_path,
            when="midnight",
            interval=log_config.interval,
            backupCount=log_config.backup_count,
            encoding="utf-8",
        )
    else:
        log_handler = logging.StreamHandler()
        log_handler.stream.reconfigure(encoding="utf-8")

    log_handler.setFormatter(log_formatter)

    # 获取日志记录器，并设置日志级别
    logger = logging.getLogger(log_name)
    logger.setLevel(log_level)

    # 防止重复添加处理器
    if not logger.handlers:
        logger.addHandler(log_handler)

    # 禁用父级传播（避免重复日志）
    logger.propagate = False

    return logger


# -------------------------- 日志记录器工厂函数（微服务侧调用） --------------------------
def create_service_logger(log_config: LoggingConfig) -> logging.Logger:
    """创建服务请求日志器（微服务侧调用，传入配置）"""
    # 获取最终路径（微服务配置 > 微服务logs目录 > 系统临时目录）
    log_file_path = get_effective_log_path(log_config.service_path, "service")

    # 友好提示：使用默认路径时告知用户
    if not log_config.service_path:
        temp_logger = logging.getLogger("default_logger_hint")
        temp_logger.warning(f"未配置service_logger路径，自动使用微服务侧默认路径：{log_file_path}\n")

    return setup_logger(log_name="service_logger", log_config=log_config, log_file_path=log_config.service_path)


def create_task_logger(log_config: LoggingConfig) -> logging.Logger:
    """创建定时任务日志器（微服务侧调用，传入配置）"""
    log_file_path = get_effective_log_path(log_config.task_path, "task")

    if not log_config.task_path:
        temp_logger = logging.getLogger("default_logger_hint")
        temp_logger.warning(f"未配置task_logger路径，自动使用微服务侧默认路径：{log_file_path}\n")

    return setup_logger(log_name="task_logger", log_config=log_config, log_file_path=log_config.task_path)


# HTTP请求日志中间件
class LoggingMiddleware(BaseHTTPMiddleware):
    """
    中间件，用于记录每个HTTP请求的详细信息和响应信息
    支持：
    1. exclude_routes：完全排除指定路由的所有日志
    2. sensitive_routes：仅跳过指定路由的请求体日志
    3. sensitive_fields：过滤请求体中的敏感字段值
    """

    def __init__(self, app: ASGIApp, log_config: LoggingConfig):
        super().__init__(app)
        self.log_config = log_config
        self.service_logger = create_service_logger(log_config)

        # 1. 预处理敏感路由（仅跳过请求体）
        self.valid_sensitive_routes = []
        for raw_route in self.log_config.sensitive_routes:
            route = raw_route.strip()
            if not route:
                continue
            route = route.rstrip("/")  # 统一去除末尾斜杠
            self.valid_sensitive_routes.append(route)

        # 2. 预处理排除路由（完全不记录日志）
        self.valid_exclude_routes = []
        for raw_route in self.log_config.exclude_routes:
            route = raw_route.strip()
            if not route:
                continue
            route = route.rstrip("/")  # 统一去除末尾斜杠
            self.valid_exclude_routes.append(route)

        # 3. 预处理敏感请求头（转小写，避免大小写不匹配）
        self.valid_sensitive_headers = [h.lower() for h in self.log_config.sensitive_headers]

    def filter_sensitive_headers(self, headers: dict) -> dict:
        """过滤请求头中的敏感字段（保留Bearer前缀）"""
        filtered = {}
        for key, value in headers.items():
            if key.lower() in self.valid_sensitive_headers:
                if key.lower() == "authorization" and value.startswith("Bearer "):
                    # 保留Bearer前缀，屏蔽后续Token
                    filtered[key] = "Bearer ***"
                else:
                    filtered[key] = "***"
            else:
                filtered[key] = value
        return filtered

    @classmethod
    def filter_sensitive_data(cls, data: Union[dict, list], sensitive_fields: List[str]) -> Union[dict, list]:
        """
        类型安全的敏感数据过滤方法
        """
        if isinstance(data, dict):
            return {
                key: "***" if key.lower() in sensitive_fields else cls.filter_sensitive_data(value, sensitive_fields)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [cls.filter_sensitive_data(item, sensitive_fields) for item in data]
        return data

    async def _process_body(self, request: Request) -> str:
        """处理请求体并过滤敏感信息"""
        content_type = request.headers.get("content-type", "")
        raw_body = await request.body()

        try:
            # JSON 数据处理
            if "application/json" in content_type:
                json_body = json.loads(raw_body.decode(encoding="utf-8", errors="replace"))
                filtered = self.filter_sensitive_data(json_body, self.log_config.sensitive_fields)
                return json.dumps(filtered, ensure_ascii=False)

            # 表单数据处理
            elif "application/x-www-form-urlencoded" in content_type:
                form_data = parse_qs(raw_body.decode(encoding="utf-8", errors="replace"))
                filtered = {k: ["***"] if k in self.log_config.sensitive_fields else v for k, v in form_data.items()}
                return str(filtered)

            # 其他文本类型
            elif "text/" in content_type:
                return raw_body.decode(encoding="utf-8", errors="replace")

            # 二进制数据不记录
            else:
                return "[BINARY DATA]"

        except Exception as e:
            self.service_logger.error(f"Body processing error: {str(e)}")
            return "[ERROR PROCESSING BODY]"

    @staticmethod
    def _is_route_match(request_path: str, target_routes: List[str]) -> bool:
        """
        通用路由匹配逻辑（支持精确匹配 + 通配符匹配）
        :param request_path: 请求实际路径（如 /probes/health）
        :param target_routes: 配置的目标路由列表（如 ["/probes*", "/auth"]）
        :return: 是否匹配
        """
        # 统一处理请求路径（去末尾斜杠）
        normalized_path = request_path.rstrip("/")

        for route in target_routes:
            # 通配符匹配（如 /probes* 匹配 /probes/health、/probes/liveness）
            if route.endswith("*"):
                prefix = route[:-1]
                if normalized_path.startswith(prefix):
                    return True
            # 精确匹配（如 /probes 匹配 /probes 或 /probes/）
            elif normalized_path == route:
                return True
        return False

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """处理请求日志记录"""
        start_time = time.time()
        path = request.url.path

        # 优先判断是否为排除路由，匹配则直接跳过所有日志
        if self._is_route_match(path, self.valid_exclude_routes):
            response = await call_next(request)
            return response

        raw_headers = dict(request.headers)
        filtered_headers = self.filter_sensitive_headers(raw_headers)
        self.service_logger.info(f"Request: {request.method} {request.url}")
        self.service_logger.info(f"Headers: {dict(filtered_headers)}")

        if self._is_route_match(path, self.valid_sensitive_routes):
            self.service_logger.info("Request body: [SENSITIVE ROUTE SKIPPED]")
        else:
            if request.method in ["POST", "PUT", "PATCH"]:
                filtered_body = await self._process_body(request)
                self.service_logger.info(f"Filtered Request Body: {filtered_body}")

        response = await call_next(request)
        process_time = time.time() - start_time

        self.service_logger.info(
            f"Response: {response.status_code} | " f"Time: {process_time:.2f}s | " f"Headers: {dict(response.headers)}"
        )
        return response


# 动态记录任务日志的函数
def log_task_message(message: str, logger: Optional[logging.Logger] = None, log_config: Optional[LoggingConfig] = None):
    """
    记录任务日志信息，包括任务函数名和执行时间

    :param message: 日志信息
    :param logger: 自定义Logger（优先使用）
    :param log_config: 通用日志配置（无logger时使用）
    """
    # 优先级1：使用传入的自定义logger
    if logger is not None:
        target_logger = logger
    else:
        # 优先级2：查找已初始化的task_logger（避免重复创建）
        existing_task_logger = logging.getLogger("task_logger")
        # 判断是否是"有效"的logger（有处理器、非默认级别）
        if existing_task_logger.handlers:
            target_logger = existing_task_logger
        else:
            # 优先级3：无有效实例时，创建新的task_logger
            if log_config is None:
                # 兜底：使用默认配置创建临时logger
                log_config = LoggingConfig()
                temp_logger = logging.getLogger("default_logger_hint")
                temp_logger.warning(
                    "未传入logger和log_config，自动使用微服务侧默认路径创建task_logger\n"
                    "建议显式传入logger或配置LoggingConfig的task_path！"
                )
            target_logger = create_task_logger(log_config)

    # 获取调用此函数上一帧栈信息，以提取任务的函数名
    frame = inspect.currentframe().f_back
    function_name = frame.f_code.co_name  # 获取任务的函数名
    # 安全清理栈帧（避免内存泄漏）
    del frame

    # 获取当前时间戳
    current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    # 组合详细日志信息，包括任务执行的时间和函数名
    detailed_message = f"[{current_time}] {message} | Task Function: {function_name}"

    # 将详细日志信息记录到日志文件
    target_logger.info(detailed_message)
