import re
from datetime import datetime

from pydantic import ValidationError


# 验证用户名的格式
def validate_username(value: str):
    if not re.match(r'^[A-Za-z0-9_.@]{4,30}$', value):
        raise ValidationError("用户名格式无效，应为4到30位的字母、数字、点、下划线或@符号。")


# 验证邮箱格式
def validate_email(value: str):
    if not re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', value):
        raise ValidationError("邮箱格式无效，请输入正确的邮箱地址。")


# 验证手机号码格式（中国手机号）
def validate_mobile(value: str):
    if not re.match(r'^(13[0-9]|14[5|7]|15[0-9]|18[0-9]|17[0-9])\d{8}$', value):
        raise ValidationError("手机号格式无效，请输入有效的中国大陆手机号码。")


# 验证密码格式
def validate_password(value: str):
    if not re.match(r'^(?=.*[a-zA-Z])(?=.*\d).{8,64}$', value):
        raise ValidationError("密码格式无效，必须包含字母和数字，长度为8到64个字符。")


# 验证身份证格式
def validate_identity_card(value: str):
    error_msg = "身份证号格式错误"
    if not value:
        raise ValidationError(error_msg)

    id_card = value.strip()

    if len(id_card) != 18:
        raise ValidationError(error_msg)

    if not re.match(r'^[1-9]\d{16}[\dXx]$', id_card):
        raise ValidationError(error_msg)

    if not re.match(r'^[1-9]\d{5}$', id_card[:6]):
        raise ValidationError(error_msg)

    birth_date_str = id_card[6:14]
    try:
        birth_date = datetime.strptime(birth_date_str, "%Y%m%d")
        current_year = datetime.now().year
        if birth_date.year > current_year or (current_year - birth_date.year) > 120:
            raise ValidationError(error_msg)
    except ValidationError:
        raise ValidationError(error_msg)

    check_code = id_card[-1].upper()
    coefficients = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_code_map = {0: '1', 1: '0', 2: 'X', 3: '9', 4: '8', 5: '7', 6: '6', 7: '5', 8: '4', 9: '3', 10: '2'}
    total = sum(int(id_card[i]) * coefficients[i] for i in range(17))
    remainder = total % 11
    expected_check_code = check_code_map[remainder]

    if check_code != expected_check_code:
        raise ValidationError(error_msg)

    if not re.match(r'^\d{3}$', id_card[14:17]):
        raise ValidationError(error_msg)


# 验证url格式
def validate_url(value: str) -> None:
    if not value:
        return  # 允许空值

    url_pattern = re.compile(
        r'^https?://'  # 必须以http/https开头
        r'(?:(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+'  # 子域名（支持-）
        r'[a-zA-Z]{2,}|'  # 顶级域（长度≥2，取消6的上限）
        r'localhost|'  # 本地主机
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IPv4
        r'(?::\d{1,5})?'  # 端口（1-5位数字，符合TCP端口范围）
        r'(?:/[^\s]*)?'  # 路径（允许空路径，兼容URL编码字符、锚点#）
        r'$',
        re.IGNORECASE
    )

    if not url_pattern.match(value):
        raise ValidationError(
            "URL格式无效，需以http/https开头，如：https://example.com/avatar.jpg"
        )


# 验证验证码格式
def validate_verifycode(value: str):
    if not re.match(r'^\d{6}$', value):
        raise ValidationError("验证码格式无效，应为6位数字。")


# 验证权限码格式
def validate_permission_code(value: str):
    if not re.match(r'^[a-z][a-z0-9_:]*:[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*)?$', value):
        raise ValidationError(
            "权限代码格式错误，必须为：资源:操作[:范围]，"
            "且只允许小写字母、数字、下划线和冒号"
        )
