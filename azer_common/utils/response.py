from typing import Any

from pydantic import BaseModel


class StandardResponse(BaseModel):
    result: Any
    code: int
    message: str


def response(result: Any = '', code: int = 200, message: str = "Success") -> dict:
    """
    封装标准响应数据
    :param result: 实际返回的数据
    :param code: 状态码
    :param message: 描述消息
    :return: 包含标准结构的 JSON 数据
    """
    return StandardResponse(result=result, code=code, message=message).model_dump()


def to_camel(string: str) -> str:
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])
