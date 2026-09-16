"""核心逻辑单元测试。

覆盖作业测试要求 T01~T06(当前以长箭关卡实测同一套判定规则),
以及关卡数据、长箭合法性的自动验证。
单格箭头的路径检测另有纯函数测试(TestPathDetection)覆盖。

运行方法(项目根目录下):
    py -m unittest discover -s tests -v
"""

import os
import sys
import unittest

# 让测试能找到项目根目录下的模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logic import (  # noqa: E402
    GameLogic,
    generate_random_level,
    is_path_clear,
    is_solvable,
    STATUS_PLAYING,
    STATUS_CLEARED,
    STATUS_FAILED,
    RESULT_FLY,
    RESULT_BLOCKED,
)
from levels import LEVELS  # noqa: E402


class TestPathDetection(unittest.TestCase):
    """单格箭头的四个方向路径检测(纯函数, 保留基础规则验证)。"""

    def test_right_free_and_blocked(self):
        grid = [list("→.→..")]  # 单行: (0,0) 被 (0,2) 阻挡, (0,2) 右侧无障碍
        self.assertFalse(is_path_clear(grid, 0, 0))
        self.assertTrue(is_path_clear(grid, 0, 2))

    def test_left_edge_outward(self):
        grid = [list("←....")]  # 贴左边朝左, 直接飞出
        self.assertTrue(is_path_clear(grid, 0, 0))

    def test_up_free_and_blocked(self):
        grid = [list("↑...."), list("....."), list("↑....")]
        self.assertTrue(is_path_clear(grid, 0, 0))   # 贴边朝上, 畅通
        self.assertFalse(is_path_clear(grid, 2, 0))  # 上方有 (0,0), 被阻挡

    def test_down_free_and_blocked(self):
        grid = [list("↓...."), list("....."), list("↓....")]
        self.assertTrue(is_path_clear(grid, 2, 0))   # 贴边朝下, 畅通
        self.assertFalse(is_path_clear(grid, 0, 0))  # 下方有 (2,0), 被阻挡


class TestClickBehavior(unittest.TestCase):
    """点击行为(第 1 关, 全为长箭), 对应作业测试要求 T01~T03。"""

    def test_t01_free_arrow_flies_away(self):
        """T01: 点击前方无阻挡的箭头 -> 箭头飞出并消失, 失误不变。"""
        g = GameLogic(0)  # 第 1 关: 长箭 [(0,0),(0,1)] 前方无阻挡
        result, arrow = g.click(0, 0)
        self.assertEqual(result, RESULT_FLY)
        self.assertIsNone(g._path_owner(0, 0))  # 整支箭已消失
        self.assertEqual(g.mistakes_left, 3)
        self.assertEqual(g.arrows_left, 3)  # 第 1 关共 4 支箭, 剩 3 支

    def test_t02_blocked_arrow_costs_mistake(self):
        """T02: 点击前方有阻挡的箭头 -> 不消失, 失误次数减 1。"""
        g = GameLogic(0)
        result, arrow = g.click(2, 3)  # 长箭 [(2,3),(3,3)] 被 [(4,2)..(4,4)] 挡住
        self.assertEqual(result, RESULT_BLOCKED)
        self.assertEqual(g.mistakes_left, 2)
        self.assertEqual(g.arrows_left, 4)  # 整支箭还在
        self.assertIsNotNone(g._path_owner(2, 3))

    def test_t03_edge_arrow_outward(self):
        """T03: 点击头部位于边缘且朝向棋盘外的箭头 -> 正常消失, 不越界。"""
        g = GameLogic(0)
        result, arrow = g.click(4, 4)  # 长箭 [(4,2),(4,3),(4,4)] 头部朝棋盘外
        self.assertEqual(result, RESULT_FLY)
        self.assertIsNone(g._path_owner(4, 4))


class TestLevelFlow(unittest.TestCase):
    """关卡流程(第 1 关), 对应作业测试要求 T04~T06。"""

    def test_t04_clear_level_wins(self):
        """T04: 清空本关全部箭头 -> 状态变为通关。"""
        g = GameLogic(0)
        # 第 1 关的一个通关顺序: 先解开被挡的长箭, 再点自由长箭
        order = [(4, 4), (2, 3), (0, 0), (1, 0)]
        for r, c in order:
            g.click(r, c)
        self.assertEqual(g.status, STATUS_CLEARED)
        self.assertEqual(g.arrows_left, 0)

    def test_t05_fail_after_mistakes_exhausted(self):
        """T05: 失误次数耗尽 -> 失败, 且重新开始后恢复。"""
        g = GameLogic(0)
        for _ in range(3):
            result, _ = g.click(2, 3)  # 连续点击被阻挡的长箭
        self.assertEqual(g.status, STATUS_FAILED)
        g.restart()
        self.assertEqual(g.status, STATUS_PLAYING)
        self.assertEqual(g.mistakes_left, 3)

    def test_t06_restart_mid_game(self):
        """T06: 游戏进行中重新开始 -> 布局和失误次数恢复初始。"""
        g = GameLogic(0)
        g.click(2, 3)   # 被阻挡, 失误 -1
        g.click(0, 0)   # 飞出 1 支
        self.assertEqual(g.mistakes_left, 2)
        self.assertEqual(g.arrows_left, 3)
        g.restart()
        self.assertEqual(g.mistakes_left, 3)
        self.assertEqual(g.arrows_left, 4)
        self.assertIsNotNone(g._path_owner(0, 0))
        self.assertEqual(g.status, STATUS_PLAYING)


class TestLevelData(unittest.TestCase):
    """关卡数据验证: 每关都必须可以通关, 且不是"白送"。"""

    def test_all_levels_solvable(self):
        for i, level in enumerate(LEVELS):
            self.assertTrue(
                is_solvable(level), f"第 {i + 1} 关无法通关, 请调整布局!"
            )

    def test_all_levels_have_blocked_arrow(self):
        """每关至少要有一个初始被阻挡的箭头(含长箭), 否则没有思考量。"""
        for i in range(len(LEVELS)):
            g = GameLogic(i)
            blocked = any(
                g.grid[r][c] != "." and g.is_blocked(r, c)
                for r in range(g.rows) for c in range(g.cols)
            ) or any(g.path_blocked(j) for j in range(len(g.paths)))
            self.assertTrue(blocked, f"第 {i + 1} 关没有初始阻挡")

    def test_grids_are_rectangular(self):
        for i, level in enumerate(LEVELS):
            widths = {len(row) for row in level["grid"]}
            self.assertEqual(len(widths), 1, f"第 {i + 1} 关各行宽度不一致")

    def test_grid_chars_valid(self):
        for i, level in enumerate(LEVELS):
            for row in level["grid"]:
                for cell in row:
                    self.assertIn(cell, ".→←↑↓", f"第 {i + 1} 关含非法字符: {cell!r}")


class TestAdvancedLevels(unittest.TestCase):
    """长箭玩法: 合法性、阻挡判定、进阶关卡通关。"""

    def test_paths_valid(self):
        """每支长箭: 至少 2 格、格子相邻不重复、不越界、不与单格箭头重叠。"""
        for i, level in enumerate(LEVELS):
            for j, p in enumerate(level.get("paths", [])):
                self.assertGreaterEqual(len(p), 2, f"第 {i + 1} 关路径 {j} 太短")
                for (r, c) in p:
                    in_bounds = (0 <= r < len(level["grid"])
                                 and 0 <= c < len(level["grid"][0]))
                    self.assertTrue(in_bounds, f"第 {i + 1} 关路径 {j} 越界")
                for (r1, c1), (r2, c2) in zip(p, p[1:]):
                    step = abs(r1 - r2) + abs(c1 - c2)
                    self.assertEqual(step, 1,
                                     f"第 {i + 1} 关路径 {j} 相邻格不相邻")
                self.assertEqual(len(set(p)), len(p),
                                 f"第 {i + 1} 关路径 {j} 有重复格")
                for (r, c) in p:
                    self.assertEqual(level["grid"][r][c], ".",
                                     f"第 {i + 1} 关路径 {j} 与单格箭头重叠")

    def test_multi_cell_arrow_fly(self):
        """点击长箭的身体任意格 -> 整支箭飞出消失。"""
        g = GameLogic(5)  # 第 6 关
        before = g.arrows_left
        result, arrow = g.click(3, 4)  # 自由长蛇
        self.assertEqual(result, RESULT_FLY)
        self.assertEqual(g.arrows_left, before - 1)
        # 按解算器给出的顺序继续解锁
        self.assertEqual(g.click(0, 1)[0], RESULT_FLY)
        self.assertEqual(g.click(3, 1)[0], RESULT_FLY)
        self.assertEqual(g.click(4, 4)[0], RESULT_FLY)

    def test_multi_cell_arrow_blocked(self):
        """长箭前方有阻挡 -> 整支箭不消失, 失误减 1。"""
        g = GameLogic(5)
        result, arrow = g.click(4, 2)  # 初始被阻挡的拐角长蛇
        self.assertEqual(result, RESULT_BLOCKED)
        self.assertEqual(g.mistakes_left, 2)
        self.assertEqual(g.arrows_left, 10)

    def test_path_blocked_by_other_path_body(self):
        """长箭被另一支长箭的箭身阻挡。"""
        g = GameLogic(7)  # 第 8 关
        result, _ = g.click(4, 5)  # 拐角长蛇被其他长蛇的箭身挡住
        self.assertEqual(result, RESULT_BLOCKED)

    def test_advanced_level_clear(self):
        """进阶关卡也能完整通关。"""
        g = GameLogic(5)  # 第 6 关, 10 支乱序长蛇、满格
        # 按解算器给出的通关顺序点击
        order = [(3, 4), (0, 1), (3, 1), (4, 4), (1, 5),
                 (1, 2), (0, 4), (4, 0), (4, 2), (2, 3)]
        for cell in order:
            g.click(*cell)
        self.assertEqual(g.status, STATUS_CLEARED)
        self.assertEqual(g.arrows_left, 0)


class TestExtensions(unittest.TestCase):
    """拓展功能: 撤销快照、求解指引、随机关卡生成。"""

    def test_snapshot_and_restore(self):
        """撤销: 快照-恢复能精确还原局面(布局/失误/状态)。"""
        g = GameLogic(0)
        snap = g.snapshot()
        g.click(0, 0)   # 飞出 1 支
        g.click(2, 3)   # 被阻挡, 失误 -1
        self.assertNotEqual(g.mistakes_left, snap["mistakes_left"])
        g.restore(snap)
        self.assertEqual(g.arrows_left, 4)
        self.assertEqual(g.mistakes_left, 3)
        self.assertEqual(g.status, snap["status"])
        self.assertIsNotNone(g._path_owner(0, 0))

    def test_restore_with_json_paths(self):
        """从 JSON 存档恢复(格子是列表而非元组)后, 占据与点击判定正常。

        回归测试: 存档 JSON 序列化会把元组变成列表, 恢复后必须
        规范化为元组, 否则字典键查找会崩溃(unhashable type: 'list')。
        """
        import json
        g = GameLogic(0)
        snap = json.loads(json.dumps(g.snapshot()))  # 模拟 JSON 往返
        g.click(0, 0)
        g.restore(snap)
        self.assertIsNotNone(g._path_owner(0, 0))
        result, _ = g.click(0, 0)
        self.assertEqual(result, RESULT_FLY)

    def test_find_solvable_cell(self):
        """求解指引: 找到的格子必然可飞出; 清空后返回 None。"""
        g = GameLogic(0)
        cell = g.find_solvable_cell()
        self.assertIsNotNone(cell)
        result, _ = g.click(*cell)
        self.assertEqual(result, RESULT_FLY)
        for _ in range(20):
            cell = g.find_solvable_cell()
            if cell is None:
                break
            g.click(*cell)
        self.assertIsNone(g.find_solvable_cell())

    def test_random_levels_solvable_and_valid(self):
        """随机生成的 60 个关卡全部数据合法且可通关。"""
        import random as _random
        for seed in range(60):
            level = generate_random_level(rng=_random.Random(seed))
            occupied = set()
            for p in level["paths"]:
                self.assertGreaterEqual(len(p), 2)
                for (r1, c1), (r2, c2) in zip(p, p[1:]):
                    self.assertEqual(abs(r1 - r2) + abs(c1 - c2), 1,
                                     f"seed {seed} 相邻格不相邻")
                for cell in p:
                    self.assertNotIn(cell, occupied, f"seed {seed} 重叠")
                    occupied.add(cell)
            self.assertGreaterEqual(len(occupied), 20, f"seed {seed} 填充太少")
            self.assertTrue(is_solvable(level), f"seed {seed} 不可通关")

    def test_random_level_playable(self):
        """随机关卡可以通过 GameLogic 实际通关。"""
        import random as _random
        level = generate_random_level(rng=_random.Random(7))
        g = GameLogic(level=level)
        steps = 0
        while g.status == STATUS_PLAYING and steps < 100:
            cell = g.find_solvable_cell()
            self.assertIsNotNone(cell, "随机关卡死锁!")
            result, _ = g.click(*cell)
            self.assertEqual(result, RESULT_FLY)
            steps += 1
        self.assertEqual(g.status, STATUS_CLEARED)


if __name__ == "__main__":
    unittest.main()
