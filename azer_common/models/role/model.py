import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from tortoise import fields
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from azer_common.models.base import BaseModel
from azer_common.models.permission.model import Permission
from azer_common.models.relations.role_permission import RolePermission
from azer_common.models.relations.user_role import UserRole
from azer_common.models.tenant.model import Tenant
from azer_common.models.user.model import User
from azer_common.utils.time import utc_now


class Role(BaseModel):
    # 核心标识字段
    code = fields.CharField(
        max_length=50,
        description='角色代码（同一租户下唯一）'
    )
    name = fields.CharField(
        max_length=50,
        description='角色显示名称'
    )
    role_type = fields.CharField(
        max_length=50,
        null=True,
        default=None,
        description='角色类型（业务自定义分类，如：管理员/运营/普通用户）'
    )
    description = fields.CharField(
        max_length=200,
        null=True,
        description='角色描述'
    )

    # 多租户字段
    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='roles',
        on_delete=fields.RESTRICT,
        description='所属租户（强关联，非空）',
        index=True,
        null=False
    )

    # 多对多关系
    permissions = fields.ManyToManyField(
        'models.Permission',
        through='azer_role_permission',
        related_name='roles',
        description='角色关联的权限',
        forward_key='role_id',
        backward_key='permission_id',
    )

    # 系统控制字段
    is_system = fields.BooleanField(
        default=False,
        description='是否系统内置角色（不可删除/修改核心属性）'
    )
    is_default = fields.BooleanField(
        default=False,
        description='是否默认角色（新用户自动分配）'
    )
    is_enabled = fields.BooleanField(
        default=True,
        description='角色是否启用（禁用后关联权限自动失效）'
    )

    # 权限继承字段
    level = fields.IntField(
        default=0,
        ge=0,
        description='角色等级（用于权限继承，数值越高优先级越高）'
    )
    parent = fields.ForeignKeyField(
        'models.Role',
        related_name='children',
        null=True,
        on_delete=fields.SET_NULL,
        description='父角色（用于角色继承）'
    )

    # 扩展字段
    metadata = fields.JSONField(
        null=True,
        description='角色元数据（如扩展属性、备注等）'
    )

    class Meta:
        table = "azer_role"
        table_description = '角色表（多租户+权限继承）'
        ordering = ["level", "code"]
        indexes = [
            ("tenant_id", "parent_id"),
            ("tenant_id", "code", "deleted_at"),
            ("tenant_id", "is_default"),
            ("tenant_id", "is_enabled", "deleted_at"),
            ("level", "tenant_id"),
        ]
        unique_together = [
            ("tenant_id", "code", "deleted_at"),  # tenant_id 是 ForeignKey 自动生成的字段
        ]

    def __str__(self):
        """优化：处理租户未加载的边界情况"""
        try:
            tenant_code = self.tenant.code if self.tenant else self.tenant_id
        except Exception:
            tenant_code = self.tenant_id
        return f"[{tenant_code}] {self.code} ({self.name})"

    async def save(self, *args, **kwargs):
        """保存前验证（强化租户+逻辑校验）"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def soft_delete(self):
        """
        重写软删除：先执行父类基础逻辑，再清理关联数据
        """
        if self.is_system:
            raise ValueError("系统内置角色不允许删除")

        async with in_transaction() as conn:
            # 1. 先调用父类的 soft_delete 方法（标记 is_deleted/deleted_at）
            await super().soft_delete()

            # 2. 撤销所有用户-角色关联（修改 is_assigned 为 False）
            await UserRole.objects.filter(
                role_id=self.id,
                is_assigned=True,
                is_deleted=False
            ).using_db(conn).update(
                is_assigned=False,
                updated_at=utc_now()
            )

            # 3. 撤销所有角色-权限关联（修改 is_granted 为 False）
            await RolePermission.objects.filter(
                role_id=self.id,
                is_granted=True,
                is_deleted=False
            ).using_db(conn).update(
                is_granted=False,
                updated_at=utc_now()
            )

            # 4. 清空子角色的父角色关联
            await self.__class__.objects.filter(
                parent_id=self.id,
                is_deleted=False
            ).using_db(conn).update(
                parent_id=None,  # 修正：使用 parent_id 而非 parent
                updated_at=utc_now()
            )

            # 5. 额外标记角色禁用
            self.is_enabled = False
            await self.save(
                update_fields=["is_enabled", "updated_at"],
                using_db=conn
            )

        return self

    async def validate(self):
        """验证角色数据（强化租户+逻辑校验，移除 code 唯一性）"""
        # 1. 租户存在性&有效性校验（核心：tenant 非空）
        if not hasattr(self, 'tenant_id') or self.tenant_id is None:
            raise ValueError("角色必须归属具体租户（tenant_id 不能为空）")

        # 检查租户是否存在且未被软删除/禁用
        tenant = await Tenant.objects.filter(
            id=self.tenant_id,
            is_deleted=False,
            is_enabled=True
        ).first()
        if not tenant:
            raise ValueError(f"租户不存在或已被禁用/删除（tenant_id: {self.tenant_id}）")

        # 2. 角色代码格式校验（仅格式，不校验唯一）
        if not re.match(r'^[A-Z_][A-Z0-9_]{0,49}$', self.code):
            raise ValueError(
                "角色代码必须为大写字母、数字和下划线，"
                "以字母或下划线开头，长度不超过50"
            )

        # 3. 父角色校验（自引用/循环/租户一致性）
        if self.parent_id:
            # 先加载父角色完整数据（包含租户关联）
            parent_role = await self.__class__.objects.filter(
                id=self.parent_id,
                tenant_id=self.tenant_id,  # 父角色必须同租户
                is_deleted=False
            ).prefetch_related('tenant').first()

            if not parent_role:
                raise ValueError(f"租户 [{tenant.code}] 下不存在父角色（id: {self.parent_id}）")

            # 禁止自引用
            if parent_role.id == self.id:
                raise ValueError("父角色不能是当前角色本身")

            # 父角色必须属于同一租户（双重校验）
            if parent_role.tenant_id != self.tenant_id:
                raise ValueError(
                    f"父角色 [{parent_role.code}] 属于租户 [{parent_role.tenant.code}]，"
                    f"与当前角色租户 [{tenant.code}] 不匹配"
                )

            # 检查循环继承
            visited = {self.id}
            current = parent_role
            max_depth = 20
            depth = 0

            while current and depth < max_depth:
                if current.id in visited:
                    raise ValueError("检测到角色继承循环（父角色链包含当前角色）")

                visited.add(current.id)
                # 加载下一级父角色（包含租户）
                current = await self.__class__.objects.filter(
                    id=current.parent_id,
                    tenant_id=self.tenant_id,
                    is_deleted=False
                ).prefetch_related('tenant').first() if current.parent_id else None
                depth += 1

            if depth >= max_depth:
                raise ValueError("角色继承层级过深（超过20层），可能存在循环或不合理设计")

        # 4. 系统角色校验（tenant 非空，仍禁止父角色/默认角色）
        if self.is_system:
            if self.parent_id:
                raise ValueError("系统内置角色不允许设置父角色")
            if self.is_default:
                raise ValueError("系统内置角色不能同时为默认角色")

        # 5. 默认角色唯一性（按租户）
        if self.is_default:
            default_query = self.__class__.objects.filter(
                is_default=True,
                tenant_id=self.tenant_id,
                is_deleted=False
            )
            if self.id:
                default_query = default_query.exclude(id=self.id)

            if await default_query.exists():
                raise ValueError(f"租户 [{tenant.code}] 下已存在默认角色，同一租户仅允许一个默认角色")

        # 6. 层级非负校验
        if self.level < 0:
            raise ValueError("角色等级不能为负数（level >= 0）")

    # ========== 权限操作：单个/批量授予/撤销 ==========
    async def grant_permission(
            self,
            permission: Union[Permission, int, str],
            effective_from: Optional[datetime] = None,
            effective_to: Optional[datetime] = None,
            metadata: Optional[Dict] = None,
    ) -> RolePermission:
        """
        为角色授予单个权限（兼容权限对象/ID/编码）
        """
        # 确保租户数据已加载
        if not hasattr(self, 'tenant') or self.tenant is None:
            self.tenant = await Tenant.objects.get(id=self.tenant_id)

        # 解析权限（支持编码）
        if isinstance(permission, str):
            perm_obj = await Permission.get_permission_by_code(
                code=permission,
                tenant_id=self.tenant_id,
                check_enabled=True
            )
            if not perm_obj:
                raise ValueError(f"租户 [{self.tenant.code}] 下不存在权限编码：{permission}")
            permission = perm_obj
        elif isinstance(permission, int):
            perm_obj = await Permission.validate_permission_tenant(
                permission=permission,
                role_tenant_id=self.tenant_id
            )
            permission = perm_obj

        # 调用 RolePermission 类方法完成授予
        return await RolePermission.grant(
            role=self,
            permission=permission,
            effective_from=effective_from,
            effective_to=effective_to,
            metadata=metadata
        )

    async def bulk_grant_permissions(
            self,
            permissions: List[Union[Permission, int, str]],
            effective_from: Optional[datetime] = None,
            effective_to: Optional[datetime] = None,
            metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        为角色批量授予权限
        """
        # 确保租户数据已加载
        if not hasattr(self, 'tenant') or self.tenant is None:
            self.tenant = await Tenant.objects.get(id=self.tenant_id)

        # 统一解析为权限ID
        perm_ids = []
        for perm in permissions:
            if isinstance(perm, str):
                perm_obj = await Permission.get_permission_by_code(
                    code=perm,
                    tenant_id=self.tenant_id,
                    check_enabled=True
                )
                if not perm_obj:
                    raise ValueError(f"租户 [{self.tenant.code}] 下不存在权限编码：{perm}")
                perm_ids.append(perm_obj.id)
            elif isinstance(perm, int):
                perm_ids.append(perm)
            elif hasattr(perm, 'id'):
                perm_ids.append(perm.id)
            else:
                raise ValueError(f"不支持的权限类型：{type(perm)}（仅支持对象/ID/编码）")

        # 调用 RolePermission 批量授予方法
        return await RolePermission.bulk_grant(
            role=self,
            permissions=perm_ids,
            effective_from=effective_from,
            effective_to=effective_to,
            metadata=metadata
        )

    async def revoke_permission(
            self,
            permission: Union[Permission, int, str],
    ) -> bool:
        """
        撤销角色的单个权限（兼容权限对象/ID/编码）
        """
        # 解析权限ID
        if isinstance(permission, str):
            perm_obj = await Permission.get_permission_by_code(
                code=permission,
                tenant_id=self.tenant_id,
                check_enabled=False
            )
            if not perm_obj:
                return False
            perm_id = perm_obj.id
        elif isinstance(permission, int):
            perm_id = permission
        elif hasattr(permission, 'id'):
            perm_id = permission.id
        else:
            raise ValueError(f"不支持的权限类型：{type(permission)}")

        # 查找并撤销权限关联
        role_perm = await RolePermission.find_by_role_and_permission(
            role_id=self.id,
            permission_id=perm_id,
            include_inactive=False,
            tenant_id=self.tenant_id
        )
        if not role_perm:
            return False

        await role_perm.revoke()
        return True

    async def bulk_revoke_permissions(
            self,
            permissions: List[Union[Permission, int, str]]
    ) -> int:
        """
        批量撤销角色的指定权限
        """
        # 解析权限ID
        perm_ids = []
        for perm in permissions:
            if isinstance(perm, str):
                perm_obj = await Permission.get_permission_by_code(
                    code=perm,
                    tenant_id=self.tenant_id,
                    check_enabled=False
                )
                if perm_obj:
                    perm_ids.append(perm_obj.id)
            elif isinstance(perm, int):
                perm_ids.append(perm)
            elif hasattr(perm, 'id'):
                perm_ids.append(perm.id)

        if not perm_ids:
            return 0

        # 调用 RolePermission 批量撤销方法
        return await RolePermission.revoke_by_role_and_permissions(
            role_id=self.id,
            permission_ids=perm_ids,
            tenant_id=self.tenant_id
        )

    # ========== 权限查询：有效权限/权限校验 ==========
    async def get_effective_permissions(
            self,
            check_time: Optional[datetime] = None,
            include_parents: bool = True,
            batch_size: int = 100
    ) -> List[Permission]:
        """
        获取角色的有效权限（包含父角色继承，子角色权限覆盖父角色）
        """
        check_time = check_time or utc_now()

        # 1. 获取角色继承链（当前角色 + 所有祖先角色，按 level 降序）
        role_chain = await self._get_role_inheritance_chain(
            include_parents=include_parents,
            batch_size=batch_size
        )
        if not role_chain:
            return []

        # 2. 批量查询所有角色的有效权限关联
        role_ids = [role.id for role in role_chain]
        effective_perms = await RolePermission.objects.filter(
            role_id__in=role_ids,
            is_granted=True,
            is_deleted=False,
            tenant_id=self.tenant_id
        ).filter(
            Q(effective_from__isnull=True) | Q(effective_from__lte=check_time),
            Q(effective_to__isnull=True) | Q(effective_to__gt=check_time)
        ).filter(
            role__is_enabled=True,
            role__is_deleted=False
        ).prefetch_related('permission')

        # 3. 按角色等级去重（高等级角色权限覆盖低等级）
        perm_map = {}
        role_level_map = {role.id: role.level for role in role_chain}

        for rp in effective_perms:
            perm_id = rp.permission.id
            # 高等级角色的权限覆盖低等级
            if perm_id not in perm_map or role_level_map[rp.role_id] > role_level_map[perm_map[perm_id].role_id]:
                perm_map[perm_id] = rp

        # 4. 提取 Permission 实例
        return [rp.permission for rp in perm_map.values()]

    async def has_permission(
            self,
            permission_code: str,
            check_time: Optional[datetime] = None
    ) -> bool:
        """
        检查角色是否拥有指定权限（包含父角色继承）
        """
        check_time = check_time or utc_now()

        # 1. 获取角色继承链
        role_chain = await self._get_role_inheritance_chain(include_parents=True)
        if not role_chain:
            return False

        # 2. 批量检查角色链的权限（复用 RolePermission 方法）
        for role in role_chain:
            if await RolePermission.has_permission(
                    role_id=role.id,
                    permission_code=permission_code,
                    check_time=check_time,
                    tenant_id=self.tenant_id
            ):
                return True

        return False

    # ========== 角色关联查询：用户/子角色 ==========
    async def get_users(
            self,
            only_valid: bool = True,
            batch_size: int = 100
    ) -> List[User]:
        """
        获取拥有当前角色的用户列表
        """
        query = UserRole.objects.filter(
            role_id=self.id,
            tenant_id=self.tenant_id  # 使用自动生成的 tenant_id 字段
        ).prefetch_related('user')

        # 过滤有效关联
        if only_valid:
            query = query.filter(
                Q(is_assigned=True) &
                (Q(expires_at__isnull=True) | Q(expires_at__gt=utc_now()))
            )

        # 批量加载并去重
        user_roles = await query.all()
        users = []
        user_ids = set()
        for ur in user_roles:
            if ur.user and ur.user.id not in user_ids:
                user_ids.add(ur.user.id)
                users.append(ur.user)

        return users

    async def get_children(self, include_disabled: bool = False) -> List['Role']:
        """
        获取当前角色的子角色列表
        """
        query = self.__class__.objects.filter(
            parent_id=self.id,
            tenant_id=self.tenant_id
        )

        if not include_disabled:
            query = query.filter(is_enabled=True)

        return await query.all()

    # ========== 内部辅助方法 ==========
    async def _get_role_inheritance_chain(
            self,
            include_parents: bool = True,
            batch_size: int = 100
    ) -> List['Role']:
        """
        获取角色继承链（当前角色 + 所有祖先角色，按 level 降序）
        """
        role_chain = [self]
        if not include_parents or not self.parent_id:
            return role_chain

        # 批量加载父角色链（防止 N+1 查询，强制加载租户关联）
        current_parent_id = self.parent_id
        fetched_ids = {self.id}
        depth = 0

        while current_parent_id and depth < batch_size:
            parent = await self.__class__.objects.filter(
                id=current_parent_id,
                tenant_id=self.tenant_id,
                is_enabled=True,
                is_deleted=False
            ).prefetch_related('tenant').first()

            if not parent or parent.id in fetched_ids:
                break

            role_chain.append(parent)
            fetched_ids.add(parent.id)
            current_parent_id = parent.parent_id
            depth += 1

        # 按 level 降序排序（高等级优先）
        return sorted(role_chain, key=lambda r: r.level, reverse=True)

    # ========== 数据格式化 ==========
    async def to_dict(
            self,
            include_related: bool = False,
            include_permissions: bool = False
    ) -> Dict[str, Any]:
        """
        转换为字典格式（支持关联数据）
        """
        # 确保租户数据已加载
        if not hasattr(self, 'tenant') or self.tenant is None:
            self.tenant = await Tenant.objects.get(id=self.tenant_id)

        base_dict = {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'role_type': self.role_type,
            'description': self.description,
            'is_system': self.is_system,
            'is_default': self.is_default,
            'is_enabled': self.is_enabled,
            'level': self.level,
            'parent_id': self.parent_id,
            'tenant_id': self.tenant_id,  # 明确返回自动生成的 tenant_id
            'tenant_code': self.tenant.code,
            'metadata': self.metadata,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'deleted_at': self.deleted_at,
        }

        # 补充关联数据
        if include_related:
            # 父角色
            if self.parent_id:
                parent = await self.__class__.objects.filter(id=self.parent_id).prefetch_related('tenant').first()
                base_dict['parent'] = parent.to_dict() if parent else None

            # 子角色
            children = await self.get_children(include_disabled=True)
            base_dict['children'] = [child.to_dict() for child in children]

        # 补充有效权限
        if include_permissions:
            permissions = await self.get_effective_permissions()
            base_dict['effective_permissions'] = [
                perm.to_dict() for perm in permissions
            ]

        return base_dict
