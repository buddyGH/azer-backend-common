"""
项目路径解析器
用于智能获取项目根目录和各种关键路径
"""

import os
import sys
from pathlib import Path
from typing import Optional
import logging

# 配置日志
logger = logging.getLogger(__name__)


class PathResolver:
    """
    项目路径解析器
    智能获取项目根目录和各种关键路径
    """

    # 类常量定义（提升可读性和可维护性）
    _PROJECT_STRUCTURE_MARKS = ("main.py", "app", "src")  # 项目结构标志
    _CONTAINER_ENV_VARS = (
        "KUBERNETES_SERVICE_HOST",  # Kubernetes
        "DOCKER_CONTAINER",  # Docker
        "CONTAINER_ID",  # 通用容器标识
        "AZURE_CONTAINER_NAME",  # Azure容器
    )

    # 缓存属性
    _project_root_cache: Optional[Path] = None
    _is_container_env: Optional[bool] = None
    _project_layout: Optional[str] = None  # 'app' 或 'src' 布局

    @classmethod
    def get_project_root(cls, use_cache: bool = True) -> Path:
        """
        获取项目根目录（纯路径获取，无打印逻辑）

        Args:
            use_cache: 是否使用缓存的结果

        Returns:
            Path: 项目根目录的Path对象

        Raises:
            FileNotFoundError: 所有路径检测方式失败时抛出，提示设置PROJECT_ROOT环境变量
        """
        # 使用缓存（如果可用且允许）
        if use_cache and cls._project_root_cache and cls._project_root_cache.exists():
            return cls._project_root_cache

        # 1. 最高优先级：环境变量（手动指定，兼容所有场景）
        env_root = os.getenv("PROJECT_ROOT")
        if env_root:
            try:
                root_path = Path(env_root).resolve()
                if root_path.is_dir():
                    logger.info(f"✅ 通过环境变量获取项目根目录: {root_path}")
                    cls._project_root_cache = root_path
                    cls._detect_project_layout(root_path)  # 检测项目布局
                    return root_path
                else:
                    logger.warning(f"环境变量PROJECT_ROOT指定的路径不存在: {env_root}")
            except Exception as e:
                logger.warning(f"解析环境变量PROJECT_ROOT失败: {e}")

        # 2. 次优先级：通过main.py入口文件推导（最稳定的锚点）
        main_path = cls._find_main_py_path()
        if main_path:
            root_path = main_path.parent.resolve()
            logger.info(f"✅ 通过main.py获取项目根目录: {root_path}")
            cls._project_root_cache = root_path
            cls._detect_project_layout(root_path)  # 检测项目布局
            return root_path

        # 3. 判断是否为容器环境
        if cls._is_container_environment():
            # 容器环境默认路径
            container_root = Path("/microservice")
            if container_root.exists() and container_root.is_dir():
                logger.info(f"✅ 容器环境，使用默认项目根目录: {container_root}")
                cls._project_root_cache = container_root
                cls._detect_project_layout(container_root)  # 检测项目布局
                return container_root

        # 4. 工作目录检查（支持app和src两种布局）
        cwd = Path(os.getcwd()).resolve()
        detected_root = cls._detect_root_from_cwd(cwd)
        if detected_root:
            logger.info(f"✅ 通过工作目录获取项目根目录: {detected_root}")
            cls._project_root_cache = detected_root
            cls._detect_project_layout(detected_root)  # 检测项目布局
            return detected_root

        # 5. 向上回溯查找（最多回溯5层）
        current_file = Path(__file__).resolve()
        for i in range(5):
            parent = current_file.parents[i]
            # 检查父目录是否有项目结构标志
            if cls._has_project_structure(parent):
                logger.info(f"✅ 通过文件回溯获取项目根目录: {parent}")
                cls._project_root_cache = parent
                cls._detect_project_layout(parent)  # 检测项目布局
                return parent

        # 6. 最后尝试：当前文件所在的app/utils目录的上两级
        fallback_root = Path(__file__).resolve().parents[2]  # app/utils -> app -> project_root
        if fallback_root.exists():
            logger.warning(f"⚠️  使用兜底路径作为项目根目录: {fallback_root}")
            cls._project_root_cache = fallback_root
            cls._detect_project_layout(fallback_root)  # 检测项目布局
            return fallback_root

        error_msg = "无法找到项目根目录，请设置PROJECT_ROOT环境变量或确保项目结构正确"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    @classmethod
    def print_project_structure(cls, max_depth: int = 3) -> None:
        """
        打印真实的项目目录结构（独立方法，无备注、读取真实文件/文件夹名）

        Args:
            max_depth: 打印的最大目录深度，默认3层（根目录 + 2级子目录）

        Raises:
            FileNotFoundError: 依赖get_project_root，根目录查找失败时抛出
        """
        # 定义需要排除的目录（可根据实际需求扩展）
        _EXCLUDE_DIRS = {
            "__pycache__",
            ".git",
            ".venv",
            "env",
            "tests",
            ".idea",
            ".vscode",
            "node_modules",
            "dist",
            "build",
            ".pytest_cache",
            ".mypy_cache",
            ".gitignore",
            ".hypothesis",
        }

        root_path = cls.get_project_root()
        structure = [f"{root_path.name}/", "│"]

        # 遍历根目录下的所有项（按名称排序，过滤排除目录）
        root_items = sorted(
            [item for item in root_path.iterdir() if item.name not in _EXCLUDE_DIRS], key=lambda x: x.name
        )
        for idx, item in enumerate(root_items):
            # 控制打印深度
            if max_depth <= 1:
                continue

            # 根目录项的前缀（最后一项用└──，其余用├──）
            prefix = "└── " if idx == len(root_items) - 1 else "├── "
            item_name = item.name + "/" if item.is_dir() else item.name
            structure.append(f"{prefix}{item_name}")

            # 遍历二级目录（仅处理文件夹，过滤排除目录）
            if item.is_dir() and max_depth >= 2:
                sub_items = sorted(
                    [sub for sub in item.iterdir() if sub.name not in _EXCLUDE_DIRS], key=lambda x: x.name
                )
                for sub_idx, sub_item in enumerate(sub_items):
                    # 二级目录前缀（根据父级是否最后一项调整竖线）
                    parent_prefix = "    " if idx == len(root_items) - 1 else "│   "
                    sub_prefix = "└── " if sub_idx == len(sub_items) - 1 else "├── "
                    sub_item_name = sub_item.name + "/" if sub_item.is_dir() else sub_item.name
                    structure.append(f"{parent_prefix}{sub_prefix}{sub_item_name}")

                    # 遍历三级目录（仅处理文件夹，max_depth>=3时，过滤排除目录）
                    if sub_item.is_dir() and max_depth >= 3:
                        sub2_items = sorted(
                            [sub2 for sub2 in sub_item.iterdir() if sub2.name not in _EXCLUDE_DIRS],
                            key=lambda x: x.name,
                        )
                        for sub2_idx, sub2_item in enumerate(sub2_items):
                            # 三级目录前缀
                            sub_parent_prefix = "    " if sub_idx == len(sub_items) - 1 else "│   "
                            sub2_prefix = "└── " if sub2_idx == len(sub2_items) - 1 else "├── "
                            sub2_item_name = sub2_item.name + "/" if sub2_item.is_dir() else sub2_item.name
                            structure.append(f"{parent_prefix}{sub_parent_prefix}{sub2_prefix}{sub2_item_name}")

        # 打印最终结构
        logger.info("\n项目真实目录结构:\n" + "\n".join(structure))

    @classmethod
    def _internal_get_subdir(cls, subdir_name: str) -> Path:
        """
        通用子目录查找方法（提取重复逻辑）

        Args:
            subdir_name: 子目录名称（如models/api/core）

        Returns:
            Path: 子目录路径（不存在时返回源码目录下的路径，仅报警告）
        """
        source_dir = cls.get_source_dir()
        subdir = source_dir / subdir_name

        # 针对src布局，检查src/app下的子目录（兼容逻辑）
        if source_dir.name == "src":
            app_subdir = source_dir / "app" / subdir_name
            if app_subdir.exists():
                subdir = app_subdir

        # 子目录不存在时，返回源码目录下的路径并报警告（不抛异常）
        if not subdir.exists():
            logger.warning(f"⚠️  未找到{subdir_name}目录: {subdir}，使用源码目录兜底: {source_dir}")
            subdir = source_dir / subdir_name  # 兜底到源码目录下的路径

        return subdir

    @classmethod
    def _find_main_py_path(cls) -> Optional[Path]:
        """
        查找main.py文件的路径

        Returns:
            Optional[Path]: main.py的Path对象，如果未找到则返回None
        """
        # 方法1: 从sys.modules中查找
        if "main" in sys.modules:
            main_module = sys.modules["main"]
            if hasattr(main_module, "__file__") and main_module.__file__:
                main_path = Path(main_module.__file__)
                if main_path.exists() and main_path.name == "main.py":
                    return main_path.resolve()

        # 方法2: 从常见位置查找（优化路径检查，减少重复resolve）
        possible_paths = [
            Path("main.py"),
            Path.cwd() / "main.py",
            Path("/microservice/main.py"),  # 容器环境
            Path(__file__).resolve().parents[2] / "main.py",  # app/utils -> app -> project_root
        ]

        for path in possible_paths:
            if path.is_file():
                return path.resolve()

        return None

    @classmethod
    def _is_container_environment(cls) -> bool:
        """
        判断是否运行在容器环境中

        Returns:
            bool: 是否是容器环境
        """
        if cls._is_container_env is not None:
            return cls._is_container_env

        # 先检查环境变量（IO操作少，优先级高）
        for env_var in cls._CONTAINER_ENV_VARS:
            if os.getenv(env_var):
                cls._is_container_env = True
                return True

        # 再检查文件系统（IO操作，优先级低）
        try:
            # 检查docker环境文件
            if Path("/.dockerenv").exists():
                cls._is_container_env = True
                return True

            # 检查cgroup（仅当必要时）
            with open("/proc/1/cgroup", "r") as f:
                content = f.read()
                if "docker" in content or "kubepods" in content:
                    cls._is_container_env = True
                    return True
        except (FileNotFoundError, PermissionError, OSError):
            pass

        cls._is_container_env = False
        return False

    @classmethod
    def _detect_root_from_cwd(cls, cwd: Path) -> Optional[Path]:
        """
        从工作目录检测项目根目录

        Args:
            cwd: 当前工作目录

        Returns:
            Optional[Path]: 检测到的项目根目录，未检测到则返回None
        """
        # 检查当前目录是否有项目结构标志
        if cls._has_project_structure(cwd):
            return cwd

        # 检查src布局：cwd/src目录下是否有项目结构
        src_dir = cwd / "src"
        if src_dir.is_dir():
            # 检查src目录下是否有app目录和main.py
            if (src_dir / "app").is_dir() and (src_dir / "main.py").is_file():
                return src_dir
            # 或者src目录本身就是app目录（main.py在cwd）
            elif (cwd / "main.py").is_file() and (src_dir / "__init__.py").is_file():
                return cwd

        return None

    @classmethod
    def _has_project_structure(cls, path: Path) -> bool:
        """
        检查路径是否具有项目结构标志（使用常量，提升可读性）

        Args:
            path: 要检查的路径

        Returns:
            bool: 是否具有项目结构标志
        """
        # 必须有main.py作为入口标志
        main_file = path / "main.py"
        if not main_file.is_file():
            return False

        # 必须有app或src目录作为代码目录
        app_dir = path / "app"
        src_dir = path / "src"
        return app_dir.is_dir() or src_dir.is_dir()

    @classmethod
    def _detect_project_layout(cls, root_path: Path) -> str:
        """
        检测项目布局类型（app布局或src布局）

        Args:
            root_path: 项目根目录

        Returns:
            str: 'app' 或 'src'（无对应目录时返回'app'）
        """
        if cls._project_layout is not None:
            return cls._project_layout

        # 优先检查src布局
        src_dir = root_path / "src"
        if src_dir.is_dir():
            cls._project_layout = "src"
        else:
            # 否则默认app布局（即使app目录不存在）
            cls._project_layout = "app"

        logger.debug(f"检测到项目布局: {cls._project_layout}（无对应目录时为默认值）")
        return cls._project_layout

    # ========== 核心对外方法（优化后） ==========
    @classmethod
    def get_source_dir(cls) -> Path:
        """
        获取源代码目录（app或src，核心方法）

        逻辑：
        1. 优先按布局检测src/app目录
        2. 无对应目录时，使用项目根目录兜底并报警告
        3. 不抛异常，保证后续路径逻辑可用

        Returns:
            Path: 源代码目录路径（兜底到根目录）

        Warnings:
            当app/src目录都不存在时，报警告并使用根目录作为源码目录
        """
        root = cls.get_project_root()
        layout = cls._detect_project_layout(root)

        # 按布局获取源码目录
        source_dir = root / ("src" if layout == "src" else "app")

        # 核心优化：不存在时兜底到根目录，报警告不抛异常
        if not source_dir.exists():
            logger.warning(f"⚠️  未找到{layout}目录: {source_dir}，使用项目根目录兜底: {root}")
            source_dir = root

        return source_dir

    @classmethod
    def get_models_dir(cls) -> Path:
        """
        获取models目录路径

        Returns:
            Path: models目录路径（不存在时返回源码目录下的models路径，仅报警告）

        Warnings:
            models目录不存在时，报警告并返回源码目录下的models路径
        """
        return cls._internal_get_subdir("models")

    @classmethod
    def get_app_dir(cls) -> Path:
        """
        获取app目录路径（兼容性方法，等同于get_source_dir）

        Returns:
            Path: app目录路径（兜底到源码目录）

        Warnings:
            无对应目录时报警告，不抛异常
        """
        # 完全复用get_source_dir逻辑，消除方法冗余
        return cls.get_source_dir()

    @classmethod
    def get_project_layout(cls) -> str:
        """
        获取项目布局类型

        Returns:
            str: 'app' 或 'src'（无对应目录时返回'app'）

        Warnings:
            无对应目录时，返回默认值'app'并在_detec中打印debug日志
        """
        root = cls.get_project_root()
        return cls._detect_project_layout(root)

    @classmethod
    def clear_cache(cls):
        """清除路径缓存"""
        cls._project_root_cache = None
        cls._is_container_env = None
        cls._project_layout = None


# 提供便捷的全局函数（补充异常文档）
def get_project_root() -> Path:
    """
    获取项目根目录（便捷函数）

    Returns:
        Path: 项目根目录的Path对象

    Raises:
        FileNotFoundError: 所有路径检测方式失败时抛出
    """
    return PathResolver.get_project_root()


def get_source_dir() -> Path:
    """
    获取源代码目录（便捷函数）

    Returns:
        Path: 源代码目录路径（兜底到根目录）

    Warnings:
        app/src目录不存在时，报警告并使用根目录兜底
    """
    return PathResolver.get_source_dir()


def get_models_dir() -> Path:
    """
    获取models目录（便捷函数）

    Returns:
        Path: models目录路径（不存在时返回源码目录下的路径）

    Warnings:
        models目录不存在时，报警告并返回源码目录下的models路径
    """
    return PathResolver.get_models_dir()


def get_app_dir() -> Path:
    """
    获取app目录（便捷函数，兼容性）

    Returns:
        Path: app目录路径（等同于get_source_dir）

    Warnings:
        无对应目录时报警告，不抛异常
    """
    return PathResolver.get_app_dir()


def get_project_layout() -> str:
    """
    获取项目布局类型（便捷函数）

    Returns:
        str: 'app' 或 'src'（无对应目录时返回'app'）
    """
    return PathResolver.get_project_layout()


def print_project_structure(max_depth: int = 3) -> None:
    """
    打印项目真实目录结构（便捷函数）

    Args:
        max_depth: 打印的最大目录深度，默认3层

    Raises:
        FileNotFoundError: 根目录查找失败时抛出
    """
    return PathResolver.print_project_structure(max_depth)
