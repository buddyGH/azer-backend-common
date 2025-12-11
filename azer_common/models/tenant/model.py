import re
from tortoise import fields
from azer_common.models.base import BaseModel
from azer_common.utils.time import utc_now


class Tenant(BaseModel):
    """租户表"""
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

    # 关联字段
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

        # 3. 过期时间合法性验证
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

    async def soft_delete(self):
        if self.is_system:
            raise ValueError("系统内置角色不允许删除")
        self.is_deleted = True
        self.is_enabled = False
        await self.save(update_fields=["is_deleted", "deleted_at", "is_enabled"])
        return self
