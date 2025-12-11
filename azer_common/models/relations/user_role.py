from datetime import datetime
from typing import Dict, List, Optional, Union

from tortoise.expressions import Q
from tortoise.exceptions import DoesNotExist

from azer_common.models.base import BaseModel
from tortoise import fields

from azer_common.models.role.model import Role
from azer_common.models.user.model import User
from azer_common.utils.time import utc_now, add_days


class UserRole(BaseModel):
    # 核心关联字段（级联删除：用户/角色删除则关联自动删除）
    user = fields.ForeignKeyField(
        'models.User',
        related_name='user_roles',
        description='用户',
        on_delete=fields.CASCADE,
        null=False  # 强制非空
    )
    role = fields.ForeignKeyField(
        'models.Role',
        related_name='role_users',
        description='角色',
        on_delete=fields.CASCADE,
        null=False  # 强制非空
    )

    # ========== 关键修正：多租户字段优化 ==========
    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='user_roles',
        description='所属租户（外键，保证数据一致性）',
        on_delete=fields.RESTRICT,
        null=False,
        index=True
    )

    # 核心业务状态字段
    is_assigned = fields.BooleanField(
        default=True,
        description='是否分配（用户-角色关联关系是否有效）'
    )
    expires_at = fields.DatetimeField(
        null=True,
        description='到期时间（null表示永久有效）'
    )
    metadata = fields.JSONField(
        null=True,
        description='扩展元数据'
    )

    class Meta:
        table = "azer_user_role"
        table_description = '用户角色关系表（核心关联表）'
        unique_together = ("user", "role", "tenant", "is_deleted")
        indexes = [
            # 基础查询索引
            ("user_id", "is_assigned", "expires_at", "is_deleted"),
            ("role_id", "is_assigned", "expires_at", "is_deleted"),
            ("expires_at", "is_assigned", "is_deleted"),
            ("tenant_id", "user_id", "is_assigned"),
            ("tenant_id", "role_id", "is_assigned"),
            ("tenant_id", "expires_at", "is_assigned"),
        ]

    def __str__(self):
        """优化：展示核心信息+租户+有效性"""
        tenant_info = "[全局]" if self.tenant_id is None else f"[租户:{self.tenant_id}]"
        valid_status = "有效" if self.is_valid() else "无效"
        return f"{tenant_info} 用户({self.user_id})-角色({self.role_id}) [{valid_status}]"

    async def save(self, *args, **kwargs):
        """保存前强验证+自动填充租户+多租户一致性校验"""
        # 1. 基础非空校验
        if not self.user_id or not self.role_id:
            raise ValueError("用户ID和角色ID不能为空")

        # 2. 预加载关联数据（仅加载一次）
        if not hasattr(self, '_user_loaded'):
            await self.fetch_related('user', 'role')
            self._user_loaded = True

        # 3. 自动填充租户ID（优先级：角色租户 > 用户租户，保证一致性）
        if not self.tenant_id:
            self.tenant_id = self.role.tenant_id or self.user.tenant_id

        # 4. 核心验证
        await self.validate()

        # 5. 执行保存
        await super().save(*args, **kwargs)

    async def validate(self):
        """强化验证：解决多租户、逻辑一致性问题"""
        # ========== 1. 关联对象存在性校验 ==========
        try:
            # 验证用户存在（未删除）
            await User.objects.filter(id=self.user_id, is_deleted=False).get()
            # 验证角色存在（未删除+启用）
            await Role.objects.filter(id=self.role_id, is_deleted=False, is_enabled=True).get()
        except DoesNotExist as e:
            raise ValueError(f"用户/角色不存在或已删除：{str(e)}")

        # ========== 2. 多租户一致性校验（解决TODO：用户-租户多对多） ==========
        # 步骤1：获取用户所属的所有租户ID（多对多场景）
        # 假设User与Tenant的关联表为UserTenant，字段为user_id/tenant_id
        # 若User直接有tenant_ids字段（多对多），则替换为：user_tenant_ids = self.user.tenant_ids
        user_tenant_ids = await self.user.tenants.values_list('id', flat=True)  # 适配多对多关联

        # 步骤2：角色租户ID校验（全局角色/用户租户内角色）
        role_tenant_id = self.role.tenant_id
        if role_tenant_id is not None:
            # 非全局角色：必须在用户的租户范围内
            if role_tenant_id not in user_tenant_ids:
                raise ValueError(
                    f"角色租户({role_tenant_id})不在用户({self.user_id})的租户范围({user_tenant_ids})内"
                )

        # ========== 3. 时间逻辑校验 ==========
        now = utc_now()
        if self.expires_at and self.expires_at <= now:
            raise ValueError(f"过期时间({self.expires_at})不能早于当前时间({now})")

        # ========== 4. 状态逻辑校验 ==========
        if self.is_assigned and self.is_expired():
            raise ValueError("已过期的角色关联不能标记为'已分配'")

        # ========== 5. 租户一致性最终校验 ==========
        if self.tenant_id is not None and self.tenant_id not in user_tenant_ids:
            raise ValueError(f"关联租户({self.tenant_id})不在用户({self.user_id})的租户范围({user_tenant_ids})内")

    def is_expired(self) -> bool:
        """检查角色是否过期（UTC时间）"""
        if not self.expires_at:
            return False
        return utc_now() >= self.expires_at

    def is_valid(self) -> bool:
        """检查角色是否有效（未过期+未撤销+未删除）"""
        return self.is_assigned and not self.is_expired() and not self.is_deleted

    # ========== 核心业务方法：单角色授予（优化多租户） ==========
    @classmethod
    async def grant_role(
            cls,
            user: Union[int, 'User'],
            role: Union[int, 'Role'],
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> 'UserRole':
        """
        授予单个角色（强化多租户校验）
        :param user: 用户ID 或 User实例
        :param role: 角色ID 或 Role实例
        :param expires_in_days: 过期天数（None=永久）
        :param metadata: 扩展元数据
        :raise ValueError: 已存在有效角色/租户不匹配/用户/角色不存在
        """
        # 1. 解析并验证用户/角色
        user_id = user.id if hasattr(user, 'id') else user
        role_id = role.id if hasattr(role, 'id') else role

        # 2. 检查用户/角色存在性
        try:
            user_obj = await User.objects.filter(id=user_id, is_deleted=False).get()
            role_obj = await Role.objects.filter(id=role_id, is_deleted=False, is_enabled=True).get()
        except DoesNotExist as e:
            raise ValueError(f"授予失败：{str(e)}")

        # 3. 多租户预校验
        user_tenant_ids = await user_obj.tenants.values_list('id', flat=True)
        if role_obj.tenant_id and role_obj.tenant_id not in user_tenant_ids:
            raise ValueError(
                f"角色({role_id})租户({role_obj.tenant_id})不在用户({user_id})租户范围({user_tenant_ids})内")

        # 4. 检查是否已存在有效角色关联（排除软删除）
        existing = await cls.objects.filter(
            user_id=user_id,
            role_id=role_id,
            is_assigned=True,
            is_deleted=False  # 排除软删除
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=utc_now())
        ).first()

        if existing and existing.is_valid():
            raise ValueError(f"用户({user_id})已拥有角色({role_id})的有效关联（ID:{existing.id}）")

        # 5. 计算过期时间
        expires_at = add_days(days=expires_in_days) if expires_in_days else None

        # 6. 创建关联（自动填充租户）
        user_role = cls(
            user_id=user_id,
            role_id=role_id,
            expires_at=expires_at,
            metadata=metadata,
            is_assigned=True,
            tenant_id=role_obj.tenant_id or user_obj.tenant_id  # 优先级：角色租户 > 用户租户
        )
        await user_role.save()
        return user_role

    @classmethod
    async def bulk_grant_roles(
            cls,
            user: Union[int, 'User'],
            roles: List[Union[int, 'Role']],
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> Dict[str, any]:
        """
        批量授予角色（解决用户-租户多对多问题）
        :return: 包含 created/existing/invalid_tenant/total 等信息的结果
        """
        # 1. 解析用户并验证
        if isinstance(user, User):
            user_id = user.id
            user_obj = user
        else:
            user_id = user
            try:
                user_obj = await User.objects.filter(id=user_id, is_deleted=False).get()
            except DoesNotExist:
                raise ValueError(f"用户({user_id})不存在或已删除")

        # 2. 获取用户所有租户ID（多对多核心）
        user_tenant_ids = await user_obj.tenants.values_list('id', flat=True)
        if not user_tenant_ids:
            raise ValueError(f"用户({user_id})未关联任何租户，无法授予角色")

        # 3. 解析并验证角色列表
        role_ids = []
        role_obj_map = {}  # role_id -> role_obj
        for r in roles:
            role_id = r.id if hasattr(r, 'id') else r
            role_ids.append(role_id)

        if not role_ids:
            return {
                "created": [], "existing": [], "invalid_tenant": [],
                "total": 0, "created_count": 0, "existing_count": 0, "invalid_tenant_count": 0
            }

        # 4. 批量查询角色（过滤未删除+启用）
        role_objs = await Role.objects.filter(
            id__in=role_ids,
            is_deleted=False,
            is_enabled=True
        ).prefetch_related('tenant')

        # 构建角色映射 & 筛选租户无效的角色
        valid_role_ids = []
        invalid_tenant_role_ids = []
        for r_obj in role_objs:
            role_obj_map[r_obj.id] = r_obj
            # 租户校验：全局角色/用户租户内角色
            if r_obj.tenant_id is None or r_obj.tenant_id in user_tenant_ids:
                valid_role_ids.append(r_obj.id)
            else:
                invalid_tenant_role_ids.append(r_obj.id)

        # 5. 查询已存在的有效关联（排除软删除）
        existing = await cls.objects.filter(
            user_id=user_id,
            role_id__in=valid_role_ids,
            is_assigned=True,
            is_deleted=False
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=utc_now())
        ).values_list('role_id', flat=True)

        existing_ids = set(existing)
        to_create_ids = set(valid_role_ids) - existing_ids

        # 6. 计算过期时间
        expires_at = add_days(days=expires_in_days) if expires_in_days else None

        # 7. 批量创建
        to_create = []
        for rid in to_create_ids:
            r_obj = role_obj_map[rid]
            to_create.append(
                cls(
                    user_id=user_id,
                    role_id=rid,
                    expires_at=expires_at,
                    metadata=metadata,
                    is_assigned=True,
                    tenant_id=r_obj.tenant_id or user_tenant_ids[0]  # 全局角色默认绑定用户第一个租户
                )
            )

        created = []
        if to_create:
            created = await cls.objects.bulk_create(to_create)

        # 8. 整理结果（包含租户无效的角色）
        return {
            "created": created,
            "existing": list(existing_ids),
            "invalid_tenant": invalid_tenant_role_ids,
            "total": len(role_ids),
            "created_count": len(created),
            "existing_count": len(existing_ids),
            "invalid_tenant_count": len(invalid_tenant_role_ids)
        }

    @classmethod
    async def revoke_role(
            cls,
            user: Union[int, 'User'],
            role: Union[int, 'Role']
    ) -> bool:
        """
        撤销用户的单个角色（标记为未分配，保留记录）
        :return: 是否成功撤销
        """
        user_id = user.id if hasattr(user, 'id') else user
        role_id = role.id if hasattr(role, 'id') else role

        updated_count = await cls.objects.filter(
            user_id=user_id,
            role_id=role_id,
            is_assigned=True,
            is_deleted=False  # 排除软删除
        ).update(
            is_assigned=False,
            updated_at=utc_now()
        )

        return updated_count > 0

    @classmethod
    async def bulk_revoke_roles(
            cls,
            user: Union[int, 'User'],
            roles: List[Union[int, 'Role']] = None,
            tenant_id: Optional[int] = None  # 新增：按租户过滤
    ) -> int:
        """
        批量撤销用户的角色（支持按租户过滤）
        :param user: 用户ID/实例
        :param roles: 角色ID/实例列表（None=撤销所有有效角色）
        :param tenant_id: 租户ID（None=所有租户）
        :return: 成功撤销的数量
        """
        user_id = user.id if hasattr(user, 'id') else user
        query = cls.objects.filter(
            user_id=user_id,
            is_assigned=True,
            is_deleted=False
        )

        # 按租户过滤
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)

        # 按角色过滤
        if roles:
            role_ids = [r.id if hasattr(r, 'id') else r for r in roles]
            query = query.filter(role_id__in=role_ids)

        # 批量更新
        updated_count = await query.update(
            is_assigned=False,
            updated_at=utc_now()
        )

        return updated_count

    @classmethod
    async def get_user_roles(
            cls,
            user: Union[int, 'User'],
            include_expired: bool = False,
            include_revoked: bool = False,
            tenant_id: Optional[int] = None,
            include_deleted: bool = False
    ) -> List['UserRole']:
        """
        查询用户的角色关联列表（强化多租户过滤）
        """
        user_id = user.id if hasattr(user, 'id') else user
        query = cls.objects.filter(
            user_id=user_id
        ).prefetch_related('role', 'tenant')  # 预加载关联

        # 过滤软删除
        if not include_deleted:
            query = query.filter(is_deleted=False)

        # 过滤已撤销的
        if not include_revoked:
            query = query.filter(is_assigned=True)

        # 过滤已过期的
        if not include_expired:
            query = query.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=utc_now())
            )

        # 按租户过滤
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)

        return await query.all()

    @classmethod
    async def has_role(
            cls,
            user: Union[int, 'User'],
            role: Union[int, 'Role', str],
            check_valid: bool = True,
            tenant_id: Optional[int] = None  # 新增：按租户过滤
    ) -> bool:
        """
        检查用户是否拥有指定角色（强化多租户+编码查询）
        :param user: 用户ID/实例
        :param role: 角色ID/实例/编码
        :param check_valid: 是否仅检查有效角色（未过期+未撤销）
        :param tenant_id: 租户ID（None=所有租户）
        """
        user_id = user.id if hasattr(user, 'id') else user
        query = cls.objects.filter(
            user_id=user_id,
            is_deleted=False  # 排除软删除
        )

        # 1. 按角色类型过滤
        if isinstance(role, str):
            # 按角色编码查询（关联Role表，过滤启用+未删除）
            query = query.filter(
                role__code=role,
                role__is_deleted=False,
                role__is_enabled=True
            )
        else:
            role_id = role.id if hasattr(role, 'id') else role
            query = query.filter(role_id=role_id)

        # 2. 按租户过滤
        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)

        # 3. 检查有效状态
        if check_valid:
            query = query.filter(
                Q(is_assigned=True) &
                (Q(expires_at__isnull=True) | Q(expires_at__gt=utc_now()))
            )

        return await query.exists()

    @classmethod
    async def refresh_expires_at(
            cls,
            user: Union[int, 'User'],
            role: Union[int, 'Role'],
            expires_in_days: int,
            tenant_id: Optional[int] = None
    ) -> bool:
        """
        刷新角色的过期时间（支持按租户过滤）
        :return: 是否成功更新
        """
        user_id = user.id if hasattr(user, 'id') else user
        role_id = role.id if hasattr(role, 'id') else role

        new_expires_at = add_days(days=expires_in_days)
        query = cls.objects.filter(
            user_id=user_id,
            role_id=role_id,
            is_deleted=False
        )

        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)

        updated_count = await query.update(
            expires_at=new_expires_at,
            updated_at=utc_now()
        )

        return updated_count > 0

    # ========== 核心业务方法：清理过期角色 ==========
    @classmethod
    async def cleanup_expired(cls, before_time: datetime = None, tenant_id: Optional[int] = None) -> int:
        """
        清理已过期的角色关联（标记为未分配，支持按租户过滤）
        :return: 清理的数量
        """
        before_time = before_time or utc_now()
        query = cls.objects.filter(
            is_assigned=True,
            is_deleted=False,
            expires_at__isnull=False,
            expires_at__lte=before_time
        )

        if tenant_id is not None:
            query = query.filter(tenant_id=tenant_id)

        updated_count = await query.update(
            is_assigned=False,
            updated_at=utc_now()
        )
        return updated_count
