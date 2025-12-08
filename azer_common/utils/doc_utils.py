import importlib
import json
from pathlib import Path
from fastapi import FastAPI


def load_docs(module_name, action_name):
    """
    动态加载对应的 _docs 模块和特定的 API 动作文档
    :param module_name: 路由模块名称，用于找到对应的文档文件
    :param action_name: API 动作名称，用于找到特定 API 的文档
    :return: 返回从文档文件中加载的 summary, description, responses
    """

    docs_module_name = f"docs.{module_name}_docs"

    try:
        # 动态导入对应的 _docs 模块
        docs_module = importlib.import_module(docs_module_name)

        # 根据 action_name 动态获取 summary, description 和 responses
        summary = getattr(docs_module, f"{action_name}_summary", "")
        description = getattr(docs_module, f"{action_name}_description", "")
        responses = getattr(docs_module, f"{action_name}_responses", {})

        return summary, description, responses

    except ModuleNotFoundError:
        # 如果没有对应的 _docs 文件，则返回默认空值
        return "", "", {}

    except AttributeError:
        # 如果没有对应的 action_name 的文档项，则返回默认空值
        return "", "", {}


def export_openapi(
        app: FastAPI,
        file_path: str = None
) -> dict:
    """
    导出 OpenAPI 规范并保存为 JSON 文件。

    :param app: FastAPI 实例
    :param file_path: 保存 OpenAPI 规范的文件路径
    :return: 返回 OpenAPI 规范的字典形式
    """
    # 初始化默认文件路径
    if file_path is None:
        file_path = f"docs/openapi.json"

    try:
        openapi_schema = app.openapi()
        output_path = Path(file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(openapi_schema, file, ensure_ascii=False, indent=4)

        print(f"OpenAPI 规范已成功导出到: {file_path}")
        return openapi_schema

    except IOError as e:
        print(f"写入 OpenAPI 规范失败 {file_path}: {str(e)}")
        raise
    except Exception as e:
        print(f"导出 OpenAPI 规范异常: {str(e)}")
        raise
