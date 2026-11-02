"""法规完整性校验的行为测试。"""
import importlib
import unittest


class VerifyLawTests(unittest.TestCase):
    def test_missing_article_is_reported(self):
        try:
            module = importlib.import_module("scripts.verify_law")
        except ModuleNotFoundError:
            self.fail("scripts.verify_law 尚未实现")
        result = module.inspect_text("第一条 原文\n第三条 原文")
        self.assertEqual(result["articles"], [1, 3])
        self.assertEqual(result["missing"], [2])
        self.assertFalse(result["continuous"])

    def test_notes_are_excluded_before_style_detection(self):
        module = importlib.import_module("scripts.verify_law")
        result = module.inspect_text("一、原文\n二、原文\n三、原文\n## 入库建议（标签）\n第五条的 3 项")
        self.assertEqual(result["articles"], [1, 2, 3])
        self.assertTrue(result["continuous"])

    def test_both_styles(self):
        module = importlib.import_module("scripts.verify_law")
        for text in ["第一条 原文\n第二条 原文", "一、原文\n二、原文"]:
            self.assertEqual(module.inspect_text(text)["articles"], [1, 2])


if __name__ == "__main__":
    unittest.main()
