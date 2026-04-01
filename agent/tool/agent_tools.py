import os
from utils.logger_handler import logger
from langchain_core.tools import tool
from rag.rag_service import RagSummarizeService
import random
from utils.config_handler import agent_conf
from utils.path_tool import get_abs_path

rag = RagSummarizeService()

user_ids = ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1010",]
month_arr = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
             "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12", ]

external_data = {}


@tool(description="从中药茶饮知识库中检索药材功效、体质辨识、茶饮配方等信息")
def rag_summarize(query: str) -> str:
    return rag.rag_summarize(query)

@tool(description="获取用户的唯一ID，用于查询个人饮用记录")
def get_user_id() -> str:
    return random.choice(user_ids)


@tool(description="获取当前月份，格式为YYYY-MM，用于查询指定月份的饮用记录")
def get_current_month() -> str:
    return random.choice(month_arr)


def generate_external_data():

    if not external_data:
        external_data_path = get_abs_path(agent_conf["external_data_path"])

        if not os.path.exists(external_data_path):
            raise FileNotFoundError(f"外部数据文件{external_data_path}不存在")

        with open(external_data_path, "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                arr: list[str] = line.strip().split(",")

                user_id: str = arr[0].replace('"', "")
                feature: str = arr[1].replace('"', "")
                efficiency: str = arr[2].replace('"', "")
                consumables: str = arr[3].replace('"', "")
                comparison: str = arr[4].replace('"', "")
                time: str = arr[5].replace('"', "")

                if user_id not in external_data:
                    external_data[user_id] = {}

                external_data[user_id][time] = {
                    "特征": feature,
                    "效率": efficiency,
                    "耗材": consumables,
                    "对比": comparison,
                }


@tool(description="获取指定用户在指定月份的茶饮饮用记录，用于生成养生报告")
def fetch_external_data(user_id: str, month: str) -> str:
    generate_external_data()

    try:
        return external_data[user_id][month]
    except KeyError:
        logger.warning(f"未检索到用户{user_id}在{month}的饮用记录")
        return ""


@tool(description="调用后触发中间件，为报告生成场景注入上下文信息")
def fill_context_for_report():
    return "fill_context_for_report已调用"
