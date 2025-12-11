from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from tortoise.expressions import Q
from azer_common.models.base import BaseModel
from tortoise import fields
from azer_common.models.permission.model import Permission
from azer_common.utils.time import utc_now


class RolePermission(BaseModel):
    # 核心关联字段（已为ForeignKey，无需修改）
    role = fields.ForeignKeyField(
        'models.Role',
        related_name='role_permissions',
        description='角色',
        on_delete=fields.CASCADE  # 角色删除则关联权限自动删除
    )
    permission = fields.ForeignKeyField(
        'models.Permission',
        related_name='permission_roles',
        description='权限',
        on_delete=fields.CASCADE  # 权限删除则关联自动删除
    )

    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='role_permissions',
        description='所属租户（外键，保证数据一致性）',
        on_delete=fields.RESTRICT,  # 租户存在关联时禁止删除，避免数据丢失
        null=True,  # 兼容全局权限（无租户）
        index=True
    )

    # 状态控制字段（保持不变）
    is_granted = fields.BooleanField(
        default=True,
        description='是否授予'
    )
    effective_from = fields.DatetimeField(
        null=True,
        description='生效开始时间'
    )
    effective_to = fields.DatetimeField(
        null=True,
        description='生效结束时间'
    )
    metadata = fields.JSONField(
        null=True,
        description='扩展元数据'
    )

    class Meta:
        table = "azer_role_permission"
        table_description = '角色权限关联表'
        unique_together = ("role", "permission", "is_deleted")
        indexes = [
            ("role", "is_granted", "is_deleted", "effective_to"),
            ("permission", "is_granted", "is_deleted", "effective_to"),
            ("is_granted", "effective_from", "effective_to", "is_deleted"),
            ("tenant_id", "role", "is_granted"),
            ("tenant_id", "permission", "is_granted"),
        ]

    async def save(self, *args, **kwargs):
        """保存前自动验证（强化租户一致性）"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self) -> None:
        """验证数据有效性（保存前调用）"""
        # 1. 关联对象存在性校验
        if not self.role_id or not self.permission_id:
            raise ValueError("角色ID和权限ID不能为空")

        # 2. 延迟导入避免循环依赖
        from azer_common.models.role.model import Role
        from azer_common.models.tenant.model import Tenant

        # 3. 加载关联数据（保证租户字段可访问）
        await self.fetch_related('role', 'permission')

        # 4. 租户一致性验证（Role和Permission的租户必须匹配）
        role_tenant_id = self.role.tenant_id
        perm_tenant_id = getattr(self.permission, 'tenant_id', None)

        # 规则：权限租户优先，无则取角色租户；全局权限（perm_tenant_id=None）兼容角色租户
        if perm_tenant_id and role_tenant_id and perm_tenant_id != role_tenant_id:
            raise ValueError(
                f"权限租户（{perm_tenant_id}）与角色租户（{role_tenant_id}）不匹配"
            )

        # 5. 自动填充租户外键（核心修改：从CharField改为ForeignKey赋值）
        target_tenant_id = perm_tenant_id or role_tenant_id
        if target_tenant_id:
            self.tenant = await Tenant.objects.filter(id=target_tenant_id).first()
        else:
            self.tenant = None  # 全局权限

        # 6. 时间逻辑验证
        if self.effective_from and self.effective_to:
            if self.effective_from >= self.effective_to:
                raise ValueError("生效开始时间必须早于结束时间")

    async def activate(self, **kwargs) -> None:
        """重新激活已撤销的权限"""
        if not self.is_granted:
            self.is_granted = True
            await self.save(**kwargs)

    async def revoke(self, **kwargs) -> None:
        """撤销角色权限"""
        self.is_granted = False
        await self.save(**kwargs)

    async def update_effective_period(
            self,
            effective_from: datetime = None,
            effective_to: datetime = None,
            **kwargs
    ) -> None:
        """更新权限生效时间段"""
        if effective_from is not None:
            self.effective_from = effective_from

        if effective_to is not None:
            self.effective_to = effective_to

        await self.save(**kwargs)

    async def to_dict(self, include_related: bool = False) -> Dict[str, Any]:
        """转换为字典格式（兼容原有tenant_id字段）"""
        result = {
            'id': self.id,
            'role_id': self.role_id,
            'permission_id': self.permission_id,
            'tenant_id': self.tenant_id,  # 兼容原有字段（ForeignKey自动生成）
            'is_granted': self.is_granted,
            'effective_from': self.effective_from,
            'effective_to': self.effective_to,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'deleted_at': self.deleted_at,
        }

        if include_related:
            await self.fetch_related('role', 'permission', 'tenant')
            # 补充角色信息
            if self.role:
                result['role'] = {
                    'id': self.role.id,
                    'name': self.role.name,
                    'code': getattr(self.role, 'code', None),
                }
            # 补充权限信息
            if self.permission:
                result['permission'] = {
                    'id': self.permission.id,
                    'code': self.permission.code,
                    'name': self.permission.name,
                    'action': self.permission.action,
                    'resource_type': self.permission.resource_type,
                }
            # 补充租户信息（新增）
            if self.tenant:
                result['tenant'] = {
                    'id': self.tenant.id,
                    'code': self.tenant.code,
                    'name': self.tenant.name,
                }
        return result

    # ========== 供 Role 模型调用的核心类方法（适配租户外键） ==========
    @classmethod
    async def _get_role_obj(cls, role_id: int) -> 'Role':
        """内部辅助：获取角色实例（避免重复代码）"""
        from azer_common.models.role.model import Role  # 延迟导入避免循环依赖
        role_obj = await Role.objects.filter(id=role_id).first()
        if not role_obj:
            raise ValueError(f"角色不存在（ID: {role_id}）")
        return role_obj

    @classmethod
    async def grant(
            cls,
            role: Union[int, 'Role'],
            permission: Union[int, Permission],
            effective_from: datetime = None,
            effective_to: datetime = None,
            metadata: Dict = None,
            **kwargs
    ) -> 'RolePermission':
        """授予角色权限（适配租户外键）"""
        # 解析角色/权限ID
        role_id = role.id if hasattr(role, 'id') else role
        permission_id = permission.id if hasattr(permission, 'id') else permission

        # 1. 校验权限存在性+租户一致性
        role_obj = await cls._get_role_obj(role_id)
        perm_obj = await Permission.validate_permission_tenant(
            permission=permission_id,
            role_tenant_id=role_obj.tenant_id
        )

        # 2. 检查是否已存在有效的权限关联
        existing = await cls.objects.filter(
            role_id=role_id,
            permission_id=permission_id,
            is_granted=True
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=utc_now()),
            Q(effective_to__isnull=True) | Q(effective_to__gt=utc_now())
        ).first()

        if existing:
            raise ValueError(f"角色已拥有该有效权限（ID: {existing.id}）")

        # 3. 创建新的权限关联（适配租户外键）
        target_tenant_id = perm_obj.tenant_id or role_obj.tenant_id
        role_permission = cls(
            role_id=role_id,
            permission_id=permission_id,
            effective_from=effective_from,
            effective_to=effective_to,
            metadata=metadata,
            tenant_id=target_tenant_id,  # 直接赋值外键生成的tenant_id字段
            **kwargs
        )
        await role_permission.save()
        return role_permission

    @classmethod
    async def bulk_grant(
            cls,
            role: Union[int, 'Role'],
            permissions: List[Union[int, Permission]],
            effective_from: datetime = None,
            effective_to: datetime = None,
            metadata: Dict = None,
    ) -> Dict[str, Any]:
        """批量授予权限（适配租户外键）"""
        # 1. 解析角色ID+权限ID
        role_id = role.id if hasattr(role, 'id') else role
        role_obj = await cls._get_role_obj(role_id)
        permission_ids = []
        for perm in permissions:
            perm_id = perm.id if hasattr(perm, 'id') else perm
            permission_ids.append(perm_id)

        if not permission_ids:
            return {"created": [], "existing": [], "total": 0, "created_count": 0, "existing_count": 0}

        # 2. 校验权限存在性+租户一致性
        valid_perms = await Permission.bulk_get_permissions(
            permission_ids=permission_ids,
            tenant_id=role_obj.tenant_id
        )
        valid_perm_ids = {p.id for p in valid_perms}
        invalid_perm_ids = set(permission_ids) - valid_perm_ids
        if invalid_perm_ids:
            raise ValueError(f"权限不存在/租户不匹配: {invalid_perm_ids}")

        # 3. 批量查询已存在的有效权限关联
        existing_role_perms = await cls.objects.filter(
            role_id=role_id,
            permission_id__in=valid_perm_ids,
            is_granted=True
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=utc_now()),
            Q(effective_to__isnull=True) | Q(effective_to__gt=utc_now())
        ).values_list('permission_id', flat=True)

        existing_perm_ids = set(existing_role_perms)
        to_create_perm_ids = set(valid_perm_ids) - existing_perm_ids

        # 4. 批量创建新的权限关联（适配租户外键）
        role_perms_to_create = []
        target_tenant_id = role_obj.tenant_id  # 角色租户ID（全局权限自动为None）
        for perm_id in to_create_perm_ids:
            role_perms_to_create.append(
                cls(
                    role_id=role_id,
                    permission_id=perm_id,
                    effective_from=effective_from,
                    effective_to=effective_to,
                    metadata=metadata,
                    is_granted=True,
                    tenant_id=target_tenant_id  # 赋值租户ID（外键自动关联）
                )
            )

        created = []
        if role_perms_to_create:
            created = await cls.objects.bulk_create(role_perms_to_create)

        # 5. 整理返回结果
        return {
            "created": created,
            "existing": list(existing_perm_ids),
            "total": len(permission_ids),
            "created_count": len(created),
            "existing_count": len(existing_perm_ids),
        }

    @classmethod
    async def get_effective_permissions(
            cls,
            role_id: int,
            check_time: datetime = None,
            include_inactive_role: bool = False,
            tenant_id: Optional[int] = None  # 适配外键的tenant_id（int类型）
    ) -> List['RolePermission']:
        """获取角色有效权限（适配租户外键过滤）"""
        check_time = check_time or utc_now()

        query = cls.objects.filter(
            role_id=role_id,
            is_granted=True
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=check_time),
            Q(effective_to__isnull=True) | Q(effective_to__gt=check_time)
        )
        # 租户过滤（适配外键的tenant_id字段）
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        # 过滤无效角色
        if not include_inactive_role:
            query = query.filter(role__is_enabled=True)

        return await query.prefetch_related('permission', 'tenant')

    @classmethod
    async def has_permission(
            cls,
            role_id: int,
            permission_code: str,
            check_time: datetime = None,
            tenant_id: Optional[int] = None
    ) -> bool:
        """检查角色是否拥有指定权限（适配租户外键）"""
        check_time = check_time or utc_now()

        # 先查权限编码对应的ID
        perm = await Permission.get_permission_by_code(
            code=permission_code,
            tenant_id=tenant_id,
            check_enabled=True
        )
        if not perm:
            return False

        # 再查角色权限关联（适配租户外键）
        count = await cls.objects.filter(
            role_id=role_id,
            permission_id=perm.id,
            is_granted=True
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=check_time),
            Q(effective_to__isnull=True) | Q(effective_to__gt=check_time)
        ).filter(
            Q(tenant_id=tenant_id) if tenant_id else Q(tenant_id__isnull=True)
        ).count()

        return count > 0

    @classmethod
    async def find_by_role_and_permission(
            cls,
            role_id: int,
            permission_id: int,
            include_inactive: bool = False,
            tenant_id: Optional[int] = None
    ) -> Optional['RolePermission']:
        """根据角色ID和权限ID查找关联（适配租户外键）"""
        query = cls.objects.filter(
            role_id=role_id,
            permission_id=permission_id
        )
        # 租户过滤
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)
        # 过滤未激活的
        if not include_inactive:
            query = query.filter(is_granted=True)

        return await query.first()

    @classmethod
    async def revoke_by_ids(
            cls,
            role_permission_ids: List[int],
            **kwargs
    ) -> int:
        """批量撤销权限关联"""
        if not role_permission_ids:
            return 0

        updated = await cls.objects.filter(
            id__in=role_permission_ids,
            is_granted=True
        ).update(
            is_granted=False,
            **kwargs
        )
        return updated

    @classmethod
    async def revoke_by_role_and_permissions(
            cls,
            role_id: int,
            permission_ids: List[int],
            tenant_id: Optional[int] = None,
            **kwargs
    ) -> int:
        """撤销角色指定权限（适配租户外键）"""
        if not permission_ids:
            return 0

        query = cls.objects.filter(
            role_id=role_id,
            permission_id__in=permission_ids,
            is_granted=True
        )
        # 租户过滤
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)

        updated = await query.update(is_granted=False, **kwargs)
        return updated

    @classmethod
    async def cleanup_expired(cls, before_time: datetime = None, tenant_id: Optional[int] = None) -> int:
        """清理已过期的权限关联（适配租户外键）"""
        before_time = before_time or utc_now()

        query = cls.objects.filter(
            is_granted=True,
            effective_to__isnull=False,
            effective_to__lte=before_time
        )
        # 租户过滤
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)

        expired = await query.update(is_granted=False)
        return expired