import logging
from typing import Type, Dict, Tuple
from tortoise import fields
from tortoise.models import Model
from tortoise.signals import post_delete, post_save
from azer_common.models.audit.base import BaseAuditLog
from azer_common.models.audit.signals import _generic_audit_signal_handler
from azer_common.utils.validators import validate_model_business_type
from azer_common.models.audit import DEFAULT_TARGET_MODEL_MODULE, DYNAMIC_AUDIT_MODULE


logger = logging.getLogger(__name__)

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
_AUDIT_MODEL_REGISTRY: Dict[Type[Model], Tuple[str, list[str]]] = {}


# 信号映射（复用自动/手动注册逻辑，绑定到待审计模型）
_SIGNAL_MAP = {
    "post_save": post_save,
    "post_delete": post_delete,
}


def register_audit(business_type: str, signals: list[str] = ["post_save"]):
    """
    【自动注册】业务模型审计装饰器
    为待审计模型自动生成审计模型 + 绑定信号 + 写入核心注册表
    用法：
    @register_audit(business_type="role_permission")  # business_type通常=待审计模型类名小写下划线
    class RolePermission(Model): ...
    """
    validate_model_business_type(business_type)

    def decorator(target_model_cls: Type[Model]) -> Type[Model]:
        """
        装饰器逻辑：
        :param target_model_cls: 待审计的业务模型类（如 RolePermission）
        :return: 原待审计模型类（无修改）
        """
        # 基础校验：待审计模型类型合法
        if not issubclass(target_model_cls, Model):
            raise TypeError(f"仅支持Tortoise Model类型，当前待审计模型类型：{type(target_model_cls)}")

        # 优化：先检查业务类型是否已注册（避免无效生成审计模型）
        if _is_business_type_registered(business_type):
            existing_audit_model = _get_audit_model_by_business_type(business_type)
            raise ValueError(f"业务类型[{business_type}]已绑定审计模型[{existing_audit_model.__name__}]，禁止重复注册")

        # 1. 自动生成审计模型（仅当业务类型未注册时生成）
        audit_model_cls = _create_audit_model(business_type, target_model_cls)

        # 2. 为待审计模型绑定信号（信号由待审计模型操作触发，关联审计逻辑）
        _bind_audit_signals(target_model_cls, business_type, signals)

        # 3. 写入核心注册表：审计模型 → (业务类型, 信号列表)
        _AUDIT_MODEL_REGISTRY[audit_model_cls] = (business_type, signals)
        logger.info(
            f"[自动注册] 审计模型[{audit_model_cls.__name__}]注册完成 "
            f"(待审计模型：{target_model_cls.__name__}，业务类型：{business_type}，信号：{signals})"
        )

        # 返回原待审计模型类，不改变其原有功能
        return target_model_cls

    return decorator


def register_audit_manual(target_model: Type[Model], business_type: str, signals: list[str] = ["post_save"]):
    """
    【手动注册】审计模型接口（适配特殊场景：无法用装饰器的待审计模型）
    逻辑与自动注册完全一致，复用底层生成/绑定逻辑
    用法：
    register_audit_manual(
        target_model=SpecialModel,  # 待审计的业务模型类
        business_type="special_model",  # 业务类型（通常=待审计模型类名小写下划线）
        signals=["post_save", "post_delete"]
    )
    """
    # 1. 统一参数验证
    validate_model_business_type(business_type)
    if not issubclass(target_model, Model):
        raise TypeError(f"仅支持Tortoise Model类型，当前待审计模型类型：{type(target_model)}")

    # 优化：先检查业务类型是否已注册（避免无效生成审计模型）
    if _is_business_type_registered(business_type):
        existing_audit_model = _get_audit_model_by_business_type(business_type)
        raise ValueError(f"业务类型[{business_type}]已绑定审计模型[{existing_audit_model.__name__}]，禁止重复注册")

    # 2. 生成审计模型（仅当业务类型未注册时生成）
    audit_model_cls = _create_audit_model(business_type, target_model)

    # 3. 为待审计模型绑定信号
    _bind_audit_signals(target_model, business_type, signals)

    # 4. 写入核心注册表
    _AUDIT_MODEL_REGISTRY[audit_model_cls] = (business_type, signals)
    logger.info(
        f"[手动注册] 审计模型[{audit_model_cls.__name__}]注册完成 "
        f"(待审计模型：{target_model.__name__}，业务类型：{business_type}，信号：{signals})"
    )


def _create_audit_model(business_type: str, target_model: Type[Model]) -> Type[BaseAuditLog]:
    """
    底层：动态生成审计模型（修正外键路径）
    :param business_type: 业务类型（待审计模型类名小写下划线）
    :param target_model: 待审计的业务模型类
    :return: 动态生成的审计模型类（如 RolePermissionAudit）
    """
    # 生成审计模型类名：snake_case → CamelCase + Audit（如 role_permission → RolePermissionAudit）
    audit_class_name = "".join(word.capitalize() for word in business_type.split("_")) + "Audit"
    # 生成审计表名：azer_业务类型_audit（如 azer_role_permission_audit）
    audit_table_name = f"azer_{business_type}_audit"
    # 外键字段名：与业务类型一致（如 role_permission）
    fk_field_name = business_type

    # 修正：获取待审计模型的实际模块路径（优先用模型自身模块，无则用默认路径）
    target_model_module = (
        target_model.__module__ if target_model.__module__ != "__main__" else DEFAULT_TARGET_MODEL_MODULE
    )
    # 待审计模型的完整路径（如 "models.role.RolePermission" 或 "models.RolePermission"）
    target_model_full_path = f"{target_model_module}.{target_model.__name__}"

    # 动态构建审计模型属性（修正外键关联路径）
    audit_model_attrs = {
        "__module__": DYNAMIC_AUDIT_MODULE,  # 动态审计模型存放路径
        "__doc__": f"{target_model.__name__}审计日志表（动态生成）",
        fk_field_name: fields.ForeignKeyField(
            target_model_full_path,  # 如 "models.RolePermission"
            related_name="audit_logs",  # 待审计模型可通过该属性反向查审计日志
            on_delete=fields.SET_NULL,
            null=True,
        ),
        "Meta": type(
            "Meta",
            (),
            {
                "table": audit_table_name,
                "table_description": f"{target_model.__name__}业务操作审计日志表",
                "indexes": BaseAuditLog.Meta.indexes + [(fk_field_name, "operated_at")],  # 联合索引优化查询
            },
        ),
    }

    # 动态创建审计模型类（继承BaseAuditLog）
    audit_model_cls = type(audit_class_name, (BaseAuditLog,), audit_model_attrs)
    logger.debug(
        f"动态生成审计模型：{audit_class_name} " f"(表名：{audit_table_name}，关联待审计模型：{target_model_full_path})"
    )
    return audit_model_cls


def _bind_audit_signals(target_model: Type[Model], business_type: str, signals: list[str]):
    """
    底层：为待审计模型绑定审计信号（自动/手动注册复用）
    注：信号绑定到「待审计模型」（操作触发方），而非审计模型
    """
    for signal_name in signals:
        # 映射信号常量（如 "post_save" → post_save 信号对象）
        signal = _SIGNAL_MAP.get(signal_name)
        if not signal:
            logger.warning(
                f"待审计模型[{target_model.__name__}]跳过不支持的信号类型：{signal_name} "
                f"(业务类型：{business_type})"
            )
            continue

        # 绑定信号处理函数（触发信号时生成审计日志）
        signal(target_model)(_generic_audit_signal_handler)
        logger.info(f"待审计模型[{target_model.__name__}]已绑定{signal_name}审计信号 " f"(业务类型：{business_type})")


def get_audit_model(business_type: str) -> Type[BaseAuditLog]:
    """
    核心查询接口：根据业务类型查找对应的审计模型（适配信号处理逻辑）
    :param business_type: 业务类型（待审计模型类名小写下划线，如 "role_permission"）
    :return: 动态生成的审计模型类（如 RolePermissionAudit）
    :raise ValueError: 未找到对应审计模型（未注册）
    """
    target_audit_model = _get_audit_model_by_business_type(business_type)
    if not target_audit_model:
        raise ValueError(
            f"未找到业务类型[{business_type}]对应的审计模型！"
            f"请确认已通过 @register_audit 或 register_audit_manual 完成注册"
        )

    logger.debug(f"根据业务类型[{business_type}]找到审计模型：{target_audit_model.__name__}")
    return target_audit_model


# ---------------- 内部辅助函数 ----------------
def _is_business_type_registered(business_type: str) -> bool:
    """
    内部辅助：检查业务类型是否已注册（避免重复生成审计模型）
    :return: True=已注册，False=未注册
    """
    for _, (bt, _) in _AUDIT_MODEL_REGISTRY.items():
        if bt == business_type:
            return True
    return False


def _get_audit_model_by_business_type(business_type: str) -> Type[Model] | None:
    """
    内部辅助：根据业务类型查找已注册的审计模型
    :return: 审计模型类 / None（未找到）
    """
    for audit_model_cls, (bt, _) in _AUDIT_MODEL_REGISTRY.items():
        if bt == business_type:
            return audit_model_cls
    return None
