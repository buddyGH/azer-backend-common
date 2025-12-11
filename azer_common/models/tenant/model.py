import re
from typing import Dict, List, Optional, Union
from tortoise import fields
from tortoise.transactions import in_transaction
from azer_common.models.base import BaseModel
from azer_common.models.relations.tenant_user import TenantUser
from azer_common.models.user.model import User
from azer_common.utils.time import utc_now


class Tenant(BaseModel):
    """租户表 - 多租户体系的核心实体"""
    # 核心标识
    code = fields.CharField(
        max_length=64,
        unique=True,
        description='租户编码（唯一，如商家编号）'
    )
    name = fields.CharField(
        max_length=100,
        description='租户名称'
    )
    tenant_type = fields.CharField(
        max_length=32,
        default="normal",
        description='租户类型'
    )
    # 状态控制
    is_enabled = fields.BooleanField(
        default=True,
        description='租户是否启用（禁用后所有资源失效）'
    )
    is_system = fields.BooleanField(
        default=False,
        description='是否系统内置租户（不可删除）'
    )
    expired_at = fields.DatetimeField(
        null=True,
        description='租户过期时间（null表示永久有效）'
    )
    # 扩展信息
    contact = fields.CharField(
        max_length=50,
        null=True,
        description='联系人'
    )
    mobile = fields.CharField(
        max_length=15,
        null=True,
        description='联系电话'
    )
    config = fields.JSONField(
        null=True,
        description='租户配置（如权限策略）'
    )

    # 关联字段 - 租户-用户多对多（以租户为主体）
    users = fields.ManyToManyField(
        'models.User',
        related_name='tenants',
        through='azer_tenant_user',
        description='租户下的用户'
    )

    class Meta:
        table = "azer_tenant"
        table_description = '租户表'
        indexes = [("code", "is_enabled")]

    def __str__(self):
        return f"租户[{self.code}]：{self.name}"

    async def save(self, *args, **kwargs):
        """保存前执行验证逻辑，通过后调用父类save"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证租户数据合法性"""
        # 1. 系统租户特殊验证
        if self.is_system:
            # 系统租户不允许设置过期时间（永久有效）
            if self.expired_at is not None:
                raise ValueError("系统内置租户不允许设置过期时间（expired_at必须为null）")
            # 系统租户默认启用，禁止禁用
            if not self.is_enabled:
                raise ValueError("系统内置租户不允许禁用（is_enabled必须为True）")

        # 2. 租户编码格式验证
        if not self.code:
            raise ValueError("租户编码（code）不能为空")
        # 正则规则：小写字母、数字、下划线、中划线，以字母开头，长度1-64
        code_pattern = r'^[a-z][a-z0-9_\-]{0,63}$'
        if not re.match(code_pattern, self.code):
            raise ValueError(
                "租户编码（code）格式错误：必须以小写字母开头，仅包含小写字母、数字、下划线、中划线，长度1-64"
            )

        # 3. 过期时间合法性验证（如有值则校验）
        if self.expired_at is not None and self.expired_at <= utc_now():
            raise ValueError(f"租户过期时间（expired_at）不能早于当前时间：{self.expired_at}")

        # 4. 租户编码唯一性验证
        # 基础查询：匹配code，区分更新/新增场景
        query = self.__class__.objects.filter(code=self.code)

        # 5. 排除自身（更新场景）
        if self.id:
            query = query.exclude(id=self.id)

        # 检查是否存在重复
        existing_tenant = await query.first()
        if existing_tenant:
            delete_status = "（已软删除）" if existing_tenant.is_deleted else ""
            raise ValueError(
                f"租户编码（code）已存在{delete_status}：{self.code}，ID：{existing_tenant.id}"
            )

    # ========== 重写软删除方法（核心需求） ==========
    async def soft_delete(self):
        """
        重写软删除：先执行父类基础逻辑，再清理关联数据
        """
        # 系统内置租户禁止删除
        if self.is_system:
            raise ValueError("系统内置租户不允许删除")

        async with in_transaction() as conn:
            # 1. 先调用父类的 soft_delete 方法（标记 is_deleted/deleted_at）
            await super().soft_delete()

            # 2. 撤销该租户下所有用户关联（置为未分配）
            await TenantUser.objects.filter(
                tenant_id=self.id,
                is_assigned=True,
                is_deleted=False
            ).using_db(conn).update(
                is_assigned=False,
                updated_at=utc_now()
            )

            # 3. 禁用租户（额外标记）
            self.is_enabled = False
            await self.save(
                update_fields=["is_enabled", "updated_at"],
                using_db=conn
            )

        return self

    # ========== 租户-用户关联便捷方法 ==========
    async def assign_user(
            self,
            user: Union[int, User],
            is_primary: bool = False,
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> TenantUser:
        """
        给当前租户分配单个用户（以租户为主体）
        """
        return await TenantUser.grant_user(
            tenant=self,
            user=user,
            is_primary=is_primary,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    async def assign_users(
            self,
            users: List[Union[int, User]],
            is_primary: bool = False,
            expires_in_days: int = None,
            metadata: Optional[Dict] = None
    ) -> Dict[str, any]:
        """
        给当前租户批量分配用户
        """
        return await TenantUser.bulk_grant_users(
            tenant=self,
            users=users,
            is_primary=is_primary,
            expires_in_days=expires_in_days,
            metadata=metadata
        )

    async def revoke_user(self, user: Union[int, User]) -> bool:
        """
        撤销当前租户下的单个用户
        """
        return await TenantUser.revoke_user(tenant=self, user=user)

    async def revoke_users(self, users: List[Union[int, User]]) -> int:
        """
        批量撤销当前租户下的用户
        """
        return await TenantUser.bulk_revoke_users(tenant=self, users=users)

    async def get_users(
            self,
            include_expired: bool = False,
            include_unassigned: bool = False
    ) -> List[User]:
        """
        获取当前租户下的所有用户
        """
        tenant_users = await TenantUser.get_tenant_users(
            tenant=self,
            include_expired=include_expired,
            include_unassigned=include_unassigned
        )
        return [tu.user for tu in tenant_users]

    async def has_user(self, user: Union[int, User], check_valid: bool = True) -> bool:
        """
        检查当前租户是否包含指定用户
        """
        return await TenantUser.has_user(tenant=self, user=user, check_valid=check_valid)

    async def set_user_primary_tenant(self, user: Union[int, User]) -> bool:
        """
        将当前租户设为指定用户的主租户
        """
        return await TenantUser.set_primary_tenant(user=user, tenant=self)
