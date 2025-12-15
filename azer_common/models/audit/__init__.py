# azer_common/models/audit/__init__.py
from typing import Type, Dict, Tuple
from tortoise.models import Model

# 全局审计注册表（唯一来源）
_AUDIT_MODEL_REGISTRY: Dict[Type[Model], Tuple[str, list[str]]] = {}
