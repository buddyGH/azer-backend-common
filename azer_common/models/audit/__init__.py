# azer_common/models/audit/__init__.py
from .registry import _AUDIT_REGISTRY

for _, audit_model_cls, _ in _AUDIT_REGISTRY.values():
    locals()[audit_model_cls.__name__] = audit_model_cls

__all__ = [audit_model_cls.__name__ for _, audit_model_cls, _ in _AUDIT_REGISTRY.values()]
