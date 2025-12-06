import os
import logging
import threading
import yaml
import sys
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Literal
from pydantic import Field, model_validator, field_validator
from pydantic_settings.main import BaseSettings as PydanticBaseSettings, SettingsConfigDict


# 定义环境类型字面量（约束仅允许开发/测试/生产）
EnvironmentType = Literal["development", "test", "production"]
# 定义限流器类型字面量
LimitType = Literal["ip", "id"]


logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(stream=sys.stdout)],  # 仅用控制台处理器
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # 可选：自定义控制台输出格式
)
logger = logging.getLogger(__name__)


class CustomBaseConfig(PydanticBaseSettings):
    """
    自定义配置基类：
    1. 支持从 YAML 文件加载配置
    2. 环境变量可覆盖文件中的配置项
    优先级：环境变量 > 配置文件 > 类默认值
    """

    # 配置类静态字段（需子类覆盖）
    config_key: ClassVar[Optional[str]] = None  # 默认配置文件路径
    config_dir: ClassVar[str] = "configs"
    _config_cache: ClassVar[Dict[Path, dict]] = {}
    _cache_lock: ClassVar[threading.Lock] = threading.Lock()  # 线程安全锁

    @classmethod
    def get_project_root(cls) -> Path:
        """
        获取项目根目录
        优先级：PROJECT_ROOT环境变量 > main.py所在目录 > 工作目录(CWD) > 兜底文件层级推导
        """
        # 1. 最高优先级：环境变量（手动指定，兼容所有场景）
        env_root = os.getenv("PROJECT_ROOT")
        if env_root:
            try:
                root_path = Path(env_root).resolve()
            except OSError as e:
                raise ValueError(f"PROJECT_ROOT路径解析失败: {env_root} - {e}")
            if root_path.is_dir():
                logger.debug(f"✅ 通过环境变量获取项目根: {root_path}")
                return root_path
            raise NotADirectoryError(f"PROJECT_ROOT={env_root} 不是有效目录")

        # 2. 次优先级：通过main.py入口文件推导（最稳定的锚点）
        main_path = cls._get_main_py_path()
        if main_path:
            root_path = main_path.parent.resolve()
            logger.debug(f"✅ 通过main.py获取项目根: {root_path}")
            return root_path

        # 3. 第三优先级：工作目录（PyCharm/容器默认）
        cwd = Path(os.getcwd()).resolve()
        if cwd.is_dir():
            logger.debug(f"✅ 通过工作目录(CWD)获取项目根: {cwd}")
            return cwd

        # 4. 兜底：原有文件层级推导（仅兼容旧场景）
        fallback_root = Path(__file__).resolve().parents[3]
        if fallback_root.is_dir():
            logger.warning(f"⚠️  仅能通过兜底路径获取项目根: {fallback_root}")
            return fallback_root

        raise FileNotFoundError("无法推导项目根目录，请设置 PROJECT_ROOT 环境变量")

    @classmethod
    def _get_main_py_path(cls) -> Optional[Path]:
        """获取项目入口main.py的绝对路径"""
        try:
            # 情况1：直接运行 main.py（python main.py / 容器 CMD 运行）
            if sys.argv and sys.argv[0]:
                main_file = Path(sys.argv[0]).resolve()
                if main_file.name == "main.py" and main_file.is_file():
                    return main_file

            # 情况2：通过模块运行（python -m app.main）
            main_module = sys.modules.get("__main__")
            if main_module and hasattr(main_module, "__file__"):
                main_file = Path(main_module.__file__).resolve()
                if main_file.name == "main.py" and main_file.is_file():
                    return main_file

            return None
        except Exception as e:
            logger.debug(f"获取main.py路径失败: {e}")
            return None

    @staticmethod
    def merge_yaml(base_yaml: dict, config_yaml: dict) -> dict:
        merged = base_yaml.copy()
        for key, value in config_yaml.items():
            if key in merged:
                if isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key] = CustomBaseConfig.merge_yaml(merged[key], value)
                elif isinstance(merged[key], list) and isinstance(value, list):
                    # 合并列表，避免重复项
                    merged[key] = list({item: None for item in merged[key] + value}.keys())
                else:
                    merged[key] = value
            else:
                merged[key] = value
        return merged

    @staticmethod
    def merge_env(base: Dict, update: Dict) -> Dict:
        merged = base.copy()
        for key, value in update.items():
            if key in merged:
                if isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key] = CustomBaseConfig.merge_env(merged[key], value)
                else:
                    merged[key] = value
            else:
                merged[key] = value
        return merged

    @model_validator(mode='before')
    @classmethod
    def load_configs_from_dir(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 计算配置目录绝对路径
            config_dir = cls.get_project_root() / "app" / cls.config_dir
            config_dir = config_dir.resolve()

            # 线程安全的缓存加载
            with cls._cache_lock:
                if config_dir not in cls._config_cache:
                    cls._config_cache[config_dir] = cls._load_and_merge_configs(config_dir)
                env_config = cls._config_cache[config_dir]

            # 提取当前类对应的配置段
            config_key = cls.config_key or cls.__name__.lower()
            config_section = env_config.get(config_key, {})

            # 合并优先级：环境变量(values) > 配置文件(config_section)
            merged = cls.merge_env(config_section, values)
            return merged
        except Exception as e:
            logger.error(f"加载配置失败: {e}", exc_info=True)
            return values

    @classmethod
    def _load_and_merge_configs(cls, config_dir: Path) -> dict:
        """加载并合并目录下所有YAML配置文件"""
        env_config = {}
        if not config_dir.exists():
            logger.warning(f"配置目录不存在: {config_dir}")
            return env_config
        if not config_dir.is_dir():
            logger.error(f"指定路径不是目录: {config_dir}")
            return env_config

        # 按文件名排序加载（保证加载顺序）
        config_files = sorted(
            [f for f in config_dir.iterdir() if f.suffix in ('.yaml', '.yml')],
            key=lambda x: x.name
        )
        for config_file in config_files:
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    file_config = yaml.safe_load(f) or {}
                    env_config = cls.merge_yaml(env_config, file_config)
                logger.debug(f"成功加载配置文件: {config_file}")
            except yaml.YAMLError as e:
                logger.error(f"解析YAML文件失败 {config_file}: {e}", exc_info=True)
            except PermissionError as e:
                logger.error(f"无权限读取配置文件 {config_file}: {e}", exc_info=True)
        return env_config

    model_config = SettingsConfigDict(
        extra='ignore',
        env_prefix="APP_",
        env_nested_delimiter="__",  # 使用双下划线表示嵌套字段，例如 APP_DB__HOST 对应 db.host
        case_sensitive=False,  # 环境变量不区分大小写
    )


class ServerConfig(CustomBaseConfig):
    """
    服务器相关的配置类，包含 API 前缀、标题、版本和运行环境。
    """
    config_key = "server"
    api_prefix: str = ''
    api_title: str = 'Default Title'
    api_version: str = 'v1'
    environment: EnvironmentType = 'development'

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> EnvironmentType:
        """校验运行环境仅允许开发/测试/生产"""
        allowed_envs: List[EnvironmentType] = ["development", "test", "production"]
        if v not in allowed_envs:
            raise ValueError(
                f"运行环境仅支持 {allowed_envs}，当前值: {v}"
            )
        return v

    model_config = SettingsConfigDict(
        env_prefix='SERVER_'  # 环境变量前缀，环境变量如 SERVER_API_PREFIX 将映射到 api_prefix
    )


class UvicornConfig(CustomBaseConfig):
    """
    Uvicorn 服务器配置类，包含主机地址、端口、是否热重载、日志级别等配置。
    """
    config_key = "uvicorn"
    host: str = '127.0.0.1'
    port: int = 8000
    reload: bool = False
    log_level: str = 'info'
    environment: EnvironmentType = 'development'

    def __init__(self, **values):
        super().__init__(**values)
        # 如果环境不是生产环境，启用热重载
        if values.get("reload") is None:
            self.reload = self.environment != 'production'

    model_config = SettingsConfigDict(
        env_prefix='UVICORN_'  # 使用 UVICORN_ 作为环境变量前缀
    )


class DatabaseConfig(PydanticBaseSettings):
    host: str = "localhost"
    port: int = 3306
    user: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None

    @field_validator('port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"Database port {v} is invalid (must be 1-65535)")
        return v


class TortoiseConfig(CustomBaseConfig):
    """
    Tortoise ORM 配置类，包含数据库连接的详细配置项。
    """
    config_key = "tortoise"
    engine: str = 'tortoise.backends.mysql'
    min_connections: int = 1
    max_connections: int = 5
    charset: str = 'utf8mb4'
    echo: bool = False
    use_tz: bool = False
    timezone: str = 'Asia/Shanghai'
    pool_recycle: int = 28000  # 小于 wait_timeout 和 interactive_timeout
    global_models: str = 'aerich.models,app.models.common.UserModels,app.models.common.RoleModels'
    additional_models: str = ''

    master: DatabaseConfig = Field(default_factory=DatabaseConfig)
    replica: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @model_validator(mode='after')
    def sync_replica_with_master(self) -> "TortoiseConfig":
        """
        后置验证器：若replica未显式配置（使用默认值），则自动复用master的配置
        实现“主库即从库”的需求，同时保留主从分离的灵活性
        """
        # 判断replica是否为默认配置（对比DatabaseConfig的初始值）
        default_replica = DatabaseConfig()
        is_replica_default = (
                self.replica.host == default_replica.host
                and self.replica.port == default_replica.port
                and self.replica.user == default_replica.user
                and self.replica.database == default_replica.database
        )

        if is_replica_default:
            self.replica = self.master.model_copy()  # 复用master配置

        return self

    def get_tortoise_orm(self) -> dict:
        """
        生成 Tortoise ORM 配置字典，包括数据库连接配置和模型配置。

        :return: Tortoise ORM 配置字典
        """
        models_list = [item.strip() for item in (self.global_models + ',' + self.additional_models).split(',') if item]
        return {
            "connections": {
                "master": {
                    "engine": self.engine,
                    "credentials": {
                        "host": self.master.host,
                        "port": self.master.port,
                        "user": self.master.user,
                        "password": self.master.password,
                        "database": self.master.database,
                        "minsize": self.min_connections,
                        "maxsize": self.max_connections,
                    }
                },
                "replica": {
                    "engine": self.engine,
                    "credentials": {
                        "host": self.replica.host,
                        "port": self.replica.port,
                        "user": self.replica.user,
                        "password": self.replica.password,
                        "database": self.replica.database,
                        "minsize": self.min_connections,
                        "maxsize": self.max_connections,
                    }
                }
            },
            "apps": {
                "models": {
                    "models": models_list,
                    "default_connection": "master",
                }
            },
            "routers": ["app.common.databases.router.DatabaseRouter"],
            "use_tz": self.use_tz,
            "timezone": self.timezone,
            "pool_recycle": self.pool_recycle
        }

    # 支持 TORTOISE_MASTER__HOST 格式的环境变量
    model_config = SettingsConfigDict(
        env_prefix='TORTOISE_'  # 使用 TORTOISE_ 作为数据库相关环境变量的前缀
    )


class RedisSingleConfig(PydanticBaseSettings):
    host: str = "localhost"
    port: int = 1234
    database: int = 0
    user: Optional[str] = None
    password: Optional[str] = None

    @field_validator('port')
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"Redis port {v} is invalid (must be 1-65535)")
        return v


class RedisConfig(CustomBaseConfig):
    """
    Redis 配置类，包含 Redis 服务器连接的相关配置。
    """
    config_key = "redis"
    master: RedisSingleConfig = Field(default_factory=RedisSingleConfig)
    replica: RedisSingleConfig = Field(default_factory=RedisSingleConfig)

    # 支持 REDIS_MASTER__HOST 格式的环境变量
    model_config = SettingsConfigDict(
        env_prefix='REDIS_'  # 使用 REDIS_ 作为 Redis 环境变量的前缀
    )


class JWTConfig(CustomBaseConfig):
    """
    JWT 配置类，包含 JWT 的加密算法、过期时间及密钥路径等配置。
    """
    config_key = "jwt"
    algorithm: str = 'RS256'
    access_expire_minutes: int = 15
    refresh_expire_days: int = 30
    private_key_path: Optional[str] = None
    public_key_path: Optional[str] = None
    issuer: str = 'azer.cc'
    token_prefix: str = "Bearer "  # Token前缀（默认Bearer）
    redis_session_prefix: str = "session:"  # Redis会话前缀（兼容原有build_redis_key逻辑）

    def __init__(self, **data):
        super().__init__(**data)
        project_root = self.get_project_root()
        if self.private_key_path:
            self.private_key_path = str(project_root / self.private_key_path)
            if not Path(self.private_key_path).exists():
                logger.warning(f"JWT私钥文件不存在: {self.private_key_path}")
        if self.public_key_path:
            self.public_key_path = str(project_root / self.public_key_path)
            if not Path(self.public_key_path).exists():
                logger.warning(f"JWT公钥文件不存在: {self.public_key_path}")

    @field_validator("algorithm")
    @classmethod
    def validate_port(cls, v: str) -> str:
        allowed_algos = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"]
        if v not in allowed_algos:
            raise ValueError(f"JWT算法仅支持{allowed_algos}，当前为{v}")
        return v

    model_config = SettingsConfigDict(
        env_prefix='JWT_'  # 使用 JWT_ 作为 JWT 配置相关环境变量的前缀
    )


class RateLimiterConfig(CustomBaseConfig):
    """
    限流器配置类，定义每分钟的低、中、高限速及限速类型（基于 IP 或用户 ID）。
    """
    config_key = "rate_limiter"
    environment: EnvironmentType = 'development'
    default_times: int = 5  # 默认限速次数（每分钟）
    default_limit_type: LimitType = "ip"  # 默认限速类型：ip/id
    low: Optional[int] = None
    medium: Optional[int] = None
    high: Optional[int] = None

    @field_validator("default_limit_type")
    @classmethod
    def validate_limit_type(cls, v: str) -> LimitType:
        """校验限速类型仅允许ip/id"""
        allowed_types: List[LimitType] = ["ip", "id"]
        if v not in allowed_types:
            raise ValueError(f"限速类型仅支持 {allowed_types}，当前值: {v}")
        return v

    model_config = SettingsConfigDict(
        env_prefix='RATE_LIMITER_'  # 使用 RATE_LIMITER_ 作为限流器环境变量的前缀
    )


class LoggingConfig(CustomBaseConfig):
    """
    日志配置类，定义日志的存储路径、日志级别、日志格式、日志轮换时间间隔、保留的备份文件数量。
    """
    config_key = "logging"
    service_path: Optional[str] = None
    task_path: Optional[str] = None
    level: str = 'INFO'
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    interval: int = 1  # 日志轮换时间间隔，单位为小时
    backup_count: int = 7  # 保留的备份文件数量
    sensitive_fields: List[str] = Field(  # 新增敏感字段配置
        default_factory=list,
        description="需要脱敏的字段名列表（不区分大小写）"
    )
    sensitive_routes: List[str] = Field(  # 新增敏感路由配置
        default_factory=list,
        description="需要跳过请求体记录的路由路径"
    )

    def __init__(self, **data):
        super().__init__(**data)
        project_root = self.get_project_root()
        if self.service_path:
            self.service_path = str(project_root / self.service_path)
            log_dir = Path(self.service_path).parent
            if not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"创建日志目录: {log_dir}")
        if self.task_path:
            self.task_path = str(project_root / self.task_path)
            log_dir = Path(self.task_path).parent
            if not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"创建日志目录: {log_dir}")

    model_config = SettingsConfigDict(
        env_prefix='LOGGING_',  # 使用 LOGGING_ 作为日志配置相关环境变量的前缀
        json_schema_extra={
            "example": {
                "sensitive_fields": ["password", "credit_card"],
                "sensitive_routes": ["/login/*"]
            }
        }
    )


class BaseConfig:
    """
    BaseConfig 类负责初始化和微服务项目的基础配置项，包括服务器配置、Uvicorn 配置、
    数据库配置、Redis 配置、JWT 配置和限流器配置。通过 BaseConfig 类可以全局访问这些配置。
    """

    def __init__(self):
        # 获取项目根目录的绝对路径，用于相对路径的拼接或其他需要项目路径的场景。
        self.project_root: Path = CustomBaseConfig.get_project_root()

        # 服务器相关配置的实例化，包括 API 前缀、标题、版本和环境等。
        self.server = ServerConfig()

        # Uvicorn 服务器配置的实例化，包括主机、端口、是否热重载、日志级别等。这里的 environment 参数从 server 配置继承。
        self.uvicorn = UvicornConfig(environment=self.server.environment)

        # Tortoise ORM 数据库配置的实例化，包括数据库连接的详细信息和 ORM 模型配置。
        self.tortoise = TortoiseConfig()

        # Redis 配置的实例化，包括 Redis 主机、端口、数据库编号、用户和密码等。
        self.redis = RedisConfig()

        # JWT 配置的实例化，包括加密算法、过期时间、密钥路径、issuer 等。
        self.jwt = JWTConfig()

        # 限流器配置的实例化，包括每分钟低、中、高频次的限速，以及限速类型（IP 或用户 ID）。
        self.rate_limiter = RateLimiterConfig(environment=self.server.environment)

        # 日志配置的实例化，包括日志存储路径、日志级别、日志格式、日志轮换时间间隔、保留的备份文件数量等。
        self.logging = LoggingConfig()

    def get_project_root(self) -> str:
        """
        获取项目根目录的绝对路径。

        :return: 项目根目录的路径字符串。
        """
        return str(self.project_root)
