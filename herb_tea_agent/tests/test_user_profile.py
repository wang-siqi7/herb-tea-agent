"""
用户画像模块测试用例 v2.0

运行方式：
python tests/test_user_profile.py
"""

import unittest
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from utils.user_profile import UserProfile, SourceType


class TestSensitiveLevel(unittest.TestCase):
    """功能6: 敏感词分级测试"""
    
    def setUp(self):
        self.profile = UserProfile()
    
    def test_red_keywords(self):
        """🔴 红词：完全拒绝"""
        test_cases = [
            "我有病历可以喝茶吗",
            "医生确诊我有XX病",
            "处方药会影响茶吗",
            "正在接受化疗",
            "精神分裂症",
            "抑郁症确诊",
        ]
        for text in test_cases:
            result = self.profile.classify_sensitive(text)
            self.assertEqual(result["level"], "red", f"Failed: {text}")
            self.assertEqual(result["action"], "reject")
    
    def test_yellow_keywords(self):
        """🟡 黄词：需免责声明"""
        test_cases = [
            "我有高血压能喝茶吗",
            "糖尿病患者",
            "高血脂饮食",
            "心脏病要注意什么",
            "冠心病",
        ]
        for text in test_cases:
            result = self.profile.classify_sensitive(text)
            self.assertEqual(result["level"], "yellow", f"Failed: {text}")
            self.assertEqual(result["action"], "disclaimer")
    
    def test_white_keywords(self):
        """🟢 白词：正常回答"""
        test_cases = [
            "我失眠怎么办",
            "胃胀气",
            "经常疲劳",
            "怕冷",
            "容易上火",
        ]
        for text in test_cases:
            result = self.profile.classify_sensitive(text)
            self.assertIn(result["level"], ["white", "green"], f"Failed: {text}")
    
    def test_green_keywords(self):
        """🟢 绿词：鼓励引导"""
        test_cases = [
            "我喜欢清淡的口感",
            "在办公室喝茶",
            "送长辈",
            "全家一起喝",
            "和孩子分享",
        ]
        for text in test_cases:
            result = self.profile.classify_sensitive(text)
            self.assertEqual(result["action"], "encourage", f"Failed: {text}")
    
    def test_gray_keywords(self):
        """⚫ 灰词：模糊回答"""
        test_cases = [
            "工资多少合适",
            "住址在哪",
            "身份证号",
            "电话是多少",
        ]
        for text in test_cases:
            result = self.profile.classify_sensitive(text)
            self.assertEqual(result["level"], "gray", f"Failed: {text}")
            self.assertEqual(result["action"], "vague")


class TestRefusalDetection(unittest.TestCase):
    """功能3: 本轮/永久拒绝测试"""
    
    def setUp(self):
        self.profile = UserProfile()
    
    def test_temp_refusal(self):
        """本轮拒绝"""
        for text in ["别问了", "不想说", "不方便"]:
            refusal_type, _ = self.profile.detect_refusal(text)
            self.assertEqual(refusal_type, "temp", f"Failed: {text}")
    
    def test_permanent_refusal(self):
        """永久拒绝"""
        for text in ["以后都别问了", "再也不问了", "不要再来烦我"]:
            refusal_type, _ = self.profile.detect_refusal(text)
            self.assertEqual(refusal_type, "permanent", f"Failed: {text}")
    
    def test_resume_keywords(self):
        """恢复引导"""
        for text in ["可以问了", "继续问吧", "恢复吧"]:
            refusal_type, _ = self.profile.detect_refusal(text)
            self.assertEqual(refusal_type, "resume", f"Failed: {text}")
    
    def test_refusal_handling(self):
        """拒绝信号处理"""
        # 本轮拒绝
        self.profile.handle_refusal("temp")
        self.assertTrue(self.profile._temp_refusal_active)
        self.assertFalse(self.profile.is_mining_allowed())
        
        # 永久拒绝
        self.profile.handle_refusal("permanent")
        self.assertTrue(self.profile._permanent_refusal_active)
        self.assertFalse(self.profile.is_mining_allowed())
        
        # 恢复
        self.profile.handle_refusal("resume")
        self.assertFalse(self.profile._permanent_refusal_active)
        self.assertTrue(self.profile.is_mining_allowed())


class TestProfileSource(unittest.TestCase):
    """功能4: 画像来源区分测试"""
    
    def setUp(self):
        self.profile = UserProfile()
    
    def test_explicit_source(self):
        """显式信息（用户明确说）"""
        self.profile.set("taste", "清淡", SourceType.EXPLICIT)
        
        entry = self.profile.get_entry("taste")
        self.assertEqual(entry.source, SourceType.EXPLICIT)
        self.assertTrue(entry.confirmed)
        
        # 只获取 explicit
        explicit = self.profile.get_explicit()
        self.assertIn("taste", explicit)
    
    def test_inferred_source(self):
        """推断信息（Agent推断）"""
        self.profile.set("has_elder", True, SourceType.INFERRED)
        
        entry = self.profile.get_entry("has_elder")
        self.assertEqual(entry.source, SourceType.INFERRED)
        self.assertFalse(entry.confirmed)
        
        # 待确认推断
        pending = self.profile.get_pending_inferences()
        self.assertIn("has_elder", pending)
    
    def test_confirm_inference(self):
        """确认推断信息"""
        self.profile.set("has_elder", True, SourceType.INFERRED)
        
        # 确认前
        self.assertFalse(self.profile.get_entry("has_elder").confirmed)
        
        # 确认
        result = self.profile.confirm_inference("has_elder")
        self.assertTrue(result)
        
        # 确认后
        entry = self.profile.get_entry("has_elder")
        self.assertTrue(entry.confirmed)
        self.assertEqual(entry.source, SourceType.EXPLICIT)  # 升级为 explicit
    
    def test_reject_inference(self):
        """拒绝推断信息"""
        self.profile.set("has_elder", True, SourceType.INFERRED)
        
        # 拒绝
        result = self.profile.reject_inference("has_elder")
        self.assertTrue(result)
        
        # 删除后不存在
        self.assertIsNone(self.profile.get_entry("has_elder"))


class TestYellowDisclaimer(unittest.TestCase):
    """功能2: 黄词免责测试"""
    
    def setUp(self):
        self.profile = UserProfile()
    
    def test_detect_yellow(self):
        """检测黄词"""
        test_cases = [
            ("我有高血压", True, "高血压"),
            ("糖尿病饮食注意", True, "糖尿病"),
            ("高血脂怎么办", True, "高血脂"),
            ("普通感冒", False, None),
        ]
        for text, expected, expected_kw in test_cases:
            detected, kw = self.profile.detect_yellow_keywords(text)
            self.assertEqual(detected, expected, f"Failed: {text}")
            if expected:
                self.assertIn(expected_kw, kw, f"Failed: {text}")


class TestProfilePersistence(unittest.TestCase):
    """功能8: 持久化测试"""
    
    def test_to_dict(self):
        """导出数据"""
        profile = UserProfile()
        profile.set("taste", "清淡", SourceType.EXPLICIT)
        profile.add_inference("has_child", True)
        
        data = profile.to_dict()
        
        self.assertIn("profile", data)
        self.assertIn("taste", data["profile"])
        self.assertIn("has_child", data["profile"])
    
    def test_from_dict(self):
        """导入数据"""
        profile = UserProfile()
        
        data = {
            "profile": {
                "taste": {
                    "key": "taste",
                    "value": "清淡",
                    "source": "explicit",
                    "confirmed": True,
                    "confidence": "high"
                }
            },
            "permanent_refusal": False
        }
        
        profile.from_dict(data)
        
        self.assertEqual(profile.get("taste"), "清淡")
        self.assertEqual(profile.get_source("taste"), "explicit")


class TestProfileLifecycle(unittest.TestCase):
    """功能7: 画像生命周期测试"""
    
    def setUp(self):
        self.profile = UserProfile()
    
    def test_clear_session(self):
        """清空会话（保留永久设置）"""
        self.profile.set("taste", "清淡")
        self.profile._permanent_refusal_active = True
        
        self.profile.clear_session()
        
        self.assertEqual(len(self.profile._profile), 0)
        self.assertTrue(self.profile._permanent_refusal_active)  # 永久设置保留
    
    def test_full_reset(self):
        """完全重置"""
        self.profile.set("taste", "清淡")
        self.profile._permanent_refusal_active = True
        self.profile._temp_refusal_active = True
        
        self.profile.full_reset()
        
        self.assertEqual(len(self.profile._profile), 0)
        self.assertFalse(self.profile._permanent_refusal_active)
        self.assertFalse(self.profile._temp_refusal_active)
    
    def test_mining_count(self):
        """挖掘计数"""
        self.assertEqual(self.profile._mining_count, 0)
        
        self.profile.increment_mining_count()
        self.assertEqual(self.profile._mining_count, 1)
        
        self.profile.increment_mining_count()
        self.assertEqual(self.profile._mining_count, 2)
    
    def test_should_stop_mining(self):
        """停止挖掘判断"""
        # 初始不应停止
        self.assertFalse(self.profile.should_stop_mining())
        
        # 挖掘3次后应停止
        self.profile._mining_count = 3
        self.assertTrue(self.profile.should_stop_mining())
        
        # 永久拒绝后应停止
        self.profile._mining_count = 0
        self.profile._permanent_refusal_active = True
        self.assertTrue(self.profile.should_stop_mining())


class TestContextSummary(unittest.TestCase):
    """上下文摘要测试"""
    
    def setUp(self):
        self.profile = UserProfile()
    
    def test_empty_profile(self):
        """空画像"""
        summary = self.profile.get_context_summary()
        self.assertEqual(summary, "暂无用户画像信息")
    
    def test_with_explicit(self):
        """有显式信息"""
        self.profile.set("taste", "清淡", SourceType.EXPLICIT)
        self.profile.set("scenario", "办公室", SourceType.EXPLICIT)
        
        summary = self.profile.get_context_summary()
        
        self.assertIn("用户明确偏好", summary)
        self.assertIn("清淡", summary)
        self.assertIn("办公室", summary)
    
    def test_with_pending(self):
        """有待确认推断"""
        self.profile.add_inference("has_elder", True)
        
        summary = self.profile.get_context_summary()
        
        self.assertIn("待确认推断", summary)
        self.assertIn("has_elder", summary)


if __name__ == '__main__':
    print("=" * 60)
    print("Running User Profile v2.0 Tests")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestSensitiveLevel))
    suite.addTests(loader.loadTestsFromTestCase(TestRefusalDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestProfileSource))
    suite.addTests(loader.loadTestsFromTestCase(TestYellowDisclaimer))
    suite.addTests(loader.loadTestsFromTestCase(TestProfilePersistence))
    suite.addTests(loader.loadTestsFromTestCase(TestProfileLifecycle))
    suite.addTests(loader.loadTestsFromTestCase(TestContextSummary))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("PASS: All tests passed!")
    else:
        print(f"FAIL: {len(result.failures)} failures, {len(result.errors)} errors")
    print("=" * 60)
