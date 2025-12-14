import re
from typing import List

from async_property import async_property
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.models.role.model import Role
from azer_common.utils.time import utc_now


class Tenant(BaseModel):
    """租户表，存储多租户体系下的租户核心信息"""

    # 核心标识字段
    code = fields.CharField(
        max_length=64, unique=True, description="租户编码（全局唯一，小写字母/数字/下划线/中划线，以字母开头）"
    )
    name = fields.CharField(max_length=100, description="租户名称")
    tenant_type = fields.CharField(max_length=32, default="normal", description="租户类型（业务自定义分类）")

    # 状态控制字段
    is_enabled = fields.BooleanField(default=True, description="租户是否启用（禁用后租户下所有资源失效）")
    is_system = fields.BooleanField(default=False, description="是否系统内置租户（不可删除、禁用、设置过期时间）")
    expired_at = fields.DatetimeField(null=True, description="租户过期时间（null表示永久有效）")

    # 反向关联字段
    roles: fields.ReverseRelation[Role]

    # 扩展信息字段
    contact = fields.CharField(max_length=50, null=True, description="租户联系人")
    mobile = fields.CharField(max_length=15, null=True, description="租户联系电话")
    config = fields.JSONField(null=True, description="租户自定义配置（如权限策略、功能开关）")

    class Meta:
        table = "azer_tenant"
        table_description = "租户表"
        indexes = [("code", "is_enabled")]

    class PydanticMeta:
        include = {
            "users": {"id", "username", "display_name"},
        }

    def __str__(self):
        """租户实例的字符串表示"""
        return f"租户[{self.code}]：{self.name}"

    async def save(self, *args, **kwargs):
        """保存租户前执行数据验证，验证通过后调用父类保存方法"""
        await self.validate()
        await super().save(*args, **kwargs)

    async def validate(self):
        """验证租户数据合法性"""
        # 系统租户校验
        if self.is_system:
            if self.expired_at is not None:
                raise ValueError("系统内置租户不允许设置过期时间（expired_at必须为null）")
            if not self.is_enabled:
                raise ValueError("系统内置租户不允许禁用（is_enabled必须为True）")

        # 编码非空+格式校验
        if not self.code:
            raise ValueError("租户编码（code）不能为空")
        code_pattern = r"^[a-z][a-z0-9_\-]{0,63}$"
        if not re.match(code_pattern, self.code):
            raise ValueError("租户编码格式错误：必须以小写字母开头，仅包含小写字母、数字、下划线、中划线，长度1-64")

        # 过期时间校验
        if self.expired_at is not None and self.expired_at <= utc_now():
            raise ValueError(f"租户过期时间不能早于当前时间：{self.expired_at}")

        # 编码唯一性校验
        query = self.__class__.all_objects.filter(code=self.code)
        if self.id:
            query = query.exclude(id=self.id)
        existing_tenant = await query.first()
        if existing_tenant:
            delete_status = "（已软删除）" if existing_tenant.is_deleted else ""
            raise ValueError(f"租户编码已存在{delete_status}：{self.code}，ID：{existing_tenant.id}")

    async def soft_delete(self):
        """软删除租户，系统租户禁止删除"""
        if self.is_system:
            raise ValueError("系统内置租户不允许删除")
        self.is_deleted = True
        self.is_enabled = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_enabled"])
        return self

    async def enable(self):
        """启用租户"""
        self.is_enabled = True
        await self.save(update_fields=["is_enabled", "updated_at"])

    async def disable(self):
        """禁用租户，系统租户禁止禁用"""
        if self.is_system:
            raise ValueError("系统内置租户不允许禁用")
        self.is_enabled = False
        await self.save(update_fields=["is_enabled", "updated_at"])

    @async_property
    async def enabled_roles(self) -> List[Role]:
        """
        异步属性：获取当前租户所有启用的角色
        调用方式：await tenant.enabled_roles
        """
        return await self.roles.filter(is_enabled=True)

    @async_property
    async def all_roles(self) -> List[Role]:
        """
        异步属性：获取当前租户所有角色
        调用：await tenant.all_roles
        """
        return await self.roles.all()
