import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from langchain.agents import create_agent
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (rag_summarize, get_user_id,
                                     get_current_month, fetch_external_data, fill_context_for_report)
from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[rag_summarize, get_user_id,
                   get_current_month, fetch_external_data, fill_context_for_report],
            middleware=[monitor_tool, log_before_model, report_prompt_switch],
        )

    def execute_stream(self, query: str, profile_context: str = "", system_addition: str = "", conversation_context: str = "", state_context: str = ""):
        """
        执行 Agent 真流式输出 - 逐字返回
        
        Args:
            query: 用户输入
            profile_context: 用户画像上下文（可选）
            system_addition: 系统提示词追加内容（可选，用于黄词免责、拒绝处理等）
            conversation_context: 最近对话上下文（可选，用于话题切换）
            state_context: 对话状态上下文（可选，状态机注入）
        """
        # 构建用户消息
        context_parts = []
        
        # 状态上下文优先（最重要）
        if state_context:
            context_parts.append(f"【对话状态】\n{state_context}")
        
        if profile_context and profile_context != "暂无用户画像信息":
            context_parts.append(f"【用户画像】\n{profile_context}")
        
        if conversation_context:
            context_parts.append(f"【最近对话记录】\n{conversation_context}")
        
        if system_addition:
            context_parts.append(f"【临时指令】\n{system_addition}")
        
        if context_parts:
            user_message = "\n\n".join(context_parts) + f"\n\n【用户当前问题】\n{query}"
        else:
            user_message = query
        
        input_dict = {
            "messages": [
                {"role": "user", "content": user_message},
            ]
        }

        # 使用 stream_mode="messages" 实现真流式输出，逐字 yield
        try:
            for chunk in self.agent.stream(input_dict, stream_mode="messages", context={"report": False}):
                # chunk 是 (message, metadata) 元组
                if isinstance(chunk, tuple) and len(chunk) >= 2:
                    message = chunk[0]
                    if hasattr(message, 'content') and message.content:
                        # 逐字 yield
                        for char in message.content:
                            yield char
                elif hasattr(chunk, 'content') and chunk.content:
                    # 直接是消息对象的情况
                    for char in chunk.content:
                        yield char
        except Exception as e:
            # 流式输出出错时，返回错误信息
            error_msg = f"[抱歉，请求出错了，请稍后重试]"
            for char in error_msg:
                yield char


if __name__ == '__main__':
    agent = ReactAgent()

    for chunk in agent.execute_stream("给我生成我的养生报告"):
        print(chunk, end="", flush=True)
