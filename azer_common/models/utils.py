# azer_common/models/utils.py
import importlib
import pkgutil
from typing import List, Tuple, Type
from pathlib import Path

from tortoise.models import Model
from azer_common.models.audit.registry import _AUDIT_MODEL_REGISTRY

# 无需导入的文件/目录（全局排除规则）
EXCLUDE_FILES = {"base.py", "registry.py", "signals.py", "__init__.py", "utils.py"}
EXCLUDE_DIRS = {"__pycache__", "dynamic", "manual"}  # dynamic单独处理


def collect_all_static_models(base_module: str = "azer_common.models", exclude_modules: List[str] = None) -> List[str]:
    """
    收集所有静态编写的模型（排除base/registry等非模型文件）
    :param base_module: 模型根模块（如 "azer_common.models"）
    :param exclude_modules: 排除的子模块（如 ["audit.dynamic"]）
    :return: 可导入的模型路径列表（如 ["azer_common.models.user.model.User"]）
    """
    if exclude_modules is None:
        exclude_modules = []

    model_paths = []
    base_path = Path(importlib.import_module(base_module).__file__).parent

    # 遍历所有子模块
    for item in pkgutil.walk_packages([str(base_path)], prefix=f"{base_module}."):
        module_name = item.name
        # 排除指定模块
        if any(excl in module_name for excl in exclude_modules):
            continue

        # 导入模块并筛选模型类
        try:
            module = importlib.import_module(module_name)
            # 排除非模型文件
            if Path(module.__file__).name in EXCLUDE_FILES:
                continue

            # 收集模块内的Model子类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Model)
                    and attr.__module__ == module_name
                    and not attr.__name__.startswith("Base")  # 排除基类
                ):
                    model_paths.append(f"{module_name}.{attr_name}")
        except ImportError:
            continue

    return model_paths


def collect_dynamic_audit_models() -> List[str]:
    """
    收集所有动态生成的审计模型（供Tortoise导入）
    :return: 动态审计模型的导入路径列表（如 ["azer_common.models.audit.dynamic.RolePermissionAudit"]）
    """
    dynamic_module = "azer_common.models.audit.dynamic"
    return [f"{dynamic_module}.{model_cls.__name__}" for model_cls in _AUDIT_MODEL_REGISTRY.keys()]


def get_tortoise_model_list(base_module: str = "azer_common.models", include_dynamic_audit: bool = True) -> List[str]:
    """
    获取完整的Tortoise模型导入列表（静态模型 + 动态审计模型）
    :param base_module: 模型根模块
    :param include_dynamic_audit: 是否包含动态审计模型
    :return: 适配tortoise_config的models列表
    """
    # 收集静态模型（排除audit.dynamic）
    static_models = collect_all_static_models(base_module=base_module, exclude_modules=["audit.dynamic"])

    # 可选：添加动态审计模型
    if include_dynamic_audit:
        static_models.extend(collect_dynamic_audit_models())

    return static_models


def register_audit_models_to_tortoise():
    """
    注册动态审计模型到Tortoise（确保ORM能识别）
    需在Tortoise.init()前调用
    """
    from tortoise import Tortoise

    dynamic_module = importlib.import_module("azer_common.models.audit.dynamic")

    # 将动态审计模型注册到Tortoise的模型注册表
    for audit_model_cls in _AUDIT_MODEL_REGISTRY.keys():
        # 绑定模块（确保Tortoise识别）
        audit_model_cls.__module__ = dynamic_module.__name__
        # 注册到Tortoise
        Tortoise.register_model(audit_model_cls)

    logger.info(f"已注册{len(_AUDIT_MODEL_REGISTRY)}个动态审计模型到Tortoise")
