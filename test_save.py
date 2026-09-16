"""存档模块单元测试。"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import save  # noqa: E402


class TestSave(unittest.TestCase):

    def test_roundtrip(self):
        """存档-读档往返: 数据完整一致。"""
        data = {"unlocked": 3, "stars": {"0": 3, "2": 1},
                "session": {"level": 2, "elapsed": 45.5}}
        path = os.path.join(tempfile.gettempdir(), "arrow_test_save.json")
        self.assertTrue(save.save_to(path, data))
        loaded = save.load_from(path)
        self.assertEqual(loaded["unlocked"], 3)
        self.assertEqual(loaded["stars"]["0"], 3)
        self.assertEqual(loaded["session"]["elapsed"], 45.5)
        os.remove(path)

    def test_load_missing_file(self):
        """读不存在的存档 -> 返回 None。"""
        path = os.path.join(tempfile.gettempdir(), "arrow_no_such_save.json")
        self.assertIsNone(save.load_from(path))

    def test_load_corrupted_file(self):
        """读损坏的存档 -> 返回 None(不抛异常)。"""
        path = os.path.join(tempfile.gettempdir(), "arrow_bad_save.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        self.assertIsNone(save.load_from(path))
        os.remove(path)


if __name__ == "__main__":
    unittest.main()
