# azer_common/repositories/user/components/base.py
from datetime import date
from typing import Any, Dict, Optional, Tuple

from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from azer_common.models.user.model import User
from azer_common.repositories.base_component import BaseComponent


class UserBaseComponent(BaseComponent):
    """用户组件基础组件"""

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

    async def get_with_credential(self, user_id: str) -> Optional[User]:
        """
        获取用户并关联认证凭证信息（密码/验证码/第三方登录等）
        :param user_id: 用户ID
        :return: 包含认证凭证的用户实例/None
        """
        # 关联查询用户认证凭证（一对一关系）
        user = await self.model.filter(id=user_id, is_deleted=False).select_related(
            "credential"  # 关联UserCredential模型（外键关联User）
        ).first()
        return user

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

    async def update_avatar(self, user_id: str, avatar_url: Optional[str]) -> Optional[User]:
        """
        单独更新用户头像（精细化控制，支持清空头像）
        :param user_id: 用户ID
        :param avatar_url: 头像URL（None/空字符串表示清空）
        :return: 更新后的用户实例/None
        """
        async with in_transaction():
            user = await self.get_by_id(user_id)
            if not user:
                return None

            # 系统用户限制修改头像
            if await self.is_user_system(user_id):
                raise ValueError("系统用户不允许修改头像")

            # 校验头像URL格式（非清空场景）
            if avatar_url is not None and avatar_url.strip() != "":
                user.avatar = avatar_url.strip()
            else:
                user.avatar = None

            await user.save(update_fields=["avatar", "updated_at"])
            return user

    async def update_nickname(self, user_id: str, nick_name: str) -> Optional[User]:
        """
        单独更新用户昵称（强化格式/长度校验）
        :param user_id: 用户ID
        :param nick_name: 新昵称（非空）
        :return: 更新后的用户实例/None
        """
        async with in_transaction():
            user = await self.get_by_id(user_id)
            if not user:
                return None

            # 系统用户限制修改昵称
            if await self.is_user_system(user_id):
                raise ValueError("系统用户不允许修改昵称")

            # 更新昵称（自动触发display_name重新计算）
            user.nick_name = nick_name
            await user.save(update_fields=["nick_name", "updated_at"])
            return user

    async def update_profile(
            self,
            user_id: str,
            nick_name: Optional[str] = None,
            avatar: Optional[str] = None,
            desc: Optional[str] = None,
            home_path: Optional[str] = None,
            sex: Optional[Any] = None
    ) -> Optional[User]:
        """
        更新用户基础资料（非敏感、非身份类信息）
        :param user_id: 用户ID
        :param nick_name: 昵称
        :param avatar: 头像URL（自动验证格式）
        :param desc: 个人简介
        :param home_path: 个人主页路径
        :param sex: 性别（需符合SexEnum枚举值）
        :return: 更新后的用户实例/None
        """
        async with in_transaction():
            user = await self.get_by_id(user_id)
            if not user:
                return None

            # 系统用户限制修改核心资料
            if await self.is_user_system(user_id):
                raise ValueError("系统用户不允许修改个人资料")

            # 验证头像URL格式
            if avatar is not None:
                if avatar.strip() == "":
                    user.avatar = None
                else:
                    user.avatar = avatar

            # 批量更新字段（仅传入非None的值）
            update_fields = []
            if nick_name is not None:
                user.nick_name = nick_name
                update_fields.append("nick_name")
            if desc is not None:
                user.desc = desc
                update_fields.append("desc")
            if home_path is not None:
                user.home_path = home_path
                update_fields.append("home_path")
            if sex is not None:
                user.sex = sex
                update_fields.append("sex")
            if avatar is not None:
                update_fields.append("avatar")

            if update_fields:
                await user.save(update_fields=update_fields + ["updated_at"])

            return user

    async def update_contact_info(
            self,
            user_id: str,
            mobile: Optional[str] = None,
            email: Optional[str] = None
    ) -> Optional[User]:
        """
        更新用户联系信息（手机号/邮箱，强制唯一性校验）
        :param user_id: 用户ID
        :param mobile: 手机号
        :param email: 邮箱
        :return: 更新后的用户实例/None
        """
        async with in_transaction():
            user = await self.get_by_id(user_id)
            if not user:
                return None

            # 系统用户限制修改联系信息
            if await self.is_user_system(user_id):
                raise ValueError("系统用户不允许修改联系信息")

            update_fields = []
            # 手机号更新（含唯一性校验）
            if mobile is not None:
                if mobile.strip() == "":
                    user.mobile = None
                    update_fields.append("mobile")
                else:
                    # 检查手机号是否已被其他用户占用
                    exists = await self.model.filter(
                        mobile=mobile,
                        is_deleted=False
                    ).exclude(id=user_id).exists()
                    if exists:
                        raise ValueError(f"手机号{mobile}已被其他用户使用")
                    user.mobile = mobile
                    update_fields.append("mobile")

            # 邮箱更新（含唯一性校验）
            if email is not None:
                if email.strip() == "":
                    user.email = None
                    update_fields.append("email")
                else:
                    # 检查邮箱是否已被其他用户占用
                    exists = await self.model.filter(
                        email=email,
                        is_deleted=False
                    ).exclude(id=user_id).exists()
                    if exists:
                        raise ValueError(f"邮箱{email}已被其他用户使用")
                    user.email = email
                    update_fields.append("email")

            if update_fields:
                await user.save(update_fields=update_fields + ["updated_at"])

            return user

    async def update_personal_info(
            self,
            user_id: str,
            real_name: Optional[str] = None,
            identity_card: Optional[str] = None,
            birth_date: Optional[date] = None
    ) -> Optional[User]:
        """
        更新用户身份信息（姓名/身份证号/生日，身份证号需唯一性校验）
        :param user_id: 用户ID
        :param real_name: 真实姓名
        :param identity_card: 身份证号（自动验证格式）
        :param birth_date: 出生日期
        :return: 更新后的用户实例/None
        """
        async with in_transaction():
            user = await self.get_by_id(user_id)
            if not user:
                return None

            # 系统用户限制修改身份信息
            if await self.is_user_system(user_id):
                raise ValueError("系统用户不允许修改身份信息")

            update_fields = []
            # 真实姓名更新
            if real_name is not None:
                user.real_name = real_name
                update_fields.append("real_name")

            # 身份证号更新（唯一性校验）
            if identity_card is not None:
                if identity_card.strip() == "":
                    user.identity_card = None
                    update_fields.append("identity_card")
                else:
                    exists = await self.model.filter(
                        identity_card=identity_card,
                        is_deleted=False
                    ).exclude(id=user_id).exists()
                    if exists:
                        raise ValueError(f"身份证号{identity_card}已被其他用户使用")
                    user.identity_card = identity_card
                    update_fields.append("identity_card")

            # 出生日期更新
            if birth_date is not None:
                user.birth_date = birth_date
                update_fields.append("birth_date")

            if update_fields:
                await user.save(update_fields=update_fields + ["updated_at"])

            return user

    async def update_preferences(
            self,
            user_id: str,
            preferences: Dict[str, Any],
            merge: bool = True
    ) -> Optional[User]:
        """
        更新用户偏好设置（JSON字段，支持合并/覆盖）
        :param user_id: 用户ID
        :param preferences: 偏好设置字典
        :param merge: 是否合并现有设置（True: 合并，False: 覆盖）
        :return: 更新后的用户实例/None
        """
        async with in_transaction():
            user = await self.get_by_id(user_id)
            if not user:
                return None

            # 系统用户限制修改偏好（可选，根据业务需求调整）
            if await self.is_user_system(user_id):
                raise ValueError("系统用户不允许修改偏好设置")

            # 处理偏好设置（合并/覆盖）
            current_preferences = user.preferences or {}
            if merge:
                current_preferences.update(preferences)
                user.preferences = current_preferences
            else:
                user.preferences = preferences

            await user.save(update_fields=["preferences", "updated_at"])
            return user

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
