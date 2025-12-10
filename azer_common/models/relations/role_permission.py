# azer_common/models/relations/role_permission.py
from datetime import datetime
from typing import Any, Dict, List, Optional

from tortoise.expressions import Q

from azer_common.models.base import BaseModel
from tortoise import fields

from azer_common.utils.time import utc_now


class RolePermission(BaseModel):
    role = fields.ForeignKeyField(
        'models.Role',
        related_name='role_permissions',
        description='角色',
        on_delete=fields.CASCADE
    )
    permission = fields.ForeignKeyField(
        'models.Permission',
        related_name='permission_roles',
        description='权限',
        on_delete=fields.CASCADE
    )

    # 授予信息
    granted_by = fields.ForeignKeyField(
        'models.User',
        null=True,
        on_delete=fields.SET_NULL,
        related_name='granted_role_permissions',
        description='授予者'
    )
    granted_at = fields.DatetimeField(
        default=utc_now,
        description='授予时间'
    )

    # 状态控制
    is_active = fields.BooleanField(
        default=True,
        description='是否有效'
    )
    revoked_at = fields.DatetimeField(
        null=True,
        description='撤销时间'
    )
    revoked_by = fields.ForeignKeyField(
        'models.User',
        null=True,
        related_name='revoked_role_permissions',
        on_delete=fields.SET_NULL,
        description='撤销者'
    )

    # 生效时间控制
    effective_from = fields.DatetimeField(
        null=True,
        description='生效开始时间'
    )
    effective_to = fields.DatetimeField(
        null=True,
        description='生效结束时间'
    )

    # 审计字段
    reason = fields.CharField(
        max_length=200,
        null=True,
        description='授予/撤销原因'
    )
    metadata = fields.JSONField(
        null=True,
        description='扩展元数据'
    )

    class Meta:
        table = "azer_role_permission"
        table_description = '角色权限关联表'
        unique_together = ("role", "permission", "is_active")
        indexes = [
            ("role", "is_active", "effective_to"),
            ("permission", "is_active", "effective_to"),
            ("granted_by", "granted_at"),
            ("effective_from", "effective_to", "is_active"),
        ]

    def is_effective(self, check_time: datetime = None) -> bool:
        """
        检查权限是否在有效期内

        Args:
            check_time: 检查的时间点，默认为当前时间

        Returns:
            bool: 是否有效
        """
        if not self.is_active:
            return False

        if self.revoked_at:
            return False

        now = check_time or utc_now()

        # 检查生效开始时间
        if self.effective_from and now < self.effective_from:
            return False

        # 检查生效结束时间
        if self.effective_to and now >= self.effective_to:
            return False

        return True

    async def revoke(
            self,
            revoked_by=None,
            reason: str = None,
            **kwargs
    ) -> None:
        """
        撤销角色权限

        Args:
            revoked_by: 撤销者
            reason: 撤销原因
            **kwargs: 其他保存参数
        """
        self.is_active = False
        self.revoked_at = utc_now()
        self.revoked_by = revoked_by

        if reason:
            self.reason = reason

        await self.save(**kwargs)

    async def update_effective_period(
            self,
            effective_from: datetime = None,
            effective_to: datetime = None,
            **kwargs
    ) -> None:
        """
        更新权限生效时间段

        Args:
            effective_from: 新的生效开始时间
            effective_to: 新的生效结束时间
            **kwargs: 其他保存参数
        """
        if effective_from is not None:
            self.effective_from = effective_from

        if effective_to is not None:
            self.effective_to = effective_to

        await self.save(**kwargs)

    async def activate(self, **kwargs) -> None:
        """
        重新激活已撤销的权限

        Args:
            **kwargs: 其他保存参数
        """
        if not self.is_active:
            self.is_active = True
            self.revoked_at = None
            self.revoked_by = None
            await self.save(**kwargs)

    async def to_dict(self, include_related: bool = False) -> Dict[str, Any]:
        """
        转换为字典格式

        Args:
            include_related: 是否包含关联对象信息

        Returns:
            Dict: 权限信息字典
        """
        result = {
            'id': self.id,
            'role_id': self.role_id,
            'permission_id': self.permission_id,
            'granted_by_id': self.granted_by_id,
            'granted_at': self.granted_at,
            'is_active': self.is_active,
            'revoked_at': self.revoked_at,
            'revoked_by_id': self.revoked_by_id,
            'effective_from': self.effective_from,
            'effective_to': self.effective_to,
            'reason': self.reason,
            'metadata': self.metadata,
            'is_effective': self.is_effective(),
        }

        if include_related:
            # 加载关联对象
            await self.fetch_related('role', 'permission', 'granted_by', 'revoked_by')

            if self.role:
                result['role'] = {
                    'id': self.role.id,
                    'name': self.role.name,
                    'code': getattr(self.role, 'code', None),
                }

            if self.permission:
                result['permission'] = {
                    'id': self.permission.id,
                    'code': self.permission.code,
                    'name': self.permission.name,
                    'action': self.permission.action,
                    'resource_type': self.permission.resource_type,
                }

            if self.granted_by:
                result['granted_by'] = {
                    'id': self.granted_by.id,
                    'username': self.granted_by.username,
                    'full_name': self.granted_by.full_name,
                }

            if self.revoked_by:
                result['revoked_by'] = {
                    'id': self.revoked_by.id,
                    'username': self.revoked_by.username,
                    'full_name': self.revoked_by.full_name,
                }

        return result

    # ========== 类方法 ==========

    @classmethod
    async def grant(
            cls,
            role,
            permission,
            granted_by=None,
            effective_from: datetime = None,
            effective_to: datetime = None,
            reason: str = None,
            metadata: Dict = None,
            **kwargs
    ) -> 'RolePermission':
        """
        授予角色权限（工厂方法）

        Args:
            role: 角色实例或ID
            permission: 权限实例或ID
            granted_by: 授予者
            effective_from: 生效开始时间
            effective_to: 生效结束时间
            reason: 授予原因
            metadata: 元数据
            **kwargs: 其他创建参数

        Returns:
            RolePermission: 新创建的权限关联实例

        Raises:
            ValueError: 如果已存在有效的相同权限关联
        """
        role_id = role.id if hasattr(role, 'id') else role
        permission_id = permission.id if hasattr(permission, 'id') else permission

        # 检查是否已存在有效的权限关联
        existing = await cls.filter(
            role_id=role_id,
            permission_id=permission_id,
            is_active=True,
            revoked_at__isnull=True
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=utc_now())
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=utc_now())
        ).first()

        if existing:
            raise ValueError(f"角色已拥有该有效权限（ID: {existing.id}）")

        # 创建新的权限关联
        role_permission = cls(
            role_id=role_id,
            permission_id=permission_id,
            granted_by=granted_by,
            effective_from=effective_from,
            effective_to=effective_to,
            reason=reason,
            metadata=metadata,
            **kwargs
        )

        await role_permission.save()
        return role_permission

    @classmethod
    async def bulk_grant(
            cls,
            role,
            permissions: List,
            granted_by=None,
            effective_from: datetime = None,
            effective_to: datetime = None,
            reason: str = None,
            metadata: Dict = None,
    ) -> List['RolePermission']:
        """
        批量授予权限

        Args:
            role: 角色实例或ID
            permissions: 权限实例或ID列表
            granted_by: 授予者
            effective_from: 生效开始时间
            effective_to: 生效结束时间
            reason: 授予原因
            metadata: 元数据

        Returns:
            List[RolePermission]: 新创建的权限关联列表
        """
        role_id = role.id if hasattr(role, 'id') else role
        results = []

        for permission in permissions:
            try:
                role_perm = await cls.grant(
                    role=role_id,
                    permission=permission,
                    granted_by=granted_by,
                    effective_from=effective_from,
                    effective_to=effective_to,
                    reason=reason,
                    metadata=metadata,
                )
                results.append(role_perm)
            except ValueError as e:
                # 跳过已存在的权限，继续处理其他权限
                continue

        return results

    @classmethod
    async def get_effective_permissions(
            cls,
            role_id: int,
            check_time: datetime = None,
            include_inactive_role: bool = False,
    ) -> List['RolePermission']:
        """
        获取角色在指定时间点的有效权限

        Args:
            role_id: 角色ID
            check_time: 检查的时间点，默认为当前时间
            include_inactive_role: 是否包含非激活角色的权限

        Returns:
            List[RolePermission]: 有效的权限关联列表
        """
        check_time = check_time or utc_now()

        query = cls.filter(
            role_id=role_id,
            is_active=True,
            revoked_at__isnull=True,
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=check_time)
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=check_time)
        )

        # 如果不需要非激活角色的权限，可以进一步过滤
        if not include_inactive_role:
            query = query.filter(role__is_active=True)

        return await query.prefetch_related('permission')

    @classmethod
    async def has_permission(
            cls,
            role_id: int,
            permission_code: str,
            check_time: datetime = None,
    ) -> bool:
        """
        检查角色是否拥有指定权限

        Args:
            role_id: 角色ID
            permission_code: 权限代码
            check_time: 检查的时间点

        Returns:
            bool: 是否拥有该权限
        """
        check_time = check_time or utc_now()

        count = await cls.filter(
            role_id=role_id,
            permission__code=permission_code,
            is_active=True,
            revoked_at__isnull=True,
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=check_time)
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=check_time)
        ).count()

        return count > 0

    @classmethod
    async def find_by_role_and_permission(
            cls,
            role_id: int,
            permission_id: int,
            include_inactive: bool = False,
    ) -> Optional['RolePermission']:
        """
        根据角色ID和权限ID查找权限关联

        Args:
            role_id: 角色ID
            permission_id: 权限ID
            include_inactive: 是否包含非激活的关联

        Returns:
            Optional[RolePermission]: 找到的权限关联或None
        """
        query = cls.filter(role_id=role_id, permission_id=permission_id)

        if not include_inactive:
            query = query.filter(is_active=True, revoked_at__isnull=True)

        return await query.first()

    @classmethod
    async def revoke_by_ids(
            cls,
            role_permission_ids: List[int],
            revoked_by=None,
            reason: str = None,
    ) -> int:
        """
        批量撤销权限关联

        Args:
            role_permission_ids: 权限关联ID列表
            revoked_by: 撤销者
            reason: 撤销原因

        Returns:
            int: 实际撤销的数量
        """
        if not role_permission_ids:
            return 0

        now = utc_now()
        updated = await cls.filter(
            id__in=role_permission_ids,
            is_active=True,
            revoked_at__isnull=True,
        ).update(
            is_active=False,
            revoked_at=now,
            revoked_by=revoked_by,
            reason=reason,
        )

        return updated

    @classmethod
    async def revoke_by_role_and_permissions(
            cls,
            role_id: int,
            permission_ids: List[int],
            revoked_by=None,
            reason: str = None,
    ) -> int:
        """
        撤销角色的指定权限

        Args:
            role_id: 角色ID
            permission_ids: 权限ID列表
            revoked_by: 撤销者
            reason: 撤销原因

        Returns:
            int: 实际撤销的数量
        """
        if not permission_ids:
            return 0

        now = utc_now()
        updated = await cls.filter(
            role_id=role_id,
            permission_id__in=permission_ids,
            is_active=True,
            revoked_at__isnull=True,
        ).update(
            is_active=False,
            revoked_at=now,
            revoked_by=revoked_by,
            reason=reason,
        )

        return updated

    @classmethod
    async def cleanup_expired(cls, before_time: datetime = None) -> int:
        """
        清理已过期的权限关联（标记为非激活）

        Args:
            before_time: 过期时间点之前的权限，默认为当前时间

        Returns:
            int: 清理的数量
        """
        before_time = before_time or utc_now()

        # 找到已过期但仍标记为激活的权限关联
        expired = await cls.filter(
            is_active=True,
            revoked_at__isnull=True,
            effective_to__isnull=False,
            effective_to__lte=before_time,
        ).update(
            is_active=False,
            revoked_at=utc_now(),
            reason='自动清理：权限已过期',
        )

        return expired

    @classmethod
    async def get_active_count_by_role(cls, role_id: int) -> int:
        """
        获取角色的有效权限数量

        Args:
            role_id: 角色ID

        Returns:
            int: 有效权限数量
        """
        now = utc_now()
        return await cls.filter(
            role_id=role_id,
            is_active=True,
            revoked_at__isnull=True,
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=now)
        ).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gt=now)
        ).count()

    # ========== 工具方法 ==========

    async def validate(self) -> None:
        """
        验证数据有效性（可在保存前调用）

        Raises:
            ValueError: 如果数据无效
        """
        # 检查时间逻辑
        if self.effective_from and self.effective_to:
            if self.effective_from >= self.effective_to:
                raise ValueError("生效开始时间必须早于结束时间")

        # 检查撤销逻辑
        if self.revoked_at and self.is_active:
            raise ValueError("已撤销的权限不能标记为激活")

        if self.revoked_at and self.revoked_at < self.granted_at:
            raise ValueError("撤销时间不能早于授予时间")

        # 检查生效时间与当前时间的关系
        now = utc_now()
        if self.effective_to and self.effective_to < now and self.is_active:
            # 这是一个警告，不是错误
            # 可以考虑自动标记为过期
            pass

    async def save(self, *args, **kwargs):
        """
        保存前自动验证
        """
        await self.validate()
        await super().save(*args, **kwargs)