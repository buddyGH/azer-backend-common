from typing import Dict, List, Optional, Union
from tortoise import fields
from tortoise.expressions import Q

from azer_common.models.base import BaseModel
from azer_common.models.user.model import User
from azer_common.models.tenant.model import Tenant
from azer_common.utils.time import utc_now, add_days


class TenantUser(BaseModel):
    """租户-用户关联表 """
    tenant = fields.ForeignKeyField(
        'models.Tenant',
        related_name='tenant_users',
        on_delete=fields.CASCADE,
        description='关联租户'
    )
    user = fields.ForeignKeyField(
        'models.User',
        related_name='user_tenants',
        on_delete=fields.CASCADE,
        description='关联用户'
    )

    is_primary = fields.BooleanField(
        default=False,
        description='是否用户的主租户（一个用户仅一个主租户）'
    )
    is_assigned = fields.BooleanField(
        default=True,
        description='是否已分配（取消分配则置为False）'
    )
    expired_at = fields.DatetimeField(
        null=True,
        description='关联过期时间（null表示永久有效）'
    )
    metadata = fields.JSONField(
        null=True,
        description='关联元数据（如分配原因、权限范围）'
    )

    class Meta:
        table = "azer_tenant_user"
        table_description = '租户-用户关联表'
        unique_together = ("tenant", "user", "is_deleted")
        indexes = [
            ("tenant", "is_assigned"),
            ("user", "is_primary"),
            ("expired_at", "is_assigned"),
        ]

    def __str__(self):
        return f"租户[{self.tenant.code}] - 用户[{self.user.username}]"

    @property
    def is_valid(self) -> bool:
        """检查关联是否有效（已分配+未过期+未软删除）"""
        if not self.is_assigned or self.is_deleted:
            return False
        if self.expired_at and self.expired_at < utc_now():
            return False
        return True

    # ========== 核心操作方法（以租户为主体，全量使用objects） ==========
    @classmethod
    async def grant_user(
            cls,
            tenant: Union[int, Tenant],
            user: Union[int, User],
            is_primary: bool = False,
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> "TenantUser":
        """
        给租户分配单个用户（以租户为主体）
        :param tenant: 租户ID/实例
        :param user: 用户ID/实例
        :param is_primary: 是否设为用户的主租户
        :param expires_in_days: 关联过期天数（None表示永久）
        :param metadata: 关联元数据
        :return: 创建/更新的TenantUser实例
        """
        # 解析实例
        tenant_obj = await Tenant.objects.get(id=tenant) if isinstance(tenant, int) else tenant
        user_obj = await User.objects.get(id=user) if isinstance(user, int) else user

        # 检查是否已存在关联（排除软删除的记录）
        tenant_user, created = await cls.objects.get_or_create(
            tenant=tenant_obj,
            user=user_obj,
            is_deleted=False,  # 对齐BaseModel软删除字段
            defaults={
                "is_primary": is_primary,
                "is_assigned": True,
                "expired_at": add_days(utc_now(), expires_in_days) if expires_in_days else None,
                "metadata": metadata
            }
        )

        # 如果设为主租户，需要取消该用户其他主租户
        if is_primary:
            tenant_user.is_primary = True
            await tenant_user.save(update_fields=["is_primary", "updated_at"])

            # 取消该用户其他租户的主租户标记
            await cls.objects.filter(
                user=user_obj,
                is_primary=True,
                is_deleted=False
            ).exclude(id=tenant_user.id).update(
                is_primary=False,
                updated_at=utc_now()
            )

        return tenant_user

    @classmethod
    async def bulk_grant_users(
            cls,
            tenant: Union[int, Tenant],
            users: List[Union[int, User]],
            is_primary: bool = False,
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> Dict[str, any]:
        """
        给租户批量分配用户（以租户为主体）
        :return: 操作结果（created: 新增数量, updated: 更新数量, failed: 失败列表）
        """
        tenant_obj = await Tenant.objects.get(id=tenant) if isinstance(tenant, int) else tenant
        expired_at = add_days(utc_now(), expires_in_days) if expires_in_days else None

        created = 0
        updated = 0
        failed = []

        for user in users:
            try:
                user_obj = await User.objects.get(id=user) if isinstance(user, int) else user
                tu, cr = await cls.objects.get_or_create(
                    tenant=tenant_obj,
                    user=user_obj,
                    is_deleted=False,
                    defaults={
                        "is_primary": is_primary,
                        "is_assigned": True,
                        "expired_at": expired_at,
                        "metadata": metadata
                    }
                )
                if cr:
                    created += 1
                else:
                    # 仅更新必要字段
                    update_fields = []
                    if tu.is_primary != is_primary:
                        tu.is_primary = is_primary
                        update_fields.append("is_primary")
                    if tu.expired_at != expired_at:
                        tu.expired_at = expired_at
                        update_fields.append("expired_at")
                    if tu.metadata != metadata:
                        tu.metadata = metadata
                        update_fields.append("metadata")
                    if not tu.is_assigned:
                        tu.is_assigned = True
                        update_fields.append("is_assigned")

                    if update_fields:
                        tu.updated_at = utc_now()
                        update_fields.append("updated_at")
                        await tu.save(update_fields=update_fields)
                        updated += 1

                # 主租户逻辑：取消该用户其他主租户
                if is_primary:
                    await cls.objects.filter(
                        user=user_obj,
                        is_primary=True,
                        is_deleted=False
                    ).exclude(id=tu.id).update(
                        is_primary=False,
                        updated_at=utc_now()
                    )
            except Exception as e:
                failed.append({"user": user, "error": str(e)})

        return {
            "created": created,
            "updated": updated,
            "failed": failed,
            "total": len(users),
            "success": len(users) - len(failed)
        }

    @classmethod
    async def revoke_user(
            cls,
            tenant: Union[int, Tenant],
            user: Union[int, User]
    ) -> bool:
        """
        撤销租户下的单个用户（软删除：置为未分配）
        :return: 是否成功
        """
        tenant_id = tenant.id if isinstance(tenant, Tenant) else tenant
        user_id = user.id if isinstance(user, User) else user

        count = await cls.objects.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            is_deleted=False
        ).update(
            is_assigned=False,
            updated_at=utc_now()
        )
        return count > 0

    @classmethod
    async def bulk_revoke_users(
            cls,
            tenant: Union[int, Tenant],
            users: List[Union[int, User]]
    ) -> int:
        """
        批量撤销租户下的用户
        :return: 成功撤销的数量
        """
        tenant_id = tenant.id if isinstance(tenant, Tenant) else tenant
        user_ids = [u.id if isinstance(u, User) else u for u in users]

        return await cls.objects.filter(
            tenant_id=tenant_id,
            user_id__in=user_ids,
            is_deleted=False
        ).update(
            is_assigned=False,
            updated_at=utc_now()
        )

    @classmethod
    async def get_tenant_users(
            cls,
            tenant: Union[int, Tenant],
            include_expired: bool = False,
            include_unassigned: bool = False
    ) -> List["TenantUser"]:
        """
        获取租户下的所有用户关联（以租户为主体）
        """
        tenant_id = tenant.id if isinstance(tenant, Tenant) else tenant
        query = cls.objects.filter(
            tenant_id=tenant_id,
            is_deleted=False
        )

        if not include_unassigned:
            query = query.filter(is_assigned=True)
        if not include_expired:
            query = query.filter(
                cls.expired_at.is_null() | (cls.expired_at > utc_now())
            )

        return await query.prefetch_related("user").all()

    @classmethod
    async def get_user_tenants(
            cls,
            user: Union[int, User],
            include_expired: bool = False,
            include_unassigned: bool = False
    ) -> List["TenantUser"]:
        """
        获取用户所属的所有租户关联
        """
        user_id = user.id if isinstance(user, User) else user
        query = cls.objects.filter(
            user_id=user_id,
            is_deleted=False
        )

        if not include_unassigned:
            query = query.filter(is_assigned=True)
        if not include_expired:
            query = query.filter(
                cls.expired_at.is_null() | (cls.expired_at > utc_now())
            )

        return await query.prefetch_related("tenant").all()

    @classmethod
    async def has_user(
            cls,
            tenant: Union[int, Tenant],
            user: Union[int, User],
            check_valid: bool = True
    ) -> bool:
        """
        检查租户是否包含指定用户（以租户为主体）
        :param check_valid: 是否仅检查有效关联（已分配+未过期）
        """
        tenant_id = tenant.id if isinstance(tenant, Tenant) else tenant
        user_id = user.id if isinstance(user, User) else user

        query = cls.objects.filter(
            tenant_id=tenant_id,
            user_id=user_id,
            is_deleted=False
        )

        query = query.filter(
            Q(is_assigned=True) &
            (Q(expired_at__isnull=True) | Q(expired_at__gt=utc_now()))
        )

        return await query.exists()

    @classmethod
    async def set_primary_tenant(
            cls,
            user: Union[int, User],
            tenant: Union[int, Tenant]
    ) -> bool:
        """
        设置用户的主租户（以租户为主体）
        :return: 是否成功
        """
        user_obj = await User.objects.get(id=user) if isinstance(user, int) else user
        tenant_obj = await Tenant.objects.get(id=tenant) if isinstance(tenant, int) else tenant

        # 先检查关联是否存在，不存在则创建
        await cls.grant_user(tenant_obj, user_obj, is_primary=False)

        # 取消原有主租户
        await cls.objects.filter(
            user=user_obj,
            is_primary=True,
            is_deleted=False
        ).update(
            is_primary=False,
            updated_at=utc_now()
        )

        # 设置新主租户
        count = await cls.objects.filter(
            tenant=tenant_obj,
            user=user_obj,
            is_deleted=False
        ).update(
            is_primary=True,
            updated_at=utc_now()
        )

        return count > 0
