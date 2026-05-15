"""
用户画像挖掘与合规边界控制模块 v2.0

功能：
1. 敏感词分级检测（红/黄/白/绿/灰）
2. 画像存储（explicit/inferred + confirmed状态）
3. 画像确认机制（推断信息需用户确认）
4. 本轮/永久拒绝区分
5. 画像生命周期管理
"""

import re
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class SourceType(Enum):
    """画像信息来源类型"""
    EXPLICIT = "explicit"  # 用户直接说出的信息
    INFERRED = "inferred"  # Agent 推断的信息


class SensitiveLevel(Enum):
    """敏感词级别"""
    RED = "red"       # 🔴 完全拒绝
    YELLOW = "yellow"  # 🟡 需免责声明
    WHITE = "white"    # 🟢 正常回答
    GREEN = "green"    # 🟢 鼓励引导
    GRAY = "gray"      # ⚫ 模糊回答


class ActionType(Enum):
    """敏感词处理动作"""
    REJECT = "reject"      # 直接拒绝
    DISCLAIMER = "disclaimer"  # 需免责声明
    NORMAL = "normal"     # 正常回答
    ENCOURAGE = "encourage"  # 鼓励引导
    VAGUE = "vague"       # 模糊回答


@dataclass
class ProfileEntry:
    """单条画像条目"""
    key: str
    value: Any
    source: SourceType  # explicit / inferred
    confirmed: bool = True  # 是否已确认（推断信息需要确认）
    confidence: str = "high"  # high / medium / low
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source": self.source.value if isinstance(self.source, SourceType) else self.source,
            "confirmed": self.confirmed,
            "confidence": self.confidence,
            "timestamp": self.timestamp
        }


class UserProfile:
    """用户画像管理类 v2.0"""
    
    def __init__(self):
        self._profile: Dict[str, ProfileEntry] = {}
        self._conversation_history: List[Dict[str, str]] = []
        
        # 画像挖掘控制
        self._temp_refusal_active: bool = False  # 本轮拒绝
        self._permanent_refusal_active: bool = False  # 永久拒绝
        self._mining_count: int = 0  # 本轮挖掘次数
        
        # 敏感词分级配置
        self._init_sensitive_keywords()
        
        # 可挖掘的画像维度定义
        self.MINABLE_DIMENSIONS = {
            "drinking_mode": {
                "key": "drinking_mode",
                "display_name": "饮用方式",
                "question_templates": [
                    "您是自己喝还是和家人一起分享呢？",
                    "平时是独自品茶还是与亲友共饮？",
                ],
                "values": ["独自饮用", "与家人分享", "与朋友分享", "办公分享"]
            },
            "usage_frequency": {
                "key": "usage_frequency",
                "display_name": "使用频率",
                "question_templates": [
                    "您大概多久喝一次养生茶呢？",
                    "平时喝茶的频率是怎样的？",
                ],
                "values": ["每天", "每周几次", "偶尔", "定期调理"]
            },
            "budget_range": {
                "key": "budget_range",
                "display_name": "预算偏好",
                "question_templates": [
                    "您对养生茶的品质有什么偏好吗？",
                    "您期望的价位是怎样的呢？",
                ],
                "values": ["经济实惠", "适中", "品质优先", "高端"]
            },
            "family_structure": {
                "key": "family_structure",
                "display_name": "家庭结构",
                "question_templates": [
                    "家里有老人或孩子一起喝吗？",
                    "是全家一起养生还是主要为自己调理？",
                ],
                "values": ["单身", "二人世界", "三口之家", "有老人", "有小孩"]
            },
            "health_goal": {
                "key": "health_goal",
                "display_name": "养生目标",
                "question_templates": [
                    "您希望通过养生茶达到什么效果呢？",
                    "平时有什么养生的需求吗？",
                ],
                "values": ["清热解毒", "补气养血", "调理肠胃", "安神助眠", "美容养颜", "增强免疫"]
            },
            "taste_preference": {
                "key": "taste_preference",
                "display_name": "口感偏好",
                "question_templates": [
                    "您喜欢什么口感的茶呢？",
                    "比较偏爱清香还是浓郁一些的？",
                ],
                "values": ["清淡", "微甜", "回甘", "浓郁", "微苦"]
            },
            "usage_scenario": {
                "key": "usage_scenario",
                "display_name": "使用场景",
                "question_templates": [
                    "您一般什么时候喝养生茶呢？",
                    "是在办公室还是家里泡茶？",
                ],
                "values": ["早晨", "下午茶", "睡前", "办公室", "居家", "随时"]
            },
        }
    
    def _init_sensitive_keywords(self):
        """初始化敏感词分级配置"""
        # 🔴 红词：完全拒绝
        self.red_keywords = [
            "病历", "确诊", "处方", "用药记录", "检查报告", "ct报告", "核磁报告",
            "精神分裂", "抑郁症确诊", "癌症", "肿瘤", "白血病", "艾滋病",
            "治疗方案", "化疗", "放疗", "透析", "手术"
        ]
        
        # 🟡 黄词：需免责声明
        self.yellow_keywords = [
            "高血压", "糖尿病", "高血脂", "高血糖", "心脏病", "冠心病",
            "心肌梗死", "心绞痛", "心率不齐", "脂肪肝", "肝硬化",
            "肾结石", "肾囊肿", "痛风", "风湿", "类风湿", "骨质疏松",
            "支气管炎", "哮喘", "肺气肿", "慢性咽炎", "胃溃疡", "十二指肠溃疡"
        ]
        
        # 🟢 白词：正常回答
        self.white_keywords = [
            "失眠", "睡眠不好", "胃胀", "胃酸", "疲劳", "乏力", "没精神",
            "怕冷", "怕热", "容易上火", "长痘", "便秘", "拉肚子",
            "熬夜", "压力大", "久坐", "眼睛干", "眼睛疲劳", "脱发",
            "掉头发", "气血不足", "脸色暗", "气色差"
        ]
        
        # 🟢 绿词：鼓励引导（用于画像挖掘）
        self.green_keywords = [
            "清淡", "浓郁", "酸甜", "微苦", "回甘", "香甜",
            "办公室", "居家", "送礼", "送长辈", "送朋友",
            "自己喝", "全家", "和孩子", "和家人", "老公", "老婆",
            "孩子", "老人", "长辈", "父母"
        ]
        
        # ⚫ 灰词：边界试探
        self.gray_keywords = [
            "工资", "月薪", "年收入", "存款", "收入", "多少钱",
            "住址", "地址", "家庭住址", "门牌号",
            "身份证", "身份证号", "护照号",
            "电话", "手机号", "微信号", "qq号"
        ]
        
        # 本轮拒绝关键词
        self.temp_refusal_keywords = [
            "别问了", "不想说", "不方便", "不要问", "不想回答"
        ]
        
        # 永久拒绝关键词
        self.permanent_refusal_keywords = [
            "以后都别问了", "再也不问了", "不要再来烦我", "永久关闭", "永远别问"
        ]
        
        # 恢复引导关键词
        self.resume_keywords = [
            "可以问了", "继续问吧", "恢复吧", "开始问吧", "继续问"
        ]
    
    # ========== 敏感词分级检测 ==========
    
    def classify_sensitive(self, text: str) -> Dict[str, Any]:
        """
        分级检测敏感词，返回级别和行为建议
        
        Returns:
            {
                "level": "red"|"yellow"|"white"|"green"|"gray",
                "action": "reject"|"disclaimer"|"normal"|"encourage"|"vague",
                "keyword": matched_keyword or None
            }
        """
        if not text:
            return {"level": "white", "action": "normal", "keyword": None}
        
        text_lower = text.lower()
        
        # 🔴 红词检测
        for kw in self.red_keywords:
            if kw in text_lower:
                return {"level": "red", "action": "reject", "keyword": kw}
        
        # 🟡 黄词检测
        for kw in self.yellow_keywords:
            if kw in text_lower:
                return {"level": "yellow", "action": "disclaimer", "keyword": kw}
        
        # ⚫ 灰词检测
        for kw in self.gray_keywords:
            if kw in text_lower:
                return {"level": "gray", "action": "vague", "keyword": kw}
        
        # 🟢 绿词检测
        for kw in self.green_keywords:
            if kw in text_lower:
                return {"level": "green", "action": "encourage", "keyword": kw}
        
        # 🟢 白词检测
        for kw in self.white_keywords:
            if kw in text_lower:
                return {"level": "white", "action": "normal", "keyword": kw}
        
        return {"level": "white", "action": "normal", "keyword": None}
    
    def is_sensitive(self, text: str) -> Tuple[bool, Optional[str]]:
        """兼容旧接口：检测是否包含敏感词"""
        result = self.classify_sensitive(text)
        return result["level"] in ["red", "yellow"], result.get("keyword")
    
    def detect_yellow_keywords(self, text: str) -> Tuple[bool, Optional[str]]:
        """检测是否包含黄词（需免责声明）"""
        if not text:
            return False, None
        text_lower = text.lower()
        for kw in self.yellow_keywords:
            if kw in text_lower:
                return True, kw
        return False, None
    
    # ========== 拒绝信号检测 ==========
    
    def detect_refusal(self, text: str) -> Tuple[str, Optional[str]]:
        """
        检测拒绝信号类型
        
        Returns:
            ("temp"|"permanent"|"resume"|"none", matched_keyword or None)
        """
        if not text:
            return "none", None
        
        text_lower = text.lower()
        
        # 永久拒绝优先检测
        for kw in self.permanent_refusal_keywords:
            if kw in text_lower:
                return "permanent", kw
        
        # 本轮拒绝检测
        for kw in self.temp_refusal_keywords:
            if kw in text_lower:
                return "temp", kw
        
        # 恢复引导检测
        for kw in self.resume_keywords:
            if kw in text_lower:
                return "resume", kw
        
        return "none", None
    
    def handle_refusal(self, refusal_type: str):
        """处理拒绝信号"""
        if refusal_type == "temp":
            self._temp_refusal_active = True
        elif refusal_type == "permanent":
            self._permanent_refusal_active = True
            self._temp_refusal_active = False
        elif refusal_type == "resume":
            self._permanent_refusal_active = False
    
    def clear_temp_refusal(self):
        """清除本轮拒绝标志（下轮自动恢复）"""
        self._temp_refusal_active = False
    
    def is_mining_allowed(self) -> bool:
        """检查是否允许画像挖掘/引导"""
        return not self._temp_refusal_active and not self._permanent_refusal_active
    
    def get_mining_status(self) -> Dict[str, Any]:
        """获取画像挖掘状态"""
        return {
            "temp_refusal": self._temp_refusal_active,
            "permanent_refusal": self._permanent_refusal_active,
            "mining_allowed": self.is_mining_allowed(),
            "mining_count": self._mining_count
        }
    
    # ========== 画像存储 ==========
    
    def set(self, key: str, value: Any, source: SourceType = SourceType.EXPLICIT,
            confidence: str = "high", confirmed: bool = None) -> None:
        """
        设置画像键值对
        
        Args:
            key: 画像键
            value: 画像值
            source: explicit(用户明确说) / inferred(Agent推断)
            confidence: high/medium/low
            confirmed: 是否已确认（None时：explicit自动为True，inferred自动为False）
        """
        if confirmed is None:
            confirmed = source == SourceType.EXPLICIT
        
        self._profile[key] = ProfileEntry(
            key=key,
            value=value,
            source=source,
            confidence=confidence,
            confirmed=confirmed,
            timestamp=datetime.now().isoformat()
        )
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取画像值"""
        entry = self._profile.get(key)
        return entry.value if entry else default
    
    def get_entry(self, key: str) -> Optional[ProfileEntry]:
        """获取画像条目（含完整信息）"""
        return self._profile.get(key)
    
    def get_source(self, key: str) -> Optional[str]:
        """获取画像来源"""
        entry = self._profile.get(key)
        return entry.source.value if entry and isinstance(entry.source, SourceType) else entry.source if entry else None
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有画像（仅值）"""
        return {k: v.value for k, v in self._profile.items()}
    
    def get_all_with_details(self) -> Dict[str, Dict[str, Any]]:
        """获取所有画像（含来源、确认状态等详情）"""
        return {k: v.to_dict() for k, v in self._profile.items()}
    
    def get_explicit(self) -> Dict[str, Any]:
        """只获取用户明确说的信息（confirmed=True）"""
        return {k: v.value for k, v in self._profile.items()
                if v.source == SourceType.EXPLICIT and v.confirmed}
    
    def get_inferred(self) -> Dict[str, Any]:
        """只获取Agent推断的信息"""
        return {k: v.value for k, v in self._profile.items()
                if v.source == SourceType.INFERRED}
    
    def get_pending_inferences(self) -> Dict[str, Any]:
        """获取待确认的推断信息"""
        return {k: v.value for k, v in self._profile.items()
                if v.source == SourceType.INFERRED and not v.confirmed}
    
    def get_confirmed_inferences(self) -> Dict[str, Any]:
        """获取已确认的推断信息"""
        return {k: v.value for k, v in self._profile.items()
                if v.source == SourceType.INFERRED and v.confirmed}
    
    # ========== 画像确认/拒绝 ==========
    
    def confirm_inference(self, key: str) -> bool:
        """
        确认推断的信息
        
        Returns:
            是否确认成功
        """
        if key in self._profile and self._profile[key].source == SourceType.INFERRED:
            entry = self._profile[key]
            entry.confirmed = True
            entry.source = SourceType.EXPLICIT  # 升级为explicit
            entry.timestamp = datetime.now().isoformat()
            return True
        return False
    
    def reject_inference(self, key: str) -> bool:
        """
        拒绝/删除推断的信息
        
        Returns:
            是否删除成功
        """
        if key in self._profile and self._profile[key].source == SourceType.INFERRED:
            del self._profile[key]
            return True
        return False
    
    def update(self, key: str, value: Any, source: str = "explicit",
               confirmed: bool = None, confidence: str = "high") -> None:
        """
        更新画像（兼容旧接口）
        
        Args:
            source: "explicit" 或 "inferred"
            confirmed: 是否已确认
        """
        source_type = SourceType.EXPLICIT if source == "explicit" else SourceType.INFERRED
        self.set(key, value, source_type, confidence, confirmed)
    
    # ========== 画像生命周期管理 ==========
    
    def clear_session(self) -> None:
        """清空本轮会话的画像（保留系统配置）"""
        self._profile.clear()
        self._conversation_history.clear()
        self._mining_count = 0
        # 注意：不清除永久拒绝状态
    
    def full_reset(self) -> None:
        """完全重置，包括永久拒绝状态"""
        self.clear_session()
        self._temp_refusal_active = False
        self._permanent_refusal_active = False
    
    def increment_mining_count(self):
        """增加挖掘计数"""
        self._mining_count += 1
    
    def should_stop_mining(self) -> bool:
        """判断是否应该停止挖掘"""
        return self._mining_count >= 3 or not self.is_mining_allowed()
    
    # ========== 画像更新（从对话中提取）==========
    
    def update_from_conversation(self, user_input: str, agent_response: str) -> List[str]:
        """
        从对话中提取并更新画像信息
        
        注意：此方法只用于提取**用户明确说**的信息
        Agent推断的信息需要通过 confirm_inference 处理
        
        Returns:
            更新了哪些画像键
        """
        updated_keys = []
        combined_text = f"{user_input} {agent_response}"
        
        # 饮用场景提取
        if self._pattern_match(combined_text, r"自己[喝品]|独自|一个人"):
            self.set("drinking_mode", "独自饮用", SourceType.EXPLICIT, "high")
            updated_keys.append("drinking_mode")
        
        if self._pattern_match(combined_text, r"家人|老公|老婆|父母|一起|分享"):
            self.set("drinking_mode", "与家人分享", SourceType.EXPLICIT, "high")
            updated_keys.append("drinking_mode")
            
        if self._pattern_match(combined_text, r"朋友|同事|同事们"):
            self.set("drinking_mode", "与朋友分享", SourceType.EXPLICIT, "high")
            updated_keys.append("drinking_mode")
        
        if self._pattern_match(combined_text, r"办公|上班|公司"):
            self.set("usage_scenario", "办公室", SourceType.EXPLICIT, "high")
            updated_keys.append("usage_scenario")
            
        if self._pattern_match(combined_text, r"家里|回家|下班后"):
            self.set("usage_scenario", "居家", SourceType.EXPLICIT, "high")
            updated_keys.append("usage_scenario")
        
        if self._pattern_match(combined_text, r"每天|天天|日常"):
            self.set("usage_frequency", "每天", SourceType.EXPLICIT, "medium")
            updated_keys.append("usage_frequency")
            
        if self._pattern_match(combined_text, r"偶尔|想起来|有空"):
            self.set("usage_frequency", "偶尔", SourceType.EXPLICIT, "medium")
            updated_keys.append("usage_frequency")
        
        # 口感偏好提取
        if self._pattern_match(combined_text, r"清淡|清甜|清香"):
            self.set("taste_preference", "清淡", SourceType.EXPLICIT, "high")
            updated_keys.append("taste_preference")
            
        if self._pattern_match(combined_text, r"浓郁|醇厚"):
            self.set("taste_preference", "浓郁", SourceType.EXPLICIT, "high")
            updated_keys.append("taste_preference")
            
        if self._pattern_match(combined_text, r"微甜|有点甜|甜"):
            self.set("taste_preference", "微甜", SourceType.EXPLICIT, "high")
            updated_keys.append("taste_preference")
            
        if self._pattern_match(combined_text, r"微苦|有点苦|苦"):
            self.set("taste_preference", "微苦", SourceType.EXPLICIT, "high")
            updated_keys.append("taste_preference")
        
        # 养生目标提取
        if self._pattern_match(combined_text, r"睡眠|失眠|睡不着|助眠"):
            self.set("health_goal", "安神助眠", SourceType.EXPLICIT, "high")
            updated_keys.append("health_goal")
            
        if self._pattern_match(combined_text, r"美容|养颜|皮肤|气色"):
            self.set("health_goal", "美容养颜", SourceType.EXPLICIT, "high")
            updated_keys.append("health_goal")
            
        if self._pattern_match(combined_text, r"免疫|抵抗力|体质"):
            self.set("health_goal", "增强免疫", SourceType.EXPLICIT, "high")
            updated_keys.append("health_goal")
            
        if self._pattern_match(combined_text, r"肠胃|消化|便秘"):
            self.set("health_goal", "调理肠胃", SourceType.EXPLICIT, "high")
            updated_keys.append("health_goal")
            
        if self._pattern_match(combined_text, r"补气|气血|气色|面色"):
            self.set("health_goal", "补气养血", SourceType.EXPLICIT, "high")
            updated_keys.append("health_goal")
        
        # 存储对话历史
        self._conversation_history.append({
            "user": user_input,
            "agent": agent_response,
            "timestamp": datetime.now().isoformat()
        })
        
        return updated_keys
    
    def add_inference(self, key: str, value: Any, confidence: str = "medium") -> None:
        """
        添加Agent推断的画像（需用户确认）
        
        Args:
            key: 画像键
            value: 推断的值
            confidence: 推断置信度
        """
        self.set(key, value, SourceType.INFERRED, confidence, confirmed=False)
    
    def _pattern_match(self, text: str, pattern: str) -> bool:
        """检查文本是否匹配模式"""
        return bool(re.search(pattern, text))
    
    # ========== 上下文摘要 ==========
    
    def get_context_summary(self) -> str:
        """生成画像上下文摘要，用于注入到 LLM"""
        if not self._profile:
            return "暂无用户画像信息"
        
        summary_parts = ["【当前用户画像】"]
        
        explicit = self.get_explicit()
        if explicit:
            summary_parts.append("用户明确偏好：")
            for k, v in explicit.items():
                dim_name = self.MINABLE_DIMENSIONS.get(k, {}).get("display_name", k)
                summary_parts.append(f"  - {dim_name}: {v}")
        
        pending = self.get_pending_inferences()
        if pending:
            summary_parts.append("待确认推断：")
            for k, v in pending.items():
                dim_name = self.MINABLE_DIMENSIONS.get(k, {}).get("display_name", k)
                summary_parts.append(f"  - {dim_name}: {v}（请确认）")
        
        return "\n".join(summary_parts)
    
    def get_minable_dimensions_status(self) -> Dict[str, bool]:
        """获取各维度画像的采集状态"""
        return {
            dim_key: dim_key in self._profile
            for dim_key in self.MINABLE_DIMENSIONS.keys()
        }
    
    def get_next_mining_dimension(self) -> Optional[Dict]:
        """获取下一个可挖掘的维度"""
        for dim_key, dim_info in self.MINABLE_DIMENSIONS.items():
            if dim_key not in self._profile:
                return dim_info
        return None
    
    def format_mining_question(self) -> Optional[str]:
        """生成下一个场景化挖掘问题"""
        next_dim = self.get_next_mining_dimension()
        if next_dim and self.is_mining_allowed():
            import random
            return random.choice(next_dim["question_templates"])
        return None
    
    # ========== 画像摘要（用于UI展示）==========
    
    def get_profile_summary(self) -> Dict[str, Any]:
        """获取画像摘要（用于前端展示）"""
        mining_status = self.get_mining_status()
        
        return {
            "profile_count": len(self._profile),
            "explicit_count": len(self.get_explicit()),
            "inferred_count": len(self.get_inferred()),
            "pending_count": len(self.get_pending_inferences()),
            "temp_refusal": mining_status["temp_refusal"],
            "permanent_refusal": mining_status["permanent_refusal"],
            "mining_allowed": mining_status["mining_allowed"],
            "mining_count": mining_status["mining_count"],
            "dimensions_status": self.get_minable_dimensions_status(),
            "profile": self.get_all_with_details()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """导出完整数据（用于持久化）"""
        return {
            "profile": {k: v.to_dict() for k, v in self._profile.items()},
            "temp_refusal": self._temp_refusal_active,
            "permanent_refusal": self._permanent_refusal_active,
            "mining_count": self._mining_count
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """从字典加载数据（用于持久化恢复）"""
        if "profile" in data:
            for k, v in data["profile"].items():
                source = SourceType.EXPLICIT if v.get("source") == "explicit" else SourceType.INFERRED
                self._profile[k] = ProfileEntry(
                    key=v["key"],
                    value=v["value"],
                    source=source,
                    confirmed=v.get("confirmed", True),
                    confidence=v.get("confidence", "high"),
                    timestamp=v.get("timestamp", "")
                )
        
        if "temp_refusal" in data:
            self._temp_refusal_active = data["temp_refusal"]
        if "permanent_refusal" in data:
            self._permanent_refusal_active = data["permanent_refusal"]
        if "mining_count" in data:
            self._mining_count = data["mining_count"]


# 全局单例
_profile_instance: Optional[UserProfile] = None


def get_profile_instance() -> UserProfile:
    """获取用户画像实例"""
    global _profile_instance
    if _profile_instance is None:
        _profile_instance = UserProfile()
    return _profile_instance


if __name__ == '__main__':
    # 测试代码
    profile = UserProfile()
    
    print("=== 敏感词分级检测测试 ===")
    test_cases = [
        ("我有高血压，能喝这个茶吗？", "yellow"),
        ("我正在做化疗", "red"),
        ("我想调理失眠", "white"),
        ("我喜欢清淡的口感", "green"),
        ("你家住在哪里？", "gray"),
    ]
    
    for text, expected_level in test_cases:
        result = profile.classify_sensitive(text)
        status = "✓" if result["level"] == expected_level else "✗"
        print(f"{status} '{text}' -> {result['level']} ({result['action']})")
    
    print("\n=== 拒绝信号检测测试 ===")
    refusal_tests = [
        ("别问了", "temp"),
        ("以后都别问了", "permanent"),
        ("可以问了", "resume"),
        ("今天天气不错", "none"),
    ]
    
    for text, expected in refusal_tests:
        result, kw = profile.detect_refusal(text)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{text}' -> {result}")
    
    print("\n=== 画像存储测试 ===")
    profile.set("taste", "清淡", SourceType.EXPLICIT)
    print(f"Explicit: {profile.get_explicit()}")
    
    profile.add_inference("has_elder", True, "medium")
    print(f"Pending inferences: {profile.get_pending_inferences()}")
    
    profile.confirm_inference("has_elder")
    print(f"After confirm: {profile.get_explicit()}")
    
    print("\n=== 上下文摘要 ===")
    print(profile.get_context_summary())
