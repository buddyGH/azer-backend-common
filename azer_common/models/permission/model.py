from azer_common.models.base import BaseModel
from tortoise import fields

from azer_common.utils.validators import validate_permission_code


class Permission(BaseModel):
    # 权限标识
    code = fields.CharField(
        max_length=100,
        unique=True,
        validators=[validate_permission_code],
        description='权限代码（唯一标识），如：user:read, article:delete'
    )
    name = fields.CharField(
        max_length=50,
        description='权限显示名称'
    )
    description = fields.CharField(
        max_length=200,
        null=True,
        description='权限详细描述'
    )

    # 权限分类
    category = fields.CharField(
        max_length=50,
        default='general',
        description='权限分类，如：system, user, content, finance'
    )
    module = fields.CharField(
        max_length=50,
        null=True,
        description='所属模块'
    )

    # 权限元数据
    action = fields.CharField(
        max_length=20,
        description='操作类型：read, write, delete, manage'
    )
    resource_type = fields.CharField(
        max_length=50,
        description='资源类型'
    )
    resource_id = fields.CharField(
        max_length=100,
        null=True,
        description='特定资源ID（为空表示所有资源）'
    )

    # 状态控制
    is_active = fields.BooleanField(
        default=True,
        description='是否启用'
    )
    is_system = fields.BooleanField(
        default=False,
        description='是否系统内置权限'
    )

    # 审计字段
    created_by = fields.ForeignKeyField(
        'models.User',
        null=True,
        on_delete=fields.SET_NULL,
        description='创建者'
    )
    metadata = fields.JSONField(
        null=True,
        description='扩展元数据'
    )

    class Meta:
        table = "azer_permission"
        table_description = '权限定义表'
        indexes = [
            ("category", "module"),
            ("resource_type", "action"),
            ("code", "is_active"),
        ]

    def __str__(self):
        return f"{self.code}: {self.name}"
