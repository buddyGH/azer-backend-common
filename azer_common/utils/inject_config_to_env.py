import os
from typing import Dict
from pydantic_settings import BaseSettings


def inject_config_to_env(
    config_instance: BaseSettings, parent_prefix: str = "", skip_existing: bool = True
) -> Dict[str, str]:
    """
    优先级：子类 env_prefix > config_key 生成的前缀 > 父前缀
    规则：仅注入不存在的环境变量、跳过ClassVar/私有字段/None值

    Args:
        config_instance: 已实例化的 BaseSettings 配置对象
        parent_prefix: 父级前缀（用于嵌套配置，如 TORTOISE_MASTER__）
        skip_existing: 是否跳过已存在的环境变量（True=仅注入不存在的）

    Returns:
        已设置的环境变量字典
    """
    # 校验输入：必须是 BaseSettings 实例
    if not isinstance(config_instance, BaseSettings):
        raise TypeError(f"config_instance 必须是 BaseSettings 实例，当前类型：{type(config_instance)}")

    # 1. 确定当前层级的前缀（优先级：env_prefix > config_key > 父前缀）
    current_prefix = parent_prefix
    # 优先取 model_config 中的 env_prefix（兼容 SettingsConfigDict 对象）
    model_config = getattr(config_instance.__class__, "model_config", {})
    env_prefix = getattr(model_config, "env_prefix", "").upper()  # 优化：用 getattr 兼容对象
    if env_prefix:
        current_prefix = env_prefix
    # 若无 env_prefix，尝试从 config_key 生成（兼容无 config_key 的嵌套类）
    elif hasattr(config_instance, "config_key") and config_instance.config_key:
        current_prefix = f"{config_instance.config_key.upper()}_"

    # 2. 遍历当前实例的所有字段（排除 ClassVar）
    injected_envs = {}
    fields = config_instance.model_fields
    for field_name, field_info in fields.items():
        # 跳过私有字段、ClassVar 字段
        if field_name.startswith("_"):
            continue

        # 读取字段的最终值（实例化后的值，含 __init__ 重写/验证器修改后的值）
        field_value = getattr(config_instance, field_name)

        # 3. 处理嵌套配置实例（递归注入）
        if isinstance(field_value, BaseSettings):
            # 读取子配置类的嵌套分隔符（而非父类，更符合语义）
            nested_delimiter = getattr(field_value.model_config, "env_nested_delimiter", "__")
            # 生成嵌套前缀（如 TORTOISE_ + MASTER + __ = TORTOISE_MASTER__）
            nested_prefix = f"{current_prefix}{field_name.upper()}{nested_delimiter}"
            nested_injected = inject_config_to_env(
                config_instance=field_value, parent_prefix=nested_prefix, skip_existing=skip_existing
            )
            injected_envs.update(nested_injected)
            continue

        # 4. 处理基础类型字段（跳过 None 值）
        if field_value is None:
            continue

        # 生成最终环境变量名（如 TORTOISE_MASTER__HOST）
        env_var_name = f"{current_prefix}{field_name.upper()}"

        # 5. 仅当环境变量不存在时注入
        if skip_existing and env_var_name in os.environ:
            continue

        # 转换为字符串（处理布尔/整数/列表等类型）
        if isinstance(field_value, bool):
            env_value = "true" if field_value else "false"  # 标准化布尔值
        elif isinstance(field_value, (list, dict)):
            env_value = str(field_value)  # 列表/字典转为字符串（如 ["a","b"] → "['a', 'b']"）
        else:
            env_value = str(field_value)

        # 6. 注入环境变量
        os.environ[env_var_name] = env_value
        injected_envs[env_var_name] = env_value

    return injected_envs
