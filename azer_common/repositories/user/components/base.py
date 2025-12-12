# azer_common/repositories/user/components/base.py
from typing import Optional, Tuple

from tortoise.expressions import Q

from azer_common.models.user.model import User
from azer_common.repositories.base_component import BaseComponent


class UserBaseComponent(BaseComponent):
    """用户组件基类 - 提供公共方法和属性"""

    # ========== 基础查询方法 ==========
    async def get_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return await self.get_by_field('username', username)

    async def get_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        return await self.get_by_field('email', email)

    async def get_by_mobile(self, mobile: str) -> Optional[User]:
        """根据手机号获取用户"""
        return await self.get_by_field('mobile', mobile)

    async def get_by_identity_card(self, identity_card: str) -> Optional[User]:
        """根据身份证号获取用户"""
        return await self.get_by_field('identity_card', identity_card)

    # ========== 存在性检查 ==========
    async def check_username_exists(self, username: str, exclude_user_id: str = None) -> bool:
        """检查用户名是否存在"""
        query = self.query.filter(username=username)
        if exclude_user_id:
            query = query.exclude(id=exclude_user_id)
        return await query.exists()

    async def check_email_exists(self, email: str, exclude_user_id: str = None) -> bool:
        """检查邮箱是否存在"""
        query = self.query.filter(email=email)
        if exclude_user_id:
            query = query.exclude(id=exclude_user_id)
        return await query.exists()

    async def check_mobile_exists(self, mobile: str, exclude_user_id: str = None) -> bool:
        """检查手机号是否存在"""
        query = self.query.filter(mobile=mobile)
        if exclude_user_id:
            query = query.exclude(id=exclude_user_id)
        return await query.exists()

    async def check_identity_info_exists(
            self,
            identity_card: Optional[str] = None,
            real_name: Optional[str] = None,
            require_both_match: bool = True,
            exclude_user_id: Optional[str] = None
    ) -> Tuple[bool, Optional[User]]:
        """
        检查身份信息是否已存在
        :param identity_card: 身份证号（可选）
        :param real_name: 真实姓名（可选）
        :param require_both_match: 是否需要同时匹配身份证号和真实姓名
        :param exclude_user_id: 排除的用户ID
        :return: (是否存在, 匹配到的用户对象)
        """
        query = self.query

        if require_both_match:
            # 需要同时匹配
            if identity_card:
                query = query.filter(identity_card=identity_card)
            if real_name:
                query = query.filter(real_name=real_name)

            if not (identity_card or real_name):
                return False, None
        else:
            if identity_card or real_name:
                q_obj = Q()
                if identity_card:
                    q_obj |= Q(identity_card=identity_card)
                if real_name:
                    q_obj |= Q(real_name=real_name)
                query = query.filter(q_obj)
            else:
                return False, None

        if exclude_user_id:
            query = query.exclude(id=exclude_user_id)

        user = await query.first()
        return user is not None, user

    async def is_user_system(self, user_id: str) -> bool:
        """
        检查用户是否为系统用户（系统用户不可删除/修改关键信息）
        :param user_id: 用户ID
        :return: 是系统用户返回True，否则False
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False
        return hasattr(user, 'is_system') and user.is_system

    async def is_user_active(self, user_id: str) -> bool:
        """
        检查用户是否处于活跃状态（状态正常且无安全限制）
        :param user_id: 用户ID
        :return: 活跃返回True，否则False
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False
        return user.is_active

    async def is_user_blocked(self, user_id: str) -> bool:
        """
        检查用户是否被限制（冻结/封禁等安全限制）
        :param user_id: 用户ID
        :return: 被限制返回True，否则False
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False
        return user.is_blocked

    async def get_display_name(self, user_id: str) -> Optional[str]:
        """
        获取用户显示名称（优先级：真实姓名 > 昵称 > 用户名）
        :param user_id: 用户ID
        :return: 显示名称/None
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None
        return user.display_name

    async def get_user_age(self, user_id: str) -> Optional[int]:
        """
        获取用户年龄（基于生日计算）
        :param user_id: 用户ID
        :return: 年龄/None（无生日时返回None）
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None
        return user.age
