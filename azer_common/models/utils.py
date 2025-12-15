# azer_common/models/utils.py
import logging
import importlib
import pkgutil
from typing import List, Optional, Set
from pathlib import Path
from tortoise.models import Model
from azer_common.models.types.constants import DYNAMIC_AUDIT_MODULE
from azer_common.models.audit.registry import _AUDIT_REGISTRY

logger = logging.getLogger(__name__)

# 公共包默认排除规则（排除非模型文件/目录，微服务可追加/覆盖）
DEFAULT_EXCLUDE_FILES = {
    "__init__.py",
    "enums.py",
    "signals.py",
    "utils.py",
    "context.py",
    "registry.py",
}
DEFAULT_EXCLUDE_DIRS = {"__pycache__", "dynamic", "manual", "types", "utils"}  # dynamic单独处理


def collect_all_static_models(
    base_module: str,
    custom_exclude_files: Optional[Set[str]] = None,
    custom_exclude_dirs: Optional[Set[str]] = None,
    exclude_modules: Optional[List[str]] = None,
) -> List[str]:
    """
    【通用】收集指定根模块下所有包含静态模型的模块路径（适配Tortoise配置）
    :param base_module: 微服务的模型根模块（如 "my_service.models" 或 "azer_common.models"）
    :param custom_exclude_files: 微服务自定义排除的文件（追加到默认规则），如 {"test_model.py"}
    :param custom_exclude_dirs: 微服务自定义排除的目录（追加到默认规则），如 {"tests"}
    :param exclude_modules: 微服务自定义排除的子模块（如 ["my_service.models.tests"]）
    :return: 可导入的模型模块路径列表（如 ["my_service.models.user.model"]）
    """
    # 合并默认排除项 + 自定义排除项
    exclude_files = DEFAULT_EXCLUDE_FILES.copy()
    if custom_exclude_files:
        exclude_files.update(custom_exclude_files)

    exclude_dirs = DEFAULT_EXCLUDE_DIRS.copy()
    if custom_exclude_dirs:
        exclude_dirs.update(custom_exclude_dirs)

    if exclude_modules is None:
        exclude_modules = []

    # 收集模块路径（去重）
    model_module_paths = set()
    try:
        # 导入根模块并获取物理路径（适配任意模块）
        root_module = importlib.import_module(base_module)
        root_path = Path(root_module.__file__).parent
    except ImportError as e:
        logger.error(f"导入模型根模块失败：{base_module}，错误：{e}")
        return []

    # 遍历根模块下所有子模块（递归）
    for item in pkgutil.walk_packages([str(root_path)], prefix=f"{base_module}."):
        module_name = item.name
        # 排除指定子模块
        if any(excl in module_name for excl in exclude_modules):
            continue

        try:
            # 导入当前子模块
            sub_module = importlib.import_module(module_name)
            sub_module_path = Path(sub_module.__file__)

            # 排除规则：非.py文件 / 排除列表内的文件 / 排除列表内的目录
            if sub_module_path.suffix != ".py":
                continue
            if sub_module_path.name in exclude_files:
                continue
            if any(dir_name in sub_module_path.parts for dir_name in exclude_dirs):
                continue

            # 检查模块内是否包含Tortoise Model子类（排除基类/非模型）
            has_valid_model = False
            for attr_name in dir(sub_module):
                attr = getattr(sub_module, attr_name)
                if (
                    isinstance(attr, type)  # 是类
                    and issubclass(attr, Model)  # 继承Tortoise Model
                    and attr.__module__ == module_name  # 属于当前模块（排除导入的模型）
                    and not attr.__name__.startswith("Base")  # 排除基类（如BaseModel）
                ):
                    has_valid_model = True
                    break

            # 仅收集包含有效模型的模块路径
            if has_valid_model:
                model_module_paths.add(module_name)
                logger.debug(f"收集到静态模型模块：{module_name}")

        except ImportError as e:
            logger.warning(f"导入子模块失败：{module_name}，错误：{e}，跳过")
            continue

    # 转列表并返回
    unique_module_paths = list(model_module_paths)
    logger.info(f"从模块[{base_module}]收集到{len(unique_module_paths)}个包含静态模型的模块")
    return unique_module_paths


def collect_dynamic_audit_models() -> List[str]:
    """
    【通用】收集公共包中动态审计模型所在的模块路径（适配Tortoise配置）
    :return: 动态审计模型的模块路径列表（如 ["azer_common.models.audit.dynamic"]）
    """
    # 前置检查：确保动态模型已绑定到模块
    if _AUDIT_REGISTRY:  # 新注册表非空时检查
        dynamic_module = importlib.import_module(DYNAMIC_AUDIT_MODULE)
        # 验证模型是否在模块中（日志排查）
        module_attrs = dir(dynamic_module)
        missing_models = []

        for _, audit_model_cls, _ in _AUDIT_REGISTRY.values():
            if audit_model_cls.__name__ not in module_attrs:
                missing_models.append(audit_model_cls.__name__)
        if missing_models:
            logger.warning(f"动态模型未添加到模块[{DYNAMIC_AUDIT_MODULE}]：{missing_models}")

    logger.info(f"收集到动态审计模型模块：{DYNAMIC_AUDIT_MODULE}（包含{len(_AUDIT_REGISTRY)}个动态审计模型）")
    return [DYNAMIC_AUDIT_MODULE]


def get_tortoise_model_list(
    base_module: str,
    include_dynamic_audit: bool = True,
    custom_exclude_files: Optional[Set[str]] = None,
    custom_exclude_dirs: Optional[Set[str]] = None,
    exclude_modules: Optional[List[str]] = None,
) -> List[str]:
    """
    【通用】获取完整的Tortoise模型模块列表（静态模型模块 + 动态审计模型模块）
    微服务直接调用该函数即可生成Tortoise config所需的models列表
    :param base_module: 微服务模型根模块（如 "my_service.models"）
    :param include_dynamic_audit: 是否包含公共包的动态审计模型模块
    :param custom_exclude_files: 微服务自定义排除文件
    :param custom_exclude_dirs: 微服务自定义排除目录
    :param exclude_modules: 微服务自定义排除子模块
    :return: 适配Tortoise config的models模块列表
    """
    # 1. 收集微服务静态模型模块
    static_model_modules = collect_all_static_models(
        base_module=base_module,
        custom_exclude_files=custom_exclude_files,
        custom_exclude_dirs=custom_exclude_dirs,
        exclude_modules=exclude_modules,
    )

    # 2. 追加公共包动态审计模型模块（可选）
    if include_dynamic_audit:
        dynamic_audit_module = collect_dynamic_audit_models()
        static_model_modules.extend(dynamic_audit_module)

    # 去重（防止重复添加模块）
    unique_model_modules = list(set(static_model_modules))
    logger.info(f"生成完整Tortoise模型模块列表，共{len(unique_model_modules)}个模块")
    return unique_model_modules + ["aerich.models"]
