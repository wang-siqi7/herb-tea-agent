"""测试阿里云百炼模型是否可用"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_direct_call():
    """直接测试 API"""
    print("=== 测试1：直接调用 ===")
    try:
        import dashscope
        from dashscope import Generation
        
        # 从环境变量读取 API Key
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            print("❌ 环境变量 DASHSCOPE_API_KEY 未设置")
            print("   请运行: export DASHSCOPE_API_KEY='sk-xxx'")
            return False
        
        print(f"✅ API Key 已找到: {api_key[:10]}...")
        
        dashscope.api_key = api_key
        messages = [{"role": "user", "content": "你好，请说'连接成功'"}]
        response = Generation.call(model="qwen3-max", messages=messages)
        
        if response.status_code == 200:
            print(f"✅ 调用成功！回复: {response.output.text}")
            return True
        else:
            print(f"❌ 调用失败: {response.code} - {response.message}")
            return False
    except Exception as e:
        print(f"❌ 出错: {e}")
        return False

def test_langchain_call():
    """测试 LangChain 调用"""
    print("\n=== 测试2：通过 LangChain 调用 ===")
    try:
        from model.factory import chat_model
        from langchain_core.messages import HumanMessage
        
        response = chat_model.invoke([HumanMessage(content="你好")])
        print(f"✅ LangChain 调用成功！")
        print(f"   回复: {response.content[:100]}...")
        return True
    except Exception as e:
        print(f"❌ LangChain 调用失败: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("中药茶饮 Agent - 模型连通性测试")
    print("=" * 50)
    
    # 先测试环境变量
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("\n⚠️ 未检测到 DASHSCOPE_API_KEY 环境变量")
        print("   请在终端运行以下命令设置：")
        print("   export DASHSCOPE_API_KEY='你的key'")
        print("   然后再运行: streamlit run app.py")
    else:
        test_direct_call()
        test_langchain_call()