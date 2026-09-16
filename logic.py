"""游戏核心逻辑(不依赖 pygame, 方便单元测试)。

职责:
  - 维护当前关卡的棋盘状态(单格箭头 + 多格拐弯箭头)
  - 判断箭头是否被阻挡(路径检测)
  - 处理点击: 箭头飞出 / 被阻挡(消耗失误次数)
  - 关卡状态机: 进行中 / 通关 / 失败

箭头模型:
  - 单格箭头: 棋盘 grid 中的一个字符 '→' '←' '↑' '↓'
  - 多格箭头(进阶关卡): 占据一串相邻格子并可在中间拐弯,
    用 {"cells": [(r, c), ...], "dir": 头部方向字符} 表示;
    路径检测只看头部前方(头部方向到边界之间)是否还有其他箭头
"""

import random

from levels import LEVELS

# 箭头字符 -> 移动方向(行, 列)
DIRECTIONS = {
    "→": (0, 1),
    "←": (0, -1),
    "↑": (-1, 0),
    "↓": (1, 0),
}

# 关卡状态
STATUS_PLAYING = "playing"   # 进行中
STATUS_CLEARED = "cleared"   # 本关通关
STATUS_FAILED = "failed"     # 失误次数耗尽

# click() 的返回结果
RESULT_INVALID = "invalid"   # 点击无效(空格/越界/关卡已结束)
RESULT_FLY = "fly"           # 飞出成功
RESULT_BLOCKED = "blocked"   # 被阻挡, 消耗一次失误


def last_segment_dir(cells):
    """多格箭头的头部方向: 由最后一段的行进方向决定。"""
    (r1, c1), (r2, c2) = cells[-2], cells[-1]
    if r2 == r1:
        return "→" if c2 > c1 else "←"
    return "↓" if r2 > r1 else "↑"


def is_path_clear(grid, row, col):
    """检测单格箭头 (row, col) 到棋盘边界的路径是否畅通。

    纯棋盘版本(不考虑多格箭头), 供单元测试与简单棋盘使用。
    只检查箭头与边界之间(不含箭头自身)同一行/列是否还有其他箭头。
    返回 None 表示该位置是空格。
    """
    arrow = grid[row][col]
    if arrow == ".":
        return None
    rows, cols = len(grid), len(grid[0])
    dr, dc = DIRECTIONS[arrow]
    r, c = row + dr, col + dc
    while 0 <= r < rows and 0 <= c < cols:
        if grid[r][c] != ".":
            return False
        r += dr
        c += dc
    return True


class GameLogic:
    """一关游戏的完整状态。"""

    def __init__(self, level_index=None, level=None, mistakes=3):
        """两种用法:
        - GameLogic(level_index): 加载 LEVELS 中的第 level_index 关;
        - GameLogic(level=关卡字典): 加载自定义关卡(随机生成的"无限挑战")。
        """
        self.level_index = level_index
        self.total_mistakes = mistakes
        self._custom_level = level
        self.restart()

    def restart(self):
        """把当前关卡恢复到初始状态(布局、失误次数、状态)。"""
        level = (self._custom_level if self._custom_level is not None
                 else LEVELS[self.level_index])
        self.rows = len(level["grid"])
        self.cols = len(level["grid"][0])
        self.grid = [list(row) for row in level["grid"]]
        self.mistakes_left = self.total_mistakes
        self.status = STATUS_PLAYING
        # 多格拐弯箭头: {"cells": [(r, c), ...], "dir": 头部方向字符}
        # 格子统一规范化为元组(存档 JSON 恢复后是列表, 元组才能作字典键)
        self.paths = [
            {"cells": [tuple(c) for c in p], "dir": last_segment_dir(p)}
            for p in level.get("paths", [])
        ]

    @property
    def arrows_left(self):
        """棋盘上剩余的箭头数量(单格 + 多格)。"""
        return (sum(cell != "." for row in self.grid for cell in row)
                + len(self.paths))

    # ------------------------------------------------------------ 占据判断

    def _path_owner(self, r, c):
        """返回占据 (r, c) 的多格箭头下标, 没有则返回 None。"""
        for i, p in enumerate(self.paths):
            if (r, c) in p["cells"]:
                return i
        return None

    def occupied(self, r, c):
        """(r, c) 是否被任意箭头占据(单格或多格)。"""
        return self.grid[r][c] != "." or self._path_owner(r, c) is not None

    # ------------------------------------------------------------ 路径检测

    def is_blocked(self, row, col):
        """判断单格箭头 (row, col) 是否被阻挡(空格返回 None)。

        路径上的阻挡者既包括其他单格箭头, 也包括多格箭头的身体。
        """
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return None
        arrow = self.grid[row][col]
        if arrow == ".":
            return None
        dr, dc = DIRECTIONS[arrow]
        r, c = row + dr, col + dc
        while 0 <= r < self.rows and 0 <= c < self.cols:
            if self.occupied(r, c):
                return True
            r += dr
            c += dc
        return False

    def path_blocked(self, idx):
        """判断多格箭头 idx 是否被阻挡: 只看头部前方。"""
        p = self.paths[idx]
        head = p["cells"][-1]
        dr, dc = DIRECTIONS[p["dir"]]
        r, c = head[0] + dr, head[1] + dc
        while 0 <= r < self.rows and 0 <= c < self.cols:
            if self.occupied(r, c):
                return True
            r += dr
            c += dc
        return False

    # ------------------------------------------------------------ 撤销与求解

    def snapshot(self):
        """返回当前局面的深拷贝快照, 用于"撤销上一步"。"""
        return {
            "grid": [row[:] for row in self.grid],
            "paths": [{"cells": list(p["cells"]), "dir": p["dir"]}
                      for p in self.paths],
            "mistakes_left": self.mistakes_left,
            "status": self.status,
        }

    def restore(self, snap):
        """把局面恢复到快照记录的状态。

        快照可能来自 JSON 存档(格子是列表), 这里统一规范化为元组,
        保证之后作为字典键等用法正常。
        """
        self.grid = [row[:] for row in snap["grid"]]
        self.paths = [{"cells": [tuple(c) for c in p["cells"]], "dir": p["dir"]}
                      for p in snap["paths"]]
        self.mistakes_left = snap["mistakes_left"]
        self.status = snap["status"]

    def find_solvable_cell(self):
        """返回一个当前可飞出箭头的身体格 (r, c), 没有则返回 None。

        供"提示"高亮和"自动求解"使用。
        """
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] != "." and not self.is_blocked(r, c):
                    return r, c
        for i in range(len(self.paths)):
            if not self.path_blocked(i):
                return self.paths[i]["cells"][0]
        return None

    # ------------------------------------------------------------ 点击

    def _cost_mistake(self):
        """消耗一次失误, 耗尽则本关失败。"""
        self.mistakes_left -= 1
        if self.mistakes_left <= 0:
            self.status = STATUS_FAILED

    def click(self, row, col):
        """玩家点击 (row, col) 格子, 返回 (结果, 箭头数据)。

        - 无效点击(空格/越界/关卡已结束): (RESULT_INVALID, None)
        - 飞出: (RESULT_FLY, 数据); 单格箭头返回方向字符,
          多格箭头返回 {"cells": [...], "dir": ...} 字典
        - 被阻挡: (RESULT_BLOCKED, 数据), 失误次数减 1
        """
        if self.status != STATUS_PLAYING:
            return RESULT_INVALID, None
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return RESULT_INVALID, None

        # 先检查是否点中了多格箭头的任意一段
        idx = self._path_owner(row, col)
        if idx is not None:
            if self.path_blocked(idx):
                self._cost_mistake()
                return RESULT_BLOCKED, dict(self.paths[idx])
            p = self.paths.pop(idx)
            if self.arrows_left == 0:
                self.status = STATUS_CLEARED
            return RESULT_FLY, dict(p)

        arrow = self.grid[row][col]
        if arrow == ".":
            return RESULT_INVALID, None
        if self.is_blocked(row, col):
            self._cost_mistake()
            return RESULT_BLOCKED, arrow

        self.grid[row][col] = "."
        if self.arrows_left == 0:
            self.status = STATUS_CLEARED
        return RESULT_FLY, arrow


def generate_random_level(rows=6, cols=6, rng=None):
    """随机生成一个必定可通关的长箭关卡("无限挑战"用)。

    逆向出题法: 按"移除顺序的逆序"放置箭头——每支新箭的头部前方到
    边界之间不能经过已放置箭头的身体。这样按放置的逆序移除箭头时,
    每一支被移除的箭头都满足"前方无阻挡", 因此关卡必然可通关。

    用随机游走式生长(长蛇在空格中行走、随机拐弯)代替独立短箭,
    填充率显著更高, 多次尝试后取填充格子最多的棋盘。
    """
    rng = rng or random.Random()
    best_filled = 0
    best_paths = []
    for _ in range(40):  # 多次尝试, 取填充最多的结果
        occupied = set()
        paths = []
        for _ in range(200):
            empties = [(r, c) for r in range(rows) for c in range(cols)
                       if (r, c) not in occupied]
            if not empties:
                break
            # 随机游走: 从空格出发, 长度 2~7, 频繁随机拐弯(不走回头路)
            r0, c0 = rng.choice(empties)
            dr, dc = rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
            cells = [(r0, c0)]
            for _ in range(rng.randint(2, 7) - 1):
                if rng.random() < 0.6:
                    cands = [(0, 1), (0, -1), (1, 0), (-1, 0)]
                    rng.shuffle(cands)
                    for ndr, ndc in cands:
                        if (ndr, ndc) == (-dr, -dc):
                            continue
                        nr, nc = cells[-1][0] + ndr, cells[-1][1] + ndc
                        if (0 <= nr < rows and 0 <= nc < cols
                                and (nr, nc) not in occupied
                                and (nr, nc) not in cells):
                            dr, dc = ndr, ndc
                            break
                nr, nc = cells[-1][0] + dr, cells[-1][1] + dc
                if (0 <= nr < rows and 0 <= nc < cols
                        and (nr, nc) not in occupied
                        and (nr, nc) not in cells):
                    cells.append((nr, nc))
                else:
                    break
            if len(cells) < 2:  # 游走未走出起点(四邻均被占), 换起点
                continue
            # 关键约束: 头部前方到边界之间不得经过已放置的箭头,
            # 也不得穿过自己的箭身(游走可能绕回来指向走过的格子)
            d = last_segment_dir(cells)
            head = cells[-1]
            hdr, hdc = DIRECTIONS[d]
            r, c = head[0] + hdr, head[1] + hdc
            blocked = False
            while 0 <= r < rows and 0 <= c < cols:
                if (r, c) in occupied or (r, c) in cells:
                    blocked = True
                    break
                r += hdr
                c += hdc
            if blocked:
                continue  # 换一个起点重新生长
            for cell in cells:
                occupied.add(cell)
            paths.append(cells)
        if len(occupied) > best_filled:
            best_filled, best_paths = len(occupied), paths
        if best_filled == rows * cols:
            break
    level = {
        "name": "无限挑战",
        "grid": ["." * cols for _ in range(rows)],
        "paths": best_paths,
    }
    # 兜底: 理论上逆向出题已保证有解, 万一不满足则继续生成
    if not is_solvable(level):
        return generate_random_level(rows, cols, rng)
    return level


def is_solvable(level):
    """用贪心法验证一个关卡是否存在通关顺序, 供关卡设计和测试使用。

    level: levels.py 中的关卡字典 {"grid": [...], "paths": [...] (可选)}

    思路: 反复把所有"当前可飞出"的箭头全部移除, 直到没有可移除的为止。
    若最终棋盘被清空, 则该关可以通关。
    正确性说明: 移除一个可飞出的箭头只会让其他箭头更可能飞出,
    绝不会产生新的阻挡, 因此只要存在解, 贪心法一定能找到。
    """
    rows = len(level["grid"])
    cols = len(level["grid"][0])
    grid = [list(row) for row in level["grid"]]
    paths = [{"cells": list(p), "dir": last_segment_dir(p)}
             for p in level.get("paths", [])]

    def occupied(r, c):
        if grid[r][c] != ".":
            return True
        return any((r, c) in p["cells"] for p in paths)

    def path_free(p):
        head = p["cells"][-1]
        dr, dc = DIRECTIONS[p["dir"]]
        r, c = head[0] + dr, head[1] + dc
        while 0 <= r < rows and 0 <= c < cols:
            if occupied(r, c):
                return False
            r += dr
            c += dc
        return True

    changed = True
    while changed:
        changed = False
        # 单格箭头
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] == ".":
                    continue
                dr, dc = DIRECTIONS[grid[r][c]]
                rr, cc = r + dr, c + dc
                blocked = False
                while 0 <= rr < rows and 0 <= cc < cols:
                    if occupied(rr, cc):
                        blocked = True
                        break
                    rr += dr
                    cc += dc
                if not blocked:
                    grid[r][c] = "."
                    changed = True
        # 多格箭头
        remaining = [p for p in paths if not path_free(p)]
        if len(remaining) != len(paths):
            paths = remaining
            changed = True
    return all(cell == "." for row in grid for cell in row) and not paths
