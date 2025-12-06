import re


# 验证用户名的格式
def validate_username(value: str):
    """
    验证用户名的格式是否有效。用户名只能包含字母、数字、点和@符号，长度为4到30个字符。

    :param value: 需要验证的用户名
    :raises ValueError: 如果用户名格式不正确，抛出异常
    """
    if not re.match(r'^[A-Za-z0-9.@]{4,30}$', value):
        raise ValueError("用户名格式无效，应为4到30位的字母、数字、点或@符号。")


# 验证邮箱格式
def validate_email(value: str):
    """
    验证邮箱地址的格式是否有效。邮箱地址必须包含字母、数字、特殊字符，并且遵循通用的邮箱格式。

    :param value: 需要验证的邮箱地址
    :raises ValueError: 如果邮箱格式不正确，抛出异常
    """
    if not re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', value):
        raise ValueError("邮箱格式无效，请输入正确的邮箱地址。")


# 验证手机号码格式（中国手机号）
def validate_mobile(value: str):
    """
    验证手机号码格式是否有效。仅支持中国大陆手机号码的验证。

    :param value: 需要验证的手机号
    :raises ValueError: 如果手机号格式不正确，抛出异常
    """
    if not re.match(r'^(13[0-9]|14[5|7]|15[0-9]|18[0-9]|17[0-9])\d{8}$', value):
        raise ValueError("手机号格式无效，请输入有效的中国大陆手机号码。")


# 验证密码格式
def validate_password(value: str):
    """
    验证密码的格式是否有效。密码必须包含字母和数字，长度为8到16个字符。

    :param value: 需要验证的密码
    :raises ValueError: 如果密码格式不正确，抛出异常
    """
    if not re.match(r'^(?=.*[a-zA-Z])(?=.*\d).{8,16}$', value):
        raise ValueError("密码格式无效，必须包含字母和数字，长度为8到16个字符。")


# 验证验证码格式
def validate_verifycode(value: str):
    """
    验证验证码的格式是否有效。验证码应为6位的纯数字。

    :param value: 需要验证的验证码
    :raises ValueError: 如果验证码格式不正确，抛出异常
    """
    if not re.match(r'^\d{6}$', value):
        raise ValueError("验证码格式无效，应为6位数字。")
