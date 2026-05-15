"""
中药茶饮智能顾问 - Streamlit 主界面
集成：敏感词分级、黄词免责、本轮/永久拒绝、画像确认、持久化
"""

import time
import re
import streamlit as st
from agent.react_agent import ReactAgent
from utils.user_profile import UserProfile, SourceType, get_profile_instance
from utils.db_manager import get_db_manager


# ========== 对话状态机 ==========

class DialogStateMachine:
    """对话状态管理器 - 解决重复追问、数字识别、话题混乱问题"""
    
    # 话题定义
    TOPICS = {
        "sleep": {"name": "改善睡眠", "keywords": ["失眠", "睡不好", "安神", "助眠", "睡眠"]},
        "stomach": {"name": "调理肠胃", "keywords": ["胃胀", "消化不良", "健脾", "养胃", "肠胃"]},
        "heat": {"name": "清热降火", "keywords": ["上火", "清热", "降火", "口干"]},
        "lung": {"name": "润肺养阴", "keywords": ["润肺", "养阴", "咳嗽", "干燥"]},
        "package": {"name": "包装规格", "keywords": ["包装", "规格", "购买", "单独"]},
    }
    
    # 肯定词
    AFFIRMATIVE = ["嗯", "要", "好", "是的", "对", "没错", "可以", "行", "嗯嗯", "哦", "ok", "好的", "是"]
    
    # 否定词
    NEGATIVE = ["不要", "不用", "不了", "算了", "别", "不是", "不对", "没有", "拒绝"]
    
    # 拒绝追问词
    REFUSE_QUESTION = ["不告诉你", "不想说", "不方便", "别问了", "不要问"]
    
    def __init__(self):
        self.current_topic = None           # 当前话题
        self.current_step = None            # 当前步骤: introducing/asking/recommending
        self.asked_questions = []           # 已问过的问题列表（避免重复）
        self.collected_answers = {}         # 已收集的答案
        self.waiting_for_option = False     # 是否在等待用户选择选项
        self.current_options = {}            # 当前问题的选项 {"1": "入睡困难", "2": "容易醒来"}
        self.option_question = None          # 当前选项对应的问题
        self.consecutive_refusals = 0        # 连续拒绝次数
        self.last_agent_response = ""        # 上一轮Agent回复
    
    def reset(self):
        """重置状态机"""
        self.current_topic = None
        self.current_step = None
        self.asked_questions = []
        self.waiting_for_option = False
        self.current_options = {}
        self.option_question = None
        self.consecutive_refusals = 0
        self.last_agent_response = ""
    
    def detect_topic(self, text: str) -> str:
        """从文本中检测话题"""
        text = text.lower()
        for topic, info in self.TOPICS.items():
            for keyword in info["keywords"]:
                if keyword in text:
                    return topic
        return None
    
    def start_topic(self, topic: str):
        """开始一个新话题"""
        self.current_topic = topic
        self.current_step = "introducing"
        self.waiting_for_option = False
        self.current_options = {}
    
    def switch_topic(self, topic: str):
        """切换话题"""
        self.current_topic = topic
        self.current_step = "introducing"
        self.waiting_for_option = False
        self.current_options = {}
        # 注意：不清空 collected_answers，跨话题保留画像
    
    def register_question(self, question: str):
        """记录已问过的问题"""
        if question and question not in self.asked_questions:
            self.asked_questions.append(question)
    
    def has_asked(self, question: str) -> bool:
        """检查是否已经问过这个问题"""
        for asked in self.asked_questions:
            if question in asked or asked in question:
                return True
        return False
    
    def set_options(self, question: str, options: dict):
        """设置选项等待用户选择"""
        self.waiting_for_option = True
        self.current_options = options
        self.option_question = question
        self.register_question(question)
    
    def parse_user_input(self, user_input: str) -> dict:
        """
        解析用户输入，返回类型和值
        """
        user_input = user_input.strip()
        
        # 检查拒绝追问（最高优先级）
        for word in self.REFUSE_QUESTION:
            if word in user_input:
                return {"type": "refuse_question", "value": word}
        
        # 检查数字输入 - 优先检查是否是选项（如果正在等待选项）
        if user_input.isdigit():
            option_key = user_input
            # 如果正在等待选项，优先识别为选项
            if self.waiting_for_option and option_key in self.current_options:
                return {"type": "option", "value": self.current_options[option_key], "option_key": option_key}
            # 如果没有当前话题，数字才识别为话题切换
            if not self.current_topic:
                topic_map = {"1": "sleep", "2": "stomach", "3": "heat", "4": "lung"}
                if user_input in topic_map:
                    return {"type": "topic_switch", "value": topic_map[user_input], "option_key": user_input}
            # 有话题但等待选项 → 仍按选项处理
            if self.waiting_for_option:
                return {"type": "option", "value": self.current_options.get(option_key, user_input), "option_key": option_key}
        
        # 检查选项（如果正在等待选项）- 文字匹配
        if self.waiting_for_option:
            for key, text in self.current_options.items():
                if text in user_input:
                    return {"type": "option", "value": text, "option_key": key}
        
        # 肯定词
        lower_input = user_input.lower()
        if user_input in self.AFFIRMATIVE or lower_input in ["yes", "y"]:
            return {"type": "affirmative", "value": user_input}
        
        # 否定词
        if user_input in self.NEGATIVE or any(neg in user_input for neg in ["不要", "不用", "不了"]):
            return {"type": "negative", "value": user_input}
        
        # 检查数字选择（不等待选项时也识别，用于话题切换）
        if user_input.isdigit():
            topic_map = {"1": "sleep", "2": "stomach", "3": "heat", "4": "lung"}
            if user_input in topic_map:
                return {"type": "topic_switch", "value": topic_map[user_input], "option_key": user_input}
        
        # 普通文本 - 检测话题关键词
        detected_topic = self.detect_topic(user_input)
        if detected_topic and detected_topic != self.current_topic:
            return {"type": "topic_change", "value": detected_topic}
        
        return {"type": "free_text", "value": user_input}
    
    def record_answer(self, question: str, answer: str):
        """记录用户答案"""
        self.collected_answers[question] = answer
    
    def should_skip_question(self, question: str) -> bool:
        """判断是否应该跳过这个问题（已问过或已回答过）"""
        if self.has_asked(question):
            return True
        for asked, answer in self.collected_answers.items():
            if question in asked or asked in question:
                return True
        return False
    
    def handle_refusal(self):
        """处理用户拒绝回答"""
        self.consecutive_refusals += 1
        if self.consecutive_refusals >= 2:
            self.skip_current_questioning()
    
    def skip_current_questioning(self):
        """跳过当前话题的所有追问，直接给出推荐"""
        self.current_step = "recommending"
        self.waiting_for_option = False
    
    def get_context_for_agent(self) -> str:
        """生成状态上下文，注入给Agent"""
        topic_name = ""
        if self.current_topic:
            topic_name = self.TOPICS.get(self.current_topic, {}).get("name", self.current_topic)
        
        context = f"""【对话状态】
当前话题: {topic_name} ({self.current_topic or '未确定'})
当前步骤: {self.current_step or '初始'}

【等待选项状态】
是否等待选项: {'是' if self.waiting_for_option else '否'}
当前选项: {self.current_options if self.current_options else '无'}
当前问题: {self.option_question or '无'}

【已收集的答案】
{self._format_collected_answers()}

【已问过的问题】（禁止重复提问！）
{', '.join(self.asked_questions) if self.asked_questions else '无'}

【连续拒绝次数】
{self.consecutive_refusals}次

【重要规则】
1. 如果用户输入数字（如"1"），必须视为选择对应的选项
2. 如果用户说"嗯"、"要"、"好"，表示肯定/确认
3. 如果用户说"不要"、"不用"，表示否定/拒绝
4. 禁止重复问已经问过的问题
5. 如果用户拒绝回答2次以上，停止追问，直接给出推荐
"""
        return context
    
    def _format_collected_answers(self) -> str:
        if not self.collected_answers:
            return "暂无"
        return "\n".join([f"- {q}: {a}" for q, a in self.collected_answers.items()])
    
    def update_from_agent_response(self, response: str):
        """从Agent回复中解析状态变化"""
        self.last_agent_response = response
        
        # 检测Agent是否提出了新的选项问题（支持多种格式）
        # 格式1: "1. 选项1\n2. 选项2"
        # 格式2: "1）选项1\n2）选项2"
        # 格式3: "1、选项1\n2、选项2"
        option_pattern = r'(\d+)[\.、\）\)]\s*([^\n\d]+)'
        matches = re.findall(option_pattern, response)
        
        if matches and len(matches) >= 2:
            # 清理选项文本
            options = {}
            for m in matches:
                option_text = m[1].strip()
                # 去除可能的前缀符号
                option_text = option_text.lstrip('.-、）) ')
                if option_text:
                    options[m[0]] = option_text
            
            if len(options) >= 2:
                # 提取问题（选项前面的句子，查找问号所在行）
                lines = response.split('\n')
                question = ""
                for line in lines:
                    if '？' in line or '?' in line:
                        question = line.strip()
                        break
                    # 也检查类似"请选择："这样的提示
                    if '请选择' in line or '请告诉我' in line or '您是' in line:
                        question = line.strip()
                        break
                
                if question and not self.has_asked(question):
                    self.set_options(question, options)
                    self.current_step = "waiting_for_answer"
    
    def to_dict(self) -> dict:
        """序列化状态"""
        return {
            "current_topic": self.current_topic,
            "current_step": self.current_step,
            "asked_questions": self.asked_questions,
            "collected_answers": self.collected_answers,
            "waiting_for_option": self.waiting_for_option,
            "current_options": self.current_options,
            "option_question": self.option_question,
            "consecutive_refusals": self.consecutive_refusals,
        }
    
    def from_dict(self, data: dict):
        """从字典恢复状态"""
        if not data:
            return
        self.current_topic = data.get("current_topic")
        self.current_step = data.get("current_step")
        self.asked_questions = data.get("asked_questions", [])
        self.collected_answers = data.get("collected_answers", {})
        self.waiting_for_option = data.get("waiting_for_option", False)
        self.current_options = data.get("current_options", {})
        self.option_question = data.get("option_question")
        self.consecutive_refusals = data.get("consecutive_refusals", 0)

# ========== 页面配置 ==========
st.set_page_config(
    page_title="中药茶饮智能顾问",
    page_icon="🍵",
    layout="wide"
)

# ========== 常量定义 ==========

# 🔴 红词拒绝回复
RED_REJECTION = "抱歉，这个问题需要专业医生来判断，我无法给出建议。建议您咨询医疗专业人士获取准确信息。"

# 🟡 黄词免责声明模板
YELLOW_DISCLAIMER_TEMPLATE = """【重要提示】
茶饮不能替代药物治疗，建议您先咨询医生意见。在遵医嘱的前提下，以下建议可作为日常调理参考：
"""

# ⚫ 灰词模糊回复
GRAY_VAGUE_REPLY = "关于这个问题，我建议您根据自身情况选择合适的养生茶，具体可以咨询专业人士。"

# 画像确认问题
PROFILE_CONFIRM_QUESTIONS = {
    "drinking_mode": "我猜您是{value}，对吗？",
    "usage_scenario": "您平时主要在{value}喝茶，对吗？",
    "health_goal": "我猜您想{value}，是这个目的吗？",
    "taste_preference": "您喜欢{value}的口感，对吗？",
}

# 拒绝信号友好回复模板
REFUSAL_RESPONSES = {
    "temp": "好的，已暂停引导。您可以继续提问，我不会再追问偏好。\n\n如需恢复引导，请说「可以问了」。\n\n如需彻底删除已记录的偏好数据，请在右侧侧边栏点击「清空画像」或「删除数据」。",
    "permanent": "好的，已永久关闭引导功能。我不会再追问您的偏好。\n\n如需恢复，请说「可以问了」。\n\n如需删除已记录的数据，请在侧边栏操作。",
    "resume": "好的，已恢复引导功能。您有需要了解的茶饮偏好吗？我可以为您推荐更合适的茶饮。",
}

# ========== 初始化 session_state ==========

def init_session_state():
    """初始化 session_state"""
    
    # 用户画像
    if "profile" not in st.session_state:
        st.session_state["profile"] = UserProfile()
    
    # Agent 实例
    if "agent" not in st.session_state:
        st.session_state["agent"] = ReactAgent()
    
    # 对话状态机
    if "dialog_state" not in st.session_state:
        st.session_state["dialog_state"] = DialogStateMachine()
    
    # 消息历史
    if "message" not in st.session_state:
        st.session_state["message"] = []
    
    # 待确认的画像（从Agent响应中提取）
    if "pending_confirms" not in st.session_state:
        st.session_state["pending_confirms"] = {}
    
    # 黄词标志（本轮需要免责声明）
    if "yellow_warning" not in st.session_state:
        st.session_state["yellow_warning"] = False
    
    # 用户ID（用于持久化）
    if "user_id" not in st.session_state:
        # 模拟用户ID（实际应从登录系统获取）
        st.session_state["user_id"] = "user_default"
    
    # 从数据库加载画像（如果存在）
    if "profile_loaded" not in st.session_state:
        st.session_state["profile_loaded"] = False
        db = get_db_manager()
        user_id = st.session_state["user_id"]
        saved_profile = db.load_profile(user_id)
        
        if saved_profile:
            profile = st.session_state["profile"]
            profile.from_dict(saved_profile)
            
            # 恢复永久拒绝状态
            if saved_profile.get("permanent_refusal"):
                profile._permanent_refusal_active = True
            
            # 恢复对话状态机
            if saved_profile.get("dialog_state"):
                st.session_state["dialog_state"].from_dict(saved_profile["dialog_state"])
            
            st.session_state["profile_loaded"] = True


# ========== 页面组件 ==========

def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.title("🍵 智能顾问")
        st.divider()
        
        profile = st.session_state["profile"]
        profile_summary = profile.get_profile_summary()
        
        # 用户ID显示
        st.subheader("👤 用户信息")
        st.text(f"用户ID: {st.session_state.get('user_id', '未登录')}")
        
        # 画像状态
        st.divider()
        st.subheader("📊 画像状态")
        
        col1, col2 = st.columns(2)
        with col1:
            status = "✅" if profile_summary["mining_allowed"] else "❌"
            st.metric("引导状态", f"{status} {'开启' if profile_summary['mining_allowed'] else '关闭'}")
        with col2:
            st.metric("采集维度", f"{profile_summary['profile_count']}/7")
        
        # 用户明确说的信息
        explicit = profile.get_explicit()
        if explicit:
            st.divider()
            st.subheader("✅ 用户明确偏好")
            for key, value in explicit.items():
                dim_name = profile.MINABLE_DIMENSIONS.get(key, {}).get("display_name", key)
                st.text(f"• {dim_name}: {value}")
        
        # 待确认的推断
        pending = profile.get_pending_inferences()
        if pending:
            st.divider()
            st.subheader("🤔 待确认推断")
            
            for key, value in pending.items():
                dim_name = profile.MINABLE_DIMENSIONS.get(key, {}).get("display_name", key)
                
                col_yes, col_no = st.columns([1, 1])
                with col_yes:
                    if st.button(f"✅ 是", key=f"confirm_{key}"):
                        profile.confirm_inference(key)
                        st.success(f"已确认: {dim_name}")
                        st.rerun()
                with col_no:
                    if st.button(f"❌ 否", key=f"reject_{key}"):
                        profile.reject_inference(key)
                        st.rerun()
        
        # 画像采集进度
        st.divider()
        st.subheader("📈 采集进度")
        dimensions = profile.get_minable_dimensions_status()
        for dim, collected in dimensions.items():
            dim_names = profile.MINABLE_DIMENSIONS.get(dim, {})
            display_name = dim_names.get("display_name", dim)
            icon = "✅" if collected else "⬜"
            st.text(f"{icon} {display_name}")
        
        # 操作按钮
        st.divider()
        st.subheader("⚙️ 操作")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("清空画像", type="secondary"):
                profile.clear_session()
                st.success("本轮画像已清空")
                st.rerun()
        
        with col2:
            if st.button("删除数据", type="secondary"):
                db = get_db_manager()
                db.delete_profile(st.session_state["user_id"])
                profile.full_reset()
                st.success("所有数据已删除")
                st.rerun()
        
        # ========== 新增：重置所有数据按钮 ==========
        st.divider()
        if st.button("🔄 重置所有数据", type="primary", use_container_width=True):
            # 1. 清空 session 中的画像
            profile.full_reset()
            # 2. 重置状态机
            dialog.reset()
            # 3. 删除数据库中的记录
            db = get_db_manager()
            db.delete_profile(st.session_state["user_id"])
            # 4. 清空消息历史
            st.session_state["message"] = []
            # 5. 重置其他状态
            st.session_state["pending_confirms"] = {}
            st.session_state["yellow_warning"] = False
            st.session_state["profile_loaded"] = False
            # 6. 显示成功消息并刷新
            st.success("所有数据已重置！")
            time.sleep(1)
            st.rerun()
        
        # 保存按钮
        if st.button("💾 保存画像", type="primary"):
            db = get_db_manager()
            if db.save_profile(st.session_state["user_id"], profile.to_dict()):
                st.success("画像已保存")
            else:
                st.error("保存失败")


def render_chat_history():
    """渲染聊天历史"""
    for message in st.session_state["message"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def handle_user_input(prompt: str):
    """
    处理用户输入的完整流程 - 集成状态机
    
    流程：
    1. 状态机解析用户输入
    2. 敏感词分级检测
    3. 调用 Agent
    4. 提取/更新画像
    5. 保存到数据库
    """
    profile = st.session_state["profile"]
    dialog = st.session_state["dialog_state"]
    
    # 显示用户消息
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role": "user", "content": prompt})
    
    # ========== Step 0: 状态机解析用户输入 ==========
    parsed = dialog.parse_user_input(prompt)
    
    # 处理话题切换（数字选项）
    if parsed["type"] == "topic_switch":
        topic_name = dialog.TOPICS.get(parsed["value"], {}).get("name", parsed["value"])
        dialog.switch_topic(parsed["value"])
        # 增强 prompt
        prompt = f"用户选择了：{topic_name}。请推荐对应的茶饮。"
    
    # 处理话题变化
    elif parsed["type"] == "topic_change":
        dialog.switch_topic(parsed["value"])
        topic_name = dialog.TOPICS.get(parsed["value"], {}).get("name", parsed["value"])
        prompt = f"用户想了解：{topic_name}。请推荐对应的茶饮。"
    
    # 处理选项选择
    elif parsed["type"] == "option":
        question = dialog.option_question or "用户选择"
        dialog.record_answer(question, parsed["value"])
        dialog.waiting_for_option = False
        # 增强 prompt
        prompt = f"用户选择了：{parsed['value']}。原问题：{prompt}"
    
    # 处理肯定
    elif parsed["type"] == "affirmative":
        prompt = f"用户说'{parsed['value']}'，表示同意/确认。请继续推进对话。"
    
    # 处理否定
    elif parsed["type"] == "negative":
        prompt = f"用户说'{parsed['value']}'，表示不同意/拒绝。请换一个方向推荐。"
    
    # 处理拒绝追问
    elif parsed["type"] == "refuse_question":
        dialog.handle_refusal()
        if dialog.consecutive_refusals >= 2:
            reply = "好的，我理解了。直接为您推荐一款通用的茶饮吧。\n\n推荐酸枣仁安神茶，由酸枣仁、百合、茯苓组成，适合改善睡眠质量。"
        else:
            reply = "好的，那我们先不聊这个。您想了解其他方面的茶饮吗？"
        with st.chat_message("assistant"):
            st.markdown(reply)
        st.session_state["message"].append({"role": "assistant", "content": reply})
        st.rerun()
    
    # ========== Step 1: 敏感词分级检测 ==========
    
    classification = profile.classify_sensitive(prompt)
    
    # 🔴 红词：直接拒绝
    if classification["action"] == "reject":
        st.chat_message("assistant").write(RED_REJECTION)
        st.session_state["message"].append({"role": "assistant", "content": RED_REJECTION})
        return
    
    # ⚫ 灰词：模糊回答
    if classification["action"] == "vague":
        st.chat_message("assistant").write(GRAY_VAGUE_REPLY)
        st.session_state["message"].append({"role": "assistant", "content": GRAY_VAGUE_REPLY})
        return
    
    # 🟡 黄词：标记需要免责声明
    if classification["action"] == "disclaimer":
        st.session_state["yellow_warning"] = True
    
    # ========== Step 2: 拒绝信号检测（带友好回复）==========
    
    refusal_type, keyword = profile.detect_refusal(prompt)
    
    if refusal_type != "none":
        profile.handle_refusal(refusal_type)
        
        # 显示友好回复（不调用 Agent，直接返回）
        friendly_reply = REFUSAL_RESPONSES.get(refusal_type, "好的，已处理您的请求。")
        
        with st.chat_message("assistant"):
            st.markdown(friendly_reply)
        st.session_state["message"].append({"role": "assistant", "content": friendly_reply})
        
        # 如果不是恢复，不需要 rerun（让用户继续对话）
        if refusal_type == "resume":
            return  # 继续等待用户下一个问题
        else:
            st.rerun()
    
    # ========== Step 3: 调用 Agent ==========
    
    # 获取画像上下文
    profile_context = profile.get_context_summary() if profile.is_mining_allowed() else "暂无用户画像信息"
    
    # 构建系统提示词追加
    system_addition = ""
    
    # 黄词：追加免责声明指令
    if st.session_state.get("yellow_warning"):
        system_addition += f"\n{YELLOW_DISCLAIMER_TEMPLATE}"
        st.session_state["yellow_warning"] = False  # 重置
    
    # 本轮拒绝：追加不引导指令
    if profile._temp_refusal_active:
        system_addition += "\n【重要】用户刚才表示不想被追问，本轮回答后不要添加任何引导问题。"
    
    # 永久拒绝：追加不引导指令
    if profile._permanent_refusal_active:
        system_addition += "\n【重要】用户已永久关闭引导功能，回答后不要添加任何引导问题或选项。"
    
    # ========== 获取最近对话上下文（用于话题切换）==========
    recent_messages = st.session_state.get("message", [])[-6:]  # 最近3轮对话
    if recent_messages:
        conversation_summary = "\n".join([
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:300]}"
            for m in recent_messages
        ])
    else:
        conversation_summary = ""
    
    # ========== 获取状态机上下文 ==========
    state_context = dialog.get_context_for_agent()
    
    # ========== 执行 Agent - 真流式显示（带光标）==========
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        try:
            res_stream = st.session_state["agent"].execute_stream(
                prompt, 
                profile_context,
                system_addition if system_addition else None,
                conversation_summary,
                state_context  # 新增：状态机上下文
            )
            
            for chunk in res_stream:
                if chunk:
                    full_response += chunk
                    # 显示带光标的逐字效果
                    response_placeholder.markdown(full_response + "▌")
            
            # 最终显示（去掉光标）
            response_placeholder.markdown(full_response)
            assistant_reply = full_response
            
        except Exception as e:
            error_msg = f"抱歉，请求出错了，请稍后重试"
            response_placeholder.markdown(error_msg)
            assistant_reply = error_msg
    
    # 保存到消息历史
    if assistant_reply:
        st.session_state["message"].append({"role": "assistant", "content": assistant_reply})
        
        # ========== 更新状态机：从 Agent 回复中解析选项 ==========
        dialog.update_from_agent_response(assistant_reply)
        
        # ========== Step 4: 更新画像 ==========
        
        # 从对话中提取用户明确说的信息
        updated_keys = profile.update_from_conversation(prompt, assistant_reply)
        
        # 检查是否有需要确认的推断
        pending = profile.get_pending_inferences()
        if pending:
            st.session_state["pending_confirms"] = pending
        
        # 增加挖掘计数
        profile.increment_mining_count()
        
        # ========== Step 5: 保存到数据库 ==========
        
        db = get_db_manager()
        # 合并画像和状态机数据
        save_data = profile.to_dict()
        save_data["dialog_state"] = dialog.to_dict()
        db.save_profile(st.session_state["user_id"], save_data)
        
        # 可选：保存对话历史
        # db.save_conversation(
        #     st.session_state["user_id"],
        #     prompt,
        #     assistant_reply,
        #     profile.to_dict()
        # )


# ========== 主程序 ==========

def main():
    """主函数"""
    
    # 初始化
    init_session_state()
    
    # 页面标题
    st.title("🍵 中药茶饮智能顾问")
    st.markdown("---")
    
    # 渲染侧边栏
    render_sidebar()
    
    # 渲染聊天历史
    render_chat_history()
    
    # 用户输入
    prompt = st.chat_input("请输入您的问题...")
    
    if prompt:
        handle_user_input(prompt)
        st.rerun()


if __name__ == '__main__':
    main()
