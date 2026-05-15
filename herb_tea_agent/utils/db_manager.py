"""
数据库管理器 - SQLite 持久化存储

功能：
1. 用户画像持久化（跨会话）
2. 对话历史存储（可选）
3. 支持 user_id 关联
"""

import sqlite3
import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import contextmanager

from utils.path_tool import get_abs_path
from utils.config_handler import prompts_conf, agent_conf
from utils.logger_handler import logger


class DBManager:
    """SQLite 数据库管理器"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库路径，默认使用项目配置
        """
        if db_path is None:
            try:
                db_path = get_abs_path(agent_conf.get("db_path", "data/user_data.db"))
            except:
                # 备用路径
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(project_root, "data", "user_data.db")
        
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_tables()
    
    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            conn.close()
    
    def _init_tables(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 用户画像表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    profile_key TEXT NOT NULL,
                    profile_value TEXT,
                    source TEXT DEFAULT 'explicit',
                    confirmed INTEGER DEFAULT 1,
                    confidence TEXT DEFAULT 'high',
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(user_id, profile_key)
                )
            """)
            
            # 用户设置表（永久拒绝状态等）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE NOT NULL,
                    permanent_refusal INTEGER DEFAULT 0,
                    mining_enabled INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            
            # 对话历史表（可选）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    user_input TEXT,
                    agent_response TEXT,
                    profile_snapshot TEXT,
                    created_at TEXT
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_profile_user_id 
                ON user_profiles(user_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_user_id 
                ON conversation_history(user_id)
            """)
    
    # ========== 用户画像操作 ==========
    
    def save_profile(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """
        保存用户画像
        
        Args:
            user_id: 用户ID
            profile_data: 画像数据（格式与 UserProfile.to_dict() 一致）
        
        Returns:
            是否保存成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                
                # 保存每个画像键
                profile_dict = profile_data.get("profile", {})
                for key, entry in profile_dict.items():
                    cursor.execute("""
                        INSERT OR REPLACE INTO user_profiles 
                        (user_id, profile_key, profile_value, source, confirmed, confidence, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id,
                        key,
                        json.dumps(entry.get("value"), ensure_ascii=False),
                        entry.get("source", "explicit"),
                        1 if entry.get("confirmed", True) else 0,
                        entry.get("confidence", "high"),
                        now
                    ))
                
                # 保存用户设置
                cursor.execute("""
                    INSERT OR REPLACE INTO user_settings 
                    (user_id, permanent_refusal, mining_enabled, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    user_id,
                    1 if profile_data.get("permanent_refusal") else 0,
                    1 if profile_data.get("mining_allowed", True) else 0,
                    now
                ))
                
            return True
        except Exception as e:
            logger.error(f"保存用户画像失败: {e}")
            return False
    
    def load_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        加载用户画像
        
        Args:
            user_id: 用户ID
        
        Returns:
            画像数据字典，或 None（如果不存在）
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 加载画像数据
                cursor.execute("""
                    SELECT profile_key, profile_value, source, confirmed, confidence
                    FROM user_profiles
                    WHERE user_id = ?
                """, (user_id,))
                
                profile_dict = {}
                for row in cursor.fetchall():
                    try:
                        value = json.loads(row["profile_value"])
                    except:
                        value = row["profile_value"]
                    
                    profile_dict[row["profile_key"]] = {
                        "key": row["profile_key"],
                        "value": value,
                        "source": row["source"],
                        "confirmed": bool(row["confirmed"]),
                        "confidence": row["confidence"]
                    }
                
                # 加载用户设置
                cursor.execute("""
                    SELECT permanent_refusal, mining_enabled
                    FROM user_settings
                    WHERE user_id = ?
                """, (user_id,))
                
                settings_row = cursor.fetchone()
                permanent_refusal = False
                mining_enabled = True
                
                if settings_row:
                    permanent_refusal = bool(settings_row["permanent_refusal"])
                    mining_enabled = bool(settings_row["mining_enabled"])
                
                if not profile_dict and not permanent_refusal:
                    return None
                
                return {
                    "profile": profile_dict,
                    "permanent_refusal": permanent_refusal,
                    "mining_enabled": mining_enabled,
                    "mining_allowed": mining_enabled and not permanent_refusal
                }
                
        except Exception as e:
            logger.error(f"加载用户画像失败: {e}")
            return None
    
    def delete_profile(self, user_id: str) -> bool:
        """
        删除用户的所有数据
        
        Args:
            user_id: 用户ID
        
        Returns:
            是否删除成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 删除画像
                cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
                
                # 删除设置
                cursor.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
                
                # 删除对话历史（可选）
                cursor.execute("DELETE FROM conversation_history WHERE user_id = ?", (user_id,))
                
            return True
        except Exception as e:
            logger.error(f"删除用户数据失败: {e}")
            return False
    
    def has_profile(self, user_id: str) -> bool:
        """检查用户是否有保存的画像"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM user_profiles WHERE user_id = ?",
                    (user_id,)
                )
                return cursor.fetchone()[0] > 0
        except:
            return False
    
    # ========== 对话历史操作 ==========
    
    def save_conversation(self, user_id: str, user_input: str, 
                          agent_response: str, profile_snapshot: Dict = None) -> bool:
        """
        保存单条对话记录
        
        Args:
            user_id: 用户ID
            user_input: 用户输入
            agent_response: Agent回复
            profile_snapshot: 当时的画像快照（JSON格式）
        
        Returns:
            是否保存成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now().isoformat()
                
                cursor.execute("""
                    INSERT INTO conversation_history 
                    (user_id, user_input, agent_response, profile_snapshot, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    user_id,
                    user_input,
                    agent_response,
                    json.dumps(profile_snapshot, ensure_ascii=False) if profile_snapshot else None,
                    now
                ))
                
            return True
        except Exception as e:
            logger.error(f"保存对话历史失败: {e}")
            return False
    
    def get_conversation_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """
        获取用户的对话历史
        
        Args:
            user_id: 用户ID
            limit: 返回条数限制
        
        Returns:
            对话历史列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_input, agent_response, profile_snapshot, created_at
                    FROM conversation_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (user_id, limit))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "user_input": row["user_input"],
                        "agent_response": row["agent_response"],
                        "profile_snapshot": json.loads(row["profile_snapshot"]) 
                            if row["profile_snapshot"] else None,
                        "created_at": row["created_at"]
                    })
                
                return results
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return []
    
    def clear_conversation_history(self, user_id: str) -> bool:
        """清空用户的对话历史"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM conversation_history WHERE user_id = ?",
                    (user_id,)
                )
            return True
        except Exception as e:
            logger.error(f"清空对话历史失败: {e}")
            return False
    
    # ========== 统计信息 ==========
    
    def get_stats(self) -> Dict[str, int]:
        """获取数据库统计信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT COUNT(DISTINCT user_id) FROM user_profiles")
                user_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM user_profiles")
                profile_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM conversation_history")
                conversation_count = cursor.fetchone()[0]
                
                return {
                    "user_count": user_count,
                    "profile_count": profile_count,
                    "conversation_count": conversation_count
                }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"user_count": 0, "profile_count": 0, "conversation_count": 0}


# 全局单例
_db_instance: Optional[DBManager] = None


def get_db_manager() -> DBManager:
    """获取数据库管理器单例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = DBManager()
    return _db_instance


if __name__ == '__main__':
    # 测试代码
    db = DBManager()
    
    print("=== 数据库统计 ===")
    print(db.get_stats())
    
    # 测试保存/加载
    test_user_id = "test_user_001"
    
    test_profile = {
        "profile": {
            "taste_preference": {
                "key": "taste_preference",
                "value": "清淡",
                "source": "explicit",
                "confirmed": True,
                "confidence": "high"
            }
        },
        "permanent_refusal": False
    }
    
    print("\n=== 测试保存 ===")
    db.save_profile(test_user_id, test_profile)
    
    print("\n=== 测试加载 ===")
    loaded = db.load_profile(test_user_id)
    print(f"Loaded: {loaded}")
    
    print("\n=== 测试删除 ===")
    db.delete_profile(test_user_id)
    print(f"After delete: {db.load_profile(test_user_id)}")
