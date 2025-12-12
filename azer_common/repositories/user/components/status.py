# azer_common/repositories/user/components/status.py
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from tortoise.transactions import in_transaction
from azer_common.models.enums.base import UserLifecycleStatus, UserSecurityStatus
from azer_common.models.user.model import User
from azer_common.repositories.base_component import BaseComponent
from azer_common.repositories.user.status import UserStatusTransitions
from azer_common.utils.time import utc_now


class UserStatusComponent(BaseComponent):


    async def filter_by_status(
            self,
            status: UserLifecycleStatus,
            tenant_id: Optional[str] = None,
            include_blocked: bool = False,
            offset: int = 0,
            limit: int = 20,
            order_by: str = "-created_at"
    ) -> Tuple[List[User], int]:
        """
        按生命周期状态过滤用户（替代原get_users_by_lifecycle_status）
        :param status: 生命周期状态
        :param tenant_id: 租户ID（可选）
        :param include_blocked: 是否包含被安全限制的用户
        :param offset: 分页偏移量
        :param limit: 分页大小
        :param order_by: 排序字段
        :return: (用户列表, 总数量)
        """
        query = self.model.filter(
            status=status,
            is_deleted=False
        )

        if not include_blocked:
            query = query.filter(security_status__isnull=True)

        if tenant_id:
            query = query.filter(tenants__id=tenant_id)

        # 优化：先count再分页，避免重复查询
        total = await query.count()
        users = await query.distinct().offset(offset).limit(limit).order_by(order_by)

        return users, total

    async def filter_by_security_status(
            self,
            security_status: UserSecurityStatus,
            tenant_id: Optional[str] = None,
            offset: int = 0,
            limit: int = 20,
            order_by: str = "-created_at"
    ) -> Tuple[List[User], int]:
        """
        按安全状态过滤用户（替代原get_users_by_security_status）
        :param security_status: 安全状态
        :param tenant_id: 租户ID（可选）
        :param offset: 分页偏移量
        :param limit: 分页大小
        :param order_by: 排序字段
        :return: (用户列表, 总数量)
        """
        query = self.model.filter(
            security_status=security_status,
            is_deleted=False
        )

        if tenant_id:
            query = query.filter(tenants__id=tenant_id)

        total = await query.count()
        users = await query.distinct().offset(offset).limit(limit).order_by(order_by)

        return users, total

    # ========== 状态检查方法 ==========
    async def is_user_active(self, user_id: str) -> bool:
        """检查用户是否可用（活跃且无限制）"""
        user = await self.get_by_id(user_id)
        if not user:
            return False

        return user.is_active

    async def is_user_blocked(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        检查用户是否被阻止
        :return: (是否被阻止, 阻止类型)
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False, None

        if user.security_status:
            return True, user.security_status.value

        return False, None

    async def check_user_status_transition(
            self,
            user_id: str,
            new_status: UserLifecycleStatus
    ) -> Tuple[bool, Optional[str]]:
        """
        检查用户是否可以转换到新状态
        :param user_id: 用户ID
        :param new_status: 目标状态
        :return: (是否允许, 错误信息)
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False, "用户不存在"

        if UserStatusTransitions.can_transition(user.status, new_status):
            return True, None

        return False, f"不允许从 {user.status.value} 转换到 {new_status.value}"

    async def get_user_allowed_transitions(self, user_id: str) -> Set[UserLifecycleStatus]:
        """获取用户允许的所有状态转换"""
        user = await self.get_by_id(user_id)
        if not user:
            return set()

        return UserStatusTransitions.get_allowed_transitions(user.status)

    # ========== 状态转换方法（核心业务逻辑） ==========

    async def activate_user(
            self,
            user_id: str,
            verified_email: bool = True,
            verified_mobile: bool = True,
            reason: Optional[str] = None,
            operator_id: Optional[str] = None
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        激活用户
        :param user_id: 用户ID
        :param verified_email: 是否验证邮箱
        :param verified_mobile: 是否验证手机
        :param reason: 操作原因
        :param operator_id: 操作者ID
        :return: (是否成功, 用户对象, 错误信息)
        """
        async with in_transaction():
            user = await self.model.filter(id=user_id, is_deleted=False).first()
            if not user:
                return False, None, "用户不存在"

            # 检查状态转换是否允许
            if not UserStatusTransitions.can_transition(
                    user.status, UserLifecycleStatus.ACTIVE
            ):
                return False, None, f"不允许从 {user.status.value} 激活"

            # 记录旧状态
            old_status = user.status

            # 更新状态
            user.status = UserLifecycleStatus.ACTIVE
            user.security_status = None  # 清除安全状态

            # 设置时间戳
            now = utc_now()
            user.activated_at = now
            user.last_active_at = now

            # 更新metadata记录状态变更
            await self._record_status_change(
                user=user,
                old_status=old_status,
                new_status=UserLifecycleStatus.ACTIVE,
                reason=reason,
                operator_id=operator_id,
                verified_email=verified_email,
                verified_mobile=verified_mobile
            )

            await user.save()
            return True, user, None

    async def freeze_user(
            self,
            user_id: str,
            reason: str,
            days: Optional[int] = None,
            operator_id: Optional[str] = None
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        冻结用户（设置安全状态）
        :param user_id: 用户ID
        :param reason: 冻结原因
        :param days: 冻结天数（None表示永久）
        :param operator_id: 操作者ID
        :return: (是否成功, 用户对象, 错误信息)
        """
        async with in_transaction():
            user = await self.model.filter(id=user_id, is_deleted=False).first()
            if not user:
                return False, None, "用户不存在"

            # 检查当前状态是否可以冻结
            # 冻结是设置安全状态，不改变生命周期状态
            if not user.status == UserLifecycleStatus.ACTIVE:
                return False, None, "只能冻结ACTIVE状态的用户"

            if user.security_status:
                return False, None, f"用户已被{user.security_status.value}，无法重复冻结"

            # 记录旧安全状态
            old_security_status = user.security_status

            # 更新安全状态
            user.security_status = UserSecurityStatus.FROZEN
            user.frozen_at = utc_now()

            # 更新metadata记录状态变更
            await self._record_security_status_change(
                user=user,
                old_security_status=old_security_status,
                new_security_status=UserSecurityStatus.FROZEN,
                reason=reason,
                operator_id=operator_id,
                days=days
            )

            # 设置预期解冻时间
            if days:
                expected_unfreeze = utc_now() + timedelta(days=days)
                if not user.metadata:
                    user.metadata = {}
                user.metadata["expected_unfreeze"] = expected_unfreeze.isoformat()

            await user.save()
            return True, user, None

    async def unfreeze_user(
            self,
            user_id: str,
            reason: str,
            operator_id: Optional[str] = None
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        解冻用户
        :param user_id: 用户ID
        :param reason: 解冻原因
        :param operator_id: 操作者ID
        :return: (是否成功, 用户对象, 错误信息)
        """
        async with in_transaction():
            user = await self.model.filter(id=user_id, is_deleted=False).first()
            if not user:
                return False, None, "用户不存在"

            if user.security_status != UserSecurityStatus.FROZEN:
                return False, None, "用户未被冻结，无法解冻"

            # 记录旧安全状态
            old_security_status = user.security_status

            # 清除安全状态
            user.security_status = None
            user.frozen_at = None

            # 更新metadata记录状态变更
            await self._record_security_status_change(
                user=user,
                old_security_status=old_security_status,
                new_security_status=None,
                reason=reason,
                operator_id=operator_id
            )

            # 清除预期解冻时间
            if user.metadata and "expected_unfreeze" in user.metadata:
                del user.metadata["expected_unfreeze"]

            await user.save()
            return True, user, None

    async def ban_user(
            self,
            user_id: str,
            reason: str,
            permanent: bool = True,
            operator_id: Optional[str] = None
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        封禁用户
        :param user_id: 用户ID
        :param reason: 封禁原因
        :param permanent: 是否永久封禁
        :param operator_id: 操作者ID
        :return: (是否成功, 用户对象, 错误信息)
        """
        async with in_transaction():
            user = await self.model.filter(id=user_id, is_deleted=False).first()
            if not user:
                return False, None, "用户不存在"

            # 检查状态转换是否允许
            if not UserStatusTransitions.can_transition(
                    user.status, UserLifecycleStatus.ACTIVE
            ):
                return False, None, f"不允许从 {user.status.value} 封禁"

            # 记录旧安全状态
            old_security_status = user.security_status

            # 更新安全状态
            user.security_status = UserSecurityStatus.BANNED
            user.banned_at = utc_now()

            # 更新metadata记录状态变更
            await self._record_security_status_change(
                user=user,
                old_security_status=old_security_status,
                new_security_status=UserSecurityStatus.BANNED,
                reason=reason,
                operator_id=operator_id,
                permanent=permanent
            )

            await user.save()
            return True, user, None

    async def close_user_account(
            self,
            user_id: str,
            reason: str = "user_request",
            operator_id: Optional[str] = None
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        注销用户账户
        :param user_id: 用户ID
        :param reason: 注销原因
        :param operator_id: 操作者ID
        :return: (是否成功, 用户对象, 错误信息)
        """
        async with in_transaction():
            user = await self.model.filter(id=user_id, is_deleted=False).first()
            if not user:
                return False, None, "用户不存在"

            # 检查状态转换是否允许
            if not UserStatusTransitions.can_transition(
                    user.status, UserLifecycleStatus.CLOSED
            ):
                return False, None, f"不允许从 {user.status.value} 注销"

            # 记录旧状态
            old_status = user.status

            # 更新状态
            user.status = UserLifecycleStatus.CLOSED
            user.security_status = None  # 清除安全状态
            user.closed_at = utc_now()

            # 更新metadata记录状态变更
            await self._record_status_change(
                user=user,
                old_status=old_status,
                new_status=UserLifecycleStatus.CLOSED,
                reason=reason,
                operator_id=operator_id
            )

            await user.save()
            return True, user, None

    async def mark_user_inactive(
            self,
            user_id: str,
            reason: str = "inactivity",
            operator_id: Optional[str] = None
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        标记用户为不活跃（自动或手动）
        :param user_id: 用户ID
        :param reason: 原因
        :param operator_id: 操作者ID
        :return: (是否成功, 用户对象, 错误信息)
        """
        async with in_transaction():
            user = await self.model.filter(id=user_id, is_deleted=False).first()
            if not user:
                return False, None, "用户不存在"

            # 检查状态转换是否允许
            if not UserStatusTransitions.can_transition(
                    user.status, UserLifecycleStatus.INACTIVE
            ):
                return False, None, f"不允许从 {user.status.value} 标记为不活跃"

            # 记录旧状态
            old_status = user.status

            # 更新状态
            user.status = UserLifecycleStatus.INACTIVE

            # 更新metadata记录状态变更
            await self._record_status_change(
                user=user,
                old_status=old_status,
                new_status=UserLifecycleStatus.INACTIVE,
                reason=reason,
                operator_id=operator_id
            )

            await user.save()
            return True, user, None

    async def update_user_last_active(
            self,
            user_id: str,
            force_reactive: bool = True
    ) -> bool:
        """
        更新用户最后活跃时间（登录/操作时调用）
        :param user_id: 用户ID
        :param force_reactive: 如果是不活跃状态，是否自动重新激活
        :return: 是否成功
        """
        async with in_transaction():
            user = await self.model.filter(id=user_id, is_deleted=False).first()
            if not user:
                return False

            # 如果用户处于INACTIVE状态且force_reactive为True，尝试重新激活
            if force_reactive and user.status == UserLifecycleStatus.INACTIVE:
                if UserStatusTransitions.can_transition(
                        user.status, UserLifecycleStatus.ACTIVE
                ):
                    user.status = UserLifecycleStatus.ACTIVE

            # 更新最后活跃时间
            user.last_active_at = utc_now()

            await user.save()
            return True

    async def review_user_application(
            self,
            user_id: str,
            approved: bool,
            reason: Optional[str] = None,
            operator_id: Optional[str] = None
    ) -> Tuple[bool, Optional[User], Optional[str]]:
        """
        审核用户申请（从PENDING状态）
        :param user_id: 用户ID
        :param approved: 是否通过
        :param reason: 审核意见
        :param operator_id: 操作者ID
        :return: (是否成功, 用户对象, 错误信息)
        """
        async with in_transaction():
            user = await self.model.filter(id=user_id, is_deleted=False).first()
            if not user:
                return False, None, "用户不存在"

            if user.status != UserLifecycleStatus.PENDING:
                return False, None, "用户不在待审核状态"

            # 记录旧状态
            old_status = user.status

            if approved:
                # 审核通过，激活用户
                new_status = UserLifecycleStatus.ACTIVE
                user.activated_at = utc_now()
                user.last_active_at = utc_now()
            else:
                # 审核不通过，冻结用户
                new_status = UserLifecycleStatus.ACTIVE  # 生命周期状态不变
                user.security_status = UserSecurityStatus.FROZEN
                user.frozen_at = utc_now()

            user.status = new_status

            # 更新metadata记录审核结果
            await self._record_status_change(
                user=user,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
                operator_id=operator_id,
                approved=approved
            )

            await user.save()
            return True, user, None

    # ========== 批量状态操作 ==========

    async def batch_mark_inactive(
            self,
            user_ids: List[str],
            reason: str = "batch_inactivity",
            operator_id: Optional[str] = None
    ) -> Tuple[int, List[str]]:
        """
        批量标记为不活跃
        :param user_ids: 用户ID列表
        :param reason: 原因
        :param operator_id: 操作者ID
        :return: (成功数量, 失败的用户ID列表)
        """
        if not user_ids:
            return 0, []

        success_count = 0
        failed_ids = []

        for user_id in user_ids:
            try:
                success, _, error = await self.mark_user_inactive(
                    user_id=user_id,
                    reason=reason,
                    operator_id=operator_id
                )
                if success:
                    success_count += 1
                else:
                    failed_ids.append(user_id)
            except Exception:
                failed_ids.append(user_id)

        return success_count, failed_ids

    async def batch_freeze_users(
            self,
            user_ids: List[str],
            reason: str,
            days: Optional[int] = None,
            operator_id: Optional[str] = None
    ) -> Tuple[int, List[str]]:
        """
        批量冻结用户
        :param user_ids: 用户ID列表
        :param reason: 冻结原因
        :param days: 冻结天数
        :param operator_id: 操作者ID
        :return: (成功数量, 失败的用户ID列表)
        """
        if not user_ids:
            return 0, []

        success_count = 0
        failed_ids = []

        for user_id in user_ids:
            try:
                success, _, error = await self.freeze_user(
                    user_id=user_id,
                    reason=reason,
                    days=days,
                    operator_id=operator_id
                )
                if success:
                    success_count += 1
                else:
                    failed_ids.append(user_id)
            except Exception:
                failed_ids.append(user_id)

        return success_count, failed_ids

    async def get_user_status_history(
            self,
            user_id: str,
            limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取用户状态变更历史
        :param user_id: 用户ID
        :param limit: 返回数量限制
        :return: 状态变更历史列表
        """
        user = await self.get_by_id(user_id)
        if not user or not user.metadata:
            return []

        history = []

        # 从metadata中提取状态变更历史
        if "status_changes" in user.metadata:
            history.extend(user.metadata["status_changes"])

        if "security_status_changes" in user.metadata:
            history.extend(user.metadata["security_status_changes"])

        # 按时间排序
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return history[:limit]

    # ========== 内部辅助方法 ==========

    async def _record_status_change(
            self,
            user: User,
            old_status: UserLifecycleStatus,
            new_status: UserLifecycleStatus,
            reason: Optional[str] = None,
            operator_id: Optional[str] = None,
            **extra_info
    ) -> None:
        """记录生命周期状态变更"""
        if not user.metadata:
            user.metadata = {}

        if "status_changes" not in user.metadata:
            user.metadata["status_changes"] = []

        change_record = {
            "timestamp": utc_now().isoformat(),
            "old_status": old_status.value,
            "new_status": new_status.value,
            "reason": reason,
            "operator_id": operator_id,
            **extra_info
        }

        user.metadata["status_changes"].append(change_record)

        # 限制历史记录数量
        if len(user.metadata["status_changes"]) > 100:
            user.metadata["status_changes"] = user.metadata["status_changes"][-50:]

    async def _record_security_status_change(
            self,
            user: User,
            old_security_status: Optional[UserSecurityStatus],
            new_security_status: Optional[UserSecurityStatus],
            reason: Optional[str] = None,
            operator_id: Optional[str] = None,
            **extra_info
    ) -> None:
        """记录安全状态变更"""
        if not user.metadata:
            user.metadata = {}

        if "security_status_changes" not in user.metadata:
            user.metadata["security_status_changes"] = []

        change_record = {
            "timestamp": utc_now().isoformat(),
            "old_status": old_security_status.value if old_security_status else None,
            "new_status": new_security_status.value if new_security_status else None,
            "reason": reason,
            "operator_id": operator_id,
            **extra_info
        }

        user.metadata["security_status_changes"].append(change_record)

        # 限制历史记录数量
        if len(user.metadata["security_status_changes"]) > 100:
            user.metadata["security_status_changes"] = user.metadata["security_status_changes"][-50:]
