import re
from typing import List, Optional, Union

from azer_common.models.base import BaseModel
from tortoise import fields
from tortoise.expressions import Q

from azer_common.utils.validators import validate_permission_code


class Permission(BaseModel):
    # 权限标识
    code = fields.CharField(
        max_length=100,
        validators=[validate_permission_code],
        description='权限代码（租户内唯一标识），如：user:read, article:delete'
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

    roles = fields.ManyToManyField(
        'models.Role',
        through='azer_role_permission',
        related_name='permissions',
        description='拥有该权限的角色',
    )

    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='permissions_list',
        null=True,  # null=全局权限，所有租户可用
        on_delete=fields.RESTRICT,
        description='所属租户（null表示全局权限）'
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
    is_enabled = fields.BooleanField(
        default=True,
        description='是否启用'
    )
    is_system = fields.BooleanField(
        default=False,
        description='是否系统内置权限'
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
            ("code", "is_enabled", "tenant_id"),  # 优化：核心查询索引
            ("tenant_id", "category", "is_enabled"),  # 新增：按租户+分类查询
        ]
        unique_together = ("code", "tenant_id", "is_deleted")  # 租户+编码+未删除 唯一

    def __str__(self):
        """优化：处理tenant未加载的边界情况，统一租户ID类型"""
        try:
            # 优先用tenant_id（无需加载关联），兼容tenant未加载场景
            tenant_id = self.tenant_id
            tenant_info = "[全局]" if tenant_id is None else f"[租户:{tenant_id}]"
        except Exception:
            tenant_info = "[租户:未知]"
        return f"{tenant_info} {self.code}: {self.name}"

    async def save(self, *args, **kwargs):
        """保存前验证"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证权限数据（强化逻辑+类型校验）"""
        # 1. 系统权限必须是全局权限（tenant_id为null）
        if self.is_system and self.tenant_id is not None:
            raise ValueError("系统内置权限必须为全局权限（tenant_id需为空）")

        # 2. 代码格式验证（强化正则）
        if not re.match(r'^[a-z_][a-z0-9_:]{0,99}$', self.code):
            raise ValueError(
                "权限代码必须为小写字母、数字、下划线和冒号，"
                "以字母或下划线开头，长度不超过100个字符"
            )

        # 3. 唯一性验证（排除软删除的，区分全局/租户）
        query = self.__class__.objects.filter(
            code=self.code,
            is_deleted=False  # 补充：排除软删除的记录
        )
        # 区分全局/租户：tenant_id 相同 或 都为 null
        if self.tenant_id is None:
            query = query.filter(tenant_id__isnull=True)
        else:
            query = query.filter(tenant_id=self.tenant_id)

        # 排除自身（更新场景）
        if self.id:
            query = query.exclude(id=self.id)

        existing = await query.first()
        if existing:
            tenant_desc = "全局" if existing.tenant_id is None else f"租户 {existing.tenant_id}"
            raise ValueError(f"{tenant_desc}下已存在相同权限代码: {self.code}")

    # ========== 供 RolePermission 调用的核心类方法（优化租户逻辑+类型） ==========
    @classmethod
    async def get_permission_by_code(
            cls,
            code: str,
            tenant_id: Optional[int] = None,  # 修正：改为int（匹配ForeignKey生成的字段类型）
            check_enabled: bool = True
    ) -> Optional['Permission']:
        """
        根据编码+租户查询权限（适配 RolePermission 权限校验）
        :param code: 权限编码
        :param tenant_id: 租户ID（None=查询全局权限）
        :param check_enabled: 是否仅查询启用的权限
        """
        query = cls.objects.filter(
            code=code,
            is_deleted=False  # 补充：排除软删除
        )
        # 租户过滤：全局/指定租户
        if tenant_id is None:
            query = query.filter(tenant_id__isnull=True)
        else:
            query = query.filter(tenant_id=tenant_id)

        # 启用状态过滤
        if check_enabled:
            query = query.filter(is_enabled=True)

        return await query.first()

    @classmethod
    async def bulk_get_permissions(
            cls,
            permission_ids: List[int],
            tenant_id: Optional[int] = None,  # 修正：改为int
            check_enabled: bool = True
    ) -> List['Permission']:
        """
        批量查询权限（供 RolePermission 批量授予时校验）
        :param permission_ids: 权限ID列表
        :param tenant_id: 租户ID（None=允许全局权限）
        :param check_enabled: 是否仅查询启用的权限
        """
        if not permission_ids:
            return []

        query = cls.objects.filter(
            id__in=permission_ids,
            is_deleted=False  # 补充：排除软删除
        )
        # ========== 关键修正：租户过滤条件（使用Q对象） ==========
        if tenant_id is not None:
            # 允许：权限属于指定租户 OR 权限是全局权限（tenant_id=null）
            query = query.filter(
                Q(tenant_id=tenant_id) | Q(tenant_id__isnull=True)
            )

        # 启用状态过滤
        if check_enabled:
            query = query.filter(is_enabled=True)

        return await query.all()

    @classmethod
    async def check_tenant_consistency(
            cls,
            permission: Union[int, str, 'Permission'],
            target_tenant_id: Optional[int]  # 修正：改为int
    ) -> bool:
        """
        校验权限与目标租户的一致性（供 RolePermission 租户校验）
        :param permission: 权限ID/编码/实例
        :param target_tenant_id: 目标租户ID（如角色的租户ID）
        :return: 一致返回True，否则False
        """
        # 解析权限实例
        if isinstance(permission, int):
            perm = await cls.objects.filter(id=permission, is_deleted=False).first()
        elif isinstance(permission, str):
            perm = await cls.get_permission_by_code(permission, target_tenant_id)
        else:
            perm = permission

        if not perm:
            return False

        # 逻辑优化：全局权限适配所有租户；非全局权限必须与目标租户一致
        if perm.tenant_id is None:
            return True
        return perm.tenant_id == target_tenant_id

    @classmethod
    async def validate_permission_tenant(
            cls,
            permission: Union[int, 'Permission'],
            role_tenant_id: Optional[int]  # 修正：改为int
    ) -> 'Permission':
        """
        校验权限与角色的租户一致性（失败抛异常，成功返回权限实例）
        :raise ValueError: 租户不匹配/权限不存在/权限禁用/软删除
        """
        # 解析权限ID
        perm_id = permission.id if hasattr(permission, 'id') else permission

        # 补充：查询时过滤软删除+禁用状态
        perm = await cls.objects.filter(
            id=perm_id,
            is_deleted=False
        ).first()

        if not perm:
            raise ValueError(f"权限不存在或已删除（ID: {perm_id}）")

        # 补充：校验权限是否启用
        if not perm.is_enabled:
            raise ValueError(f"权限已禁用（ID: {perm_id}，编码: {perm.code}）")

        # 全局权限无需校验；非全局权限必须与角色租户一致
        if perm.tenant_id is not None:
            if role_tenant_id is None:
                raise ValueError(
                    f"租户权限（ID: {perm_id}，租户:{perm.tenant_id}）不能分配给全局角色"
                )
            if role_tenant_id != perm.tenant_id:
                raise ValueError(
                    f"权限（租户:{perm.tenant_id}）与角色（租户:{role_tenant_id}）租户不匹配"
                )

        return perm