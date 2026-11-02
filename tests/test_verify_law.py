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


if __name__ == "__main__":
    unittest.main()
