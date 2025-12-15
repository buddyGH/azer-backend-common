# azer_common/models/audit/__init__.py
from typing import Type, Dict, Tuple
from azer_common.models.base import BaseModel

# 核心审计注册表（全局唯一）
# 键：动态生成的审计模型类（Type[Model]，如 RolePermissionAudit）
# 值：Tuple[str, list[str]]
#   - 第一个元素：业务类型（str，通常为待审计模型的类名小写下划线形式，如 "role_permission"）
#   - 第二个元素：信号列表（list[str]，如 ["post_save", "post_delete"]，表示该审计模型关联的待审计模型信号）
# 设计目的：
#   1. 维护「审计模型 ↔ 业务类型（待审计模型标识） ↔ 信号列表」的强关联关系
#   2. 保证审计模型全局唯一，避免重复生成/注册
#   3. 快速根据业务类型查找对应的审计模型（用于生成审计日志）
# 使用约束：
#   - 键（审计模型）不可重复，重复注册会抛出异常
#   - 业务类型通常与待审计模型类名一一对应（如 "role_permission" ↔ RolePermission）
_AUDIT_MODEL_REGISTRY: Dict[Type[BaseModel], Tuple[str, list[str]]] = {}


# 路径配置（区分审计模型/待审计模型）
DEFAULT_TARGET_MODEL_MODULE = "models"  # 待审计业务模型的默认路径（如 RolePermission 在 models 下）
DEFAULT_AUDIT_MODEL_MODULE = "models.audit"  # 审计模型自身的默认存放路径
DYNAMIC_AUDIT_MODULE = "azer_common.models.audit.dynamic"  # 动态生成审计模型的存放模块（空文件）

for audit_model_cls in _AUDIT_MODEL_REGISTRY.keys():
    locals()[audit_model_cls.__name__] = audit_model_cls

# 显式指定__all__（可选，增强可读性）
__all__ = [model_cls.__name__ for model_cls in _AUDIT_MODEL_REGISTRY.keys()]
