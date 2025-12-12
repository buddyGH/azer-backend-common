import hashlib
from typing import Optional

from user_agents import parse


class DeviceFingerprintUtil:
    """
    设备指纹工具类，用于解析 User-Agent 并生成设备指纹。
    """

    @staticmethod
    def extract_device_info(user_agent_str: Optional[str]) -> str:
        """
        从 User-Agent 中提取设备、操作系统和浏览器的简化信息。

        :param user_agent_str: User-Agent 字符串
        :return: 简化的设备信息字符串，如 "iPhone-iOS-Safari"
        """
        if not user_agent_str:
            return "unknown"

        user_agent = parse(user_agent_str)
        return f"{user_agent.device.family}-{user_agent.os.family}-{user_agent.browser.family}"

    @staticmethod
    def generate_fingerprint(user_agent_str: str) -> str:
        """
        根据设备信息生成唯一且稳定的设备指纹。

        :param user_agent_str: User-Agent 字符串
        :return: 设备指纹的 SHA256 哈希值
        """
        # 提取设备信息
        dev_info = DeviceFingerprintUtil.extract_device_info(user_agent_str)

        # 组合设备信息和随机 ID 生成唯一指纹
        fingerprint_source = f"{dev_info}"
        buffer = fingerprint_source.encode("utf-8")

        # 生成 SHA256 哈希值
        return hashlib.sha256(buffer).hexdigest()  # type: ignore
