"""Pygame 图形界面: 窗口、画面切换、动画与按钮。

画面状态机:
  start     -> 开始界面(标题 + 玩法说明 + 开始按钮)
  game      -> 游戏界面(棋盘 + HUD 信息栏)
  win       -> 单关通关结算界面
  fail      -> 失败结算界面
  all_clear -> 全部关卡通关结算界面

动画:
  FlyingArrow      箭头飞出动画(残影 + 逐渐缩小)
  CollisionEffect  碰撞反馈(撞击回弹 + 晃动 + 变红 + 飘字)
  Confetti         通关撒花
"""

import math
import os
import random

import pygame

import levels
import logic
import save
import settings
import sounds


# ------------------------------------------------------------------ 小工具

_FONT_CACHE = {}


def load_font(size, bold=False):
    """加载中文字体: 依次尝试系统字体文件, 找不到则退回默认字体。"""
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = [
        f"C:/Windows/Fonts/msyh{'bd' if bold else ''}.ttc",  # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",                      # 黑体
        "C:/Windows/Fonts/simsun.ttc",                      # 宋体
    ]
    font = None
    for path in candidates:
        if os.path.exists(path):
            try:
                font = pygame.font.Font(path, size)
                break
            except OSError:
                pass
    if font is None:
        font = pygame.font.SysFont("microsoftyahei,simhei", size, bold=bold)
    _FONT_CACHE[key] = font
    return font


def draw_text(surface, text, size, color, center=None, topleft=None, bold=False):
    """居中或按左上角绘制文字, 返回文字区域。"""
    font = load_font(size, bold)
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center is not None:
        rect.center = center
    elif topleft is not None:
        rect.topleft = topleft
    surface.blit(img, rect)
    return rect


def lerp_color(c1, c2, t):
    """在两个颜色之间线性插值。"""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


_ARROW_POINTS_CACHE = {}


def arrow_points(direction, size):
    """生成朝 direction 方向、边长约 size 的箭头多边形顶点(中心在原点)。

    箭身(杆)占全长约 2/3, 箭头(三角头)占约 1/3, 造型偏修长。
    """
    key = (direction, size)
    if key in _ARROW_POINTS_CACHE:
        return _ARROW_POINTS_CACHE[key]
    head = size * 0.34
    half = size * 0.11
    pts = [
        (-size / 2, -half),
        (size / 2 - head, -half),
        (size / 2 - head, -size / 2),
        (size / 2, 0),
        (size / 2 - head, size / 2),
        (size / 2 - head, half),
        (-size / 2, half),
    ]
    angle = {"→": 0.0, "←": math.pi, "↑": -math.pi / 2, "↓": math.pi / 2}[direction]
    ca, sa = math.cos(angle), math.sin(angle)
    rotated = [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]
    _ARROW_POINTS_CACHE[key] = rotated
    return rotated


def draw_arrow(surface, center, direction, size, color):
    """在 center 处绘制一个箭头。"""
    cx, cy = center
    pts = [(cx + x, cy + y) for x, y in arrow_points(direction, size)]
    pygame.draw.polygon(surface, color, pts)


def draw_arrow_head(surface, center, direction, size, color):
    """只绘制箭头三角部分(用于多格箭头)。

    size 取 CELL_SIZE*0.62 时, 头部与单格箭头的头部同尺寸同比例;
    三角底边位于箭身线端之后, 保证箭尾与箭头衔接处连成一体。
    """
    cx, cy = center
    angle = {"→": 0.0, "←": math.pi, "↑": -math.pi / 2, "↓": math.pi / 2}[direction]
    ca, sa = math.cos(angle), math.sin(angle)
    pts = [(size * 0.5, 0),
           (-size * 0.16, -size * 0.5),
           (-size * 0.16, size * 0.5)]
    rotated = [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]
    pygame.draw.polygon(surface, color, rotated)


def polyline_length(points):
    """折线总长度。"""
    total = 0.0
    for i in range(len(points) - 1):
        total += math.hypot(points[i + 1][0] - points[i][0],
                            points[i + 1][1] - points[i][1])
    return total


def point_and_dir_at(points, d):
    """折线上距起点 d 处的位置, 以及该处线段的方向字符。"""
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        if d <= seg or i == len(points) - 2:
            t = min(1.0, d / seg) if seg > 0 else 0.0
            pos = (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
            if abs(x2 - x1) >= abs(y2 - y1):
                dirc = "→" if x2 > x1 else "←"
            else:
                dirc = "↓" if y2 > y1 else "↑"
            return pos, dirc
        d -= seg
    return points[-1], None


def polyline_clip(points, d0, d1):
    """截取折线上 [d0, d1] 区间, 返回新的点列(含两端截点)。"""
    pts = []
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        a, b = max(d0, 0.0), min(d1, seg)
        if a <= b:
            pts.append((x1 + (x2 - x1) * (a / seg if seg else 0.0),
                        y1 + (y2 - y1) * (a / seg if seg else 0.0)))
            pts.append((x1 + (x2 - x1) * (b / seg if seg else 1.0),
                        y1 + (y2 - y1) * (b / seg if seg else 1.0)))
        d0 -= seg
        d1 -= seg
        if d1 < 0:
            break
    return pts


# ------------------------------------------------------------------ 组件

class Button:
    """简单按钮: 悬停变色 + 点击检测, 支持多行文字(text 用 \\n 分隔)与禁用态。"""

    def __init__(self, center, size, text, font_size=26):
        self.rect = pygame.Rect(0, 0, *size)
        self.rect.center = center
        self.text = text
        self.font_size = font_size
        self.enabled = True

    def hovered(self, mouse_pos):
        return self.rect.collidepoint(mouse_pos)

    def draw(self, surface, mouse_pos):
        hover = self.hovered(mouse_pos)
        if self.enabled:
            color = settings.BUTTON_HOVER if hover else settings.BUTTON_COLOR
        else:
            color = (66, 70, 100)  # 禁用灰
        pygame.draw.rect(surface, color, self.rect, border_radius=12)
        pygame.draw.rect(
            surface, tuple(max(0, c - 35) for c in color),
            self.rect, width=3, border_radius=12)
        lines = self.text.split("\n")
        step = self.font_size + 6
        for i, line in enumerate(lines):
            draw_text(surface, line, self.font_size - (4 if i > 0 else 0),
                      settings.TEXT_COLOR if self.enabled else settings.TEXT_DIM,
                      center=(self.rect.centerx,
                              self.rect.centery
                              + (i - (len(lines) - 1) / 2) * step),
                      bold=(i == 0))


class FlyingArrow:
    """箭头飞出棋盘动画: 沿所在行/列的轨道飞行(带轨道光带) + 残影 + 逐渐缩小。"""

    def __init__(self, start, end, direction):
        self.start = pygame.Vector2(start)
        self.end = pygame.Vector2(end)
        self.direction = direction
        self.time = 0.0
        self.duration = 0.45

    def update(self, dt):
        self.time += dt

    @property
    def alive(self):
        return self.time < self.duration

    def _pos_at(self, t):
        p = min(1.0, t / self.duration)
        return self.start.lerp(self.end, p ** 1.7)  # 加速飞出

    def draw(self, surface):
        p = min(1.0, self.time / self.duration)
        size = settings.CELL_SIZE * 0.62 * (1 - 0.3 * p)  # 飞出过程中缩小
        if size <= 4:
            return
        pos = self._pos_at(self.time)
        # 轨道光带: 沿箭头所在行/列的中心线, 从起点延伸到当前位置, 随飞行淡出
        dr, dc = logic.DIRECTIONS[self.direction]
        band = settings.CELL_SIZE * 0.6
        if dr == 0:  # 水平方向 -> 光带沿所在行
            track = pygame.Rect(0, 0,
                                int(abs(pos.x - self.start.x)) + band, band)
            track.center = ((pos.x + self.start.x) / 2, self.start.y)
        else:        # 垂直方向 -> 光带沿所在列
            track = pygame.Rect(0, 0, band,
                                int(abs(pos.y - self.start.y)) + band)
            track.center = (self.start.x, (pos.y + self.start.y) / 2)
        glow = pygame.Surface(track.size, pygame.SRCALPHA)
        glow.fill((*settings.ARROW_COLORS[self.direction],
                   max(0, int(46 * (1 - p)))))
        surface.blit(glow, track)
        # 残影: 之前几个时刻的位置, 越来越淡
        for i in (3, 2, 1):
            t = self.time - i * 0.045
            if t > 0:
                ghost = pygame.Surface((int(size * 2), int(size * 2)),
                                       pygame.SRCALPHA)
                draw_arrow(ghost, (size, size), self.direction, size,
                           settings.ARROW_COLORS[self.direction])
                ghost.set_alpha(50 * (4 - i))
                pos = self._pos_at(t)
                surface.blit(ghost, ghost.get_rect(
                    center=(int(pos.x), int(pos.y))))
        # 本体
        layer = pygame.Surface((int(size * 2), int(size * 2)), pygame.SRCALPHA)
        draw_arrow(layer, (size, size), self.direction, size,
                   settings.ARROW_LIGHTS[self.direction])
        pos = self._pos_at(self.time)
        surface.blit(layer, layer.get_rect(center=(int(pos.x), int(pos.y))))


class PathFlyingArrow:
    """多格箭头飞出动画: 整支箭沿自身轨道(含拐弯)滑出棋盘。

    轨道 = 从箭尾格子中心经过所有拐角到头部, 再沿头部方向延伸到棋盘外。
    动画期间头部沿轨道前进, 箭尾在轨道上落后头部一个"箭身长度"跟随,
    因此整支箭会像沿着轨道滑行一样经过拐角。
    """

    def __init__(self, cells, direction, color, cell_rect_fn, rows, cols):
        pts = [cell_rect_fn(r, c).center for r, c in cells]
        self.track = list(pts)
        head = pts[-1]
        dr, dc = logic.DIRECTIONS[direction]
        dist = settings.CELL_SIZE * max(rows, cols) + 150
        self.track.append((head[0] + dc * dist, head[1] + dr * dist))
        self.direction = direction
        self.color = color
        self.light = tuple(min(255, x + 55) for x in color)
        self.body_len = polyline_length(pts)   # 箭身总长(尾到头部)
        self.total = polyline_length(self.track)
        self.time = 0.0
        self.duration = 0.55

    def update(self, dt):
        self.time += dt

    @property
    def alive(self):
        return self.time < self.duration

    def _head_dist(self):
        p = min(1.0, self.time / self.duration)
        return self.body_len + (self.total - self.body_len) * (p ** 1.7)

    def draw(self, surface):
        head_d = self._head_dist()
        tail_d = max(0.0, head_d - self.body_len)
        sub = polyline_clip(self.track, tail_d, head_d)
        if len(sub) < 2:
            return
        # 箭身宽度与普通箭头一致; 拐弯处补画实心圆保证连贯
        width = int(settings.CELL_SIZE * 0.14)
        outline = tuple(max(0, c - 60) for c in self.color)
        pygame.draw.lines(surface, outline, False, sub, width + 4)
        pygame.draw.lines(surface, self.color, False, sub, width)
        for x, y in sub[1:-1]:
            pygame.draw.circle(surface, outline, (int(x), int(y)), width // 2 + 2)
        for x, y in sub[1:-1]:
            pygame.draw.circle(surface, self.color, (int(x), int(y)), width // 2)
        head_pos, head_dir = point_and_dir_at(self.track, head_d)
        draw_arrow_head(surface, head_pos,
                        head_dir or self.direction,
                        settings.CELL_SIZE * 0.62, self.light)


class CollisionEffect:
    """碰撞反馈: 箭头向前撞一下弹回 + 晃动 + 变红 + 飘出"被阻挡"文字。"""

    def __init__(self, direction):
        self.direction = direction
        self.time = 0.0
        self.duration = 0.6

    def update(self, dt):
        self.time += dt

    @property
    def alive(self):
        return self.time < self.duration

    def progress(self):
        return min(1.0, self.time / self.duration)

    def shake_offset(self):
        """抖动偏移: 沿前进方向撞一下再弹回, 同时垂直方向轻微晃动。"""
        fade = 1 - self.progress()
        dr, dc = logic.DIRECTIONS[self.direction]
        along = math.sin(self.time * 40) * 8 * fade   # 前后撞击
        perp = math.sin(self.time * 55) * 4 * fade    # 左右晃动
        return (dr * along + dc * perp, dc * along + dr * perp)

    def draw_text_hint(self, surface, cell_rect):
        """"被阻挡"文字, 从箭头上方飘起并淡出。"""
        p = self.progress()
        img = load_font(22, bold=True).render("被阻挡!", True, settings.DANGER)
        img.set_alpha(int(255 * (1 - p)))
        rect = img.get_rect(midbottom=(cell_rect.centerx,
                                       cell_rect.top - 4 - 30 * p))
        surface.blit(img, rect)


class Confetti:
    """通关撒花: 彩色小纸片从画面顶部飘落。"""

    COLORS = [
        settings.ACCENT, settings.SUCCESS, settings.BUTTON_COLOR,
        settings.DANGER, (255, 220, 120),
    ]

    def __init__(self, count=60):
        self.parts = []
        for _ in range(count):
            self.parts.append({
                "x": random.uniform(0, settings.WINDOW_WIDTH),
                "y": random.uniform(-300, -20),
                "vx": random.uniform(-40, 40),
                "vy": random.uniform(120, 260),
                "size": random.uniform(4, 9),
                "color": random.choice(self.COLORS),
                "rot": random.uniform(0, 360),
                "vr": random.uniform(-180, 180),
            })

    def update(self, dt):
        for p in self.parts:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["rot"] += p["vr"] * dt

    def draw(self, surface):
        for p in self.parts:
            if p["y"] > settings.WINDOW_HEIGHT + 20:
                continue
            img = pygame.Surface((int(p["size"] * 2), int(p["size"] * 1.2)),
                                 pygame.SRCALPHA)
            img.fill(p["color"])
            rotated = pygame.transform.rotate(img, p["rot"])
            surface.blit(rotated, (p["x"], p["y"]))


# ------------------------------------------------------------------ 主程序

class ArrowGame:
    """游戏主程序: 窗口、画面状态机、输入处理与动画。"""

    STATE_START = "start"
    STATE_SELECT = "select"
    STATE_GAME = "game"
    STATE_WIN = "win"
    STATE_FAIL = "fail"
    STATE_ALL_CLEAR = "all_clear"

    def __init__(self):
        try:
            pygame.init()
        except pygame.error:
            # 个别机器无声卡时初始化会失败, 用虚拟音频驱动绕过
            os.environ["SDL_AUDIODRIVER"] = "dummy"
            pygame.init()
        self.screen = pygame.display.set_mode(
            (settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT))
        pygame.display.set_caption("一箭又一箭 - 点击箭头解谜")
        self.clock = pygame.time.Clock()

        self.state = self.STATE_START
        self.mouse_pos = (0, 0)
        self.flying = []      # 正在播放飞出动画的箭头
        self.collisions = {}  # {(r, c): CollisionEffect} 碰撞反馈
        self.confetti = None  # 通关撒花
        self.mistake_flash = 0.0  # 失误圆点闪烁计时
        self.pending_state = None  # 结算前等待动画结束
        self.pending_timer = 0.0

        # 拓展功能状态
        self.unlocked = 0          # 已解锁的最大关卡下标(本局会话)
        self.stars = {}            # 固定关卡 -> 历史最高星级
        self.elapsed = 0.0         # 本关用时(秒)
        self.undo_stack = []       # 撤销快照栈
        self.auto_solving = False  # AI 自动求解中
        self.auto_timer = 0.0
        self.hint_cells = set()    # 提示高亮的箭头格子
        self.hint_timer = 0.0
        self.arrow_colors = {}     # 长箭头部格子 -> 颜色(图着色, 每关加载时计算)

        cx = settings.WINDOW_WIDTH // 2
        self.btn_continue = Button((cx - 220, 545), (190, 64), "继续游戏")
        self.btn_start = Button((cx, 545), (190, 64), "开始游戏")
        self.btn_select = Button((cx + 220, 545), (190, 64), "选择关卡")
        self.btn_restart = Button((740, 26), (150, 46), "重新开始", font_size=22)
        self.btn_undo = Button((598, 100), (84, 40), "撤销", font_size=18)
        self.btn_hint = Button((688, 100), (84, 40), "提示", font_size=18)
        self.btn_solve = Button((790, 100), (106, 40), "自动求解", font_size=16)
        self.btn_next = Button((cx - 110, 460), (190, 60), "下一关")
        self.btn_retry = Button((cx - 110, 460), (190, 60), "重新开始")
        self.btn_replay = Button((cx - 110, 460), (190, 60), "再玩一次")
        self.btn_menu = Button((cx + 110, 460), (190, 60), "返回主菜单")
        self.btn_back = Button((cx, 660), (220, 56), "返回主菜单")

        # 关卡选择按钮: 1~8 关 + 无限挑战
        self.level_buttons = []
        for i in range(levels.TOTAL_LEVELS + 1):
            row, col = divmod(i, 3)
            x = 210 + col * 170
            y = 200 + row * 140
            self.level_buttons.append(Button((x + 70, y + 55), (140, 110),
                                             "", font_size=24))

        self.sounds = sounds.build_sounds()

        # 读取存档: 恢复解锁进度与历史星级
        saved = save.load()
        if saved:
            self.unlocked = int(saved.get("unlocked", 0))
            self.stars = {int(k): v for k, v in saved.get("stars", {}).items()}
        self._saved_once = False
        self._startup = True   # 启动阶段的加载不触发存档
        self.load_level(0)
        self._startup = False

    # ------------------------------------------------------------ 关卡管理

    def _reset_play_state(self):
        """清空动画与拓展功能状态(加载/重开/撤消后调用)。"""
        self.flying = []
        self.collisions = {}
        self.confetti = None
        self.pending_state = None
        self.pending_timer = 0.0
        self.elapsed = 0.0
        self.undo_stack = []
        self.auto_solving = False
        self.hint_cells = set()
        self.hint_timer = 0.0

    def load_level(self, index):
        """加载第 index 关(index 从 0 开始), 并立即存档为新关卡。"""
        self.level_index = index
        self.logic = logic.GameLogic(index, mistakes=settings.MISTAKES_PER_LEVEL)
        self._reset_play_state()
        self._recolor_arrows()
        if not self._startup:
            self._save_progress()

    def load_random_level(self):
        """随机生成一个"无限挑战"关卡(逆向出题法, 必然可通关), 并立即存档。"""
        self.level_index = levels.TOTAL_LEVELS  # 哨兵值, 表示随机关卡
        self.logic = logic.GameLogic(level=logic.generate_random_level(),
                                     mistakes=settings.MISTAKES_PER_LEVEL)
        self._reset_play_state()
        self._recolor_arrows()
        if not self._startup:
            self._save_progress()

    def restart_level(self):
        """重新开始当前关卡(布局、失误次数、动画全部复位), 并立即存档。"""
        self.logic.restart()
        self._reset_play_state()
        self._recolor_arrows()
        if not self._startup:
            self._save_progress()

    def _recolor_arrows(self):
        """给长箭分配颜色(图着色): 相邻箭头尽量不同色, 每关至少 3 种颜色。

        相邻 = 两支箭任意格子的四邻域相交。算法确定性贪心:
        同一棋盘永远得到同一套颜色(撤销/重开/存档恢复后一致)。
        颜色以长箭头部格子为键, 箭头飞出后键仍在, 撤销恢复后颜色不变。
        """
        paths = self.logic.paths
        n = len(paths)
        cells_of = [set(p["cells"]) for p in paths]
        neighbors = [set() for _ in range(n)]
        for i in range(n):
            for (r, c) in cells_of[i]:
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    for j in range(n):
                        if j != i and (r + dr, c + dc) in cells_of[j]:
                            neighbors[i].add(j)
        palette = [settings.ARROW_COLORS[d] for d in ("→", "←", "↑", "↓")]
        colors = {}
        for i in range(n):  # 贪心: 取邻居未使用的第一个颜色
            used = {colors[j] for j in neighbors[i] if j in colors}
            for c in palette:
                if c not in used:
                    colors[i] = c
                    break
            else:
                colors[i] = palette[i % len(palette)]
        # 保证每关至少 3 种颜色(稀疏关卡贪心可能只用 2 种)
        present = set(colors.values())
        for c in palette:
            if len(present) >= 3:
                break
            if c in present:
                continue
            for i in range(n):
                if all(colors[j] != c for j in neighbors[i]):
                    colors[i] = c
                    present.add(c)
                    break
            else:
                colors[0] = c  # 极端情况: 强制换色, 满足"至少 3 色"
                present.add(c)
        self.arrow_colors = {paths[i]["cells"][-1]: colors[i]
                             for i in range(n)}

    # ------------------------------------------------------------ 存档

    def _save_progress(self):
        """把解锁进度、星级与当前对局写入本地存档。"""
        self._saved_once = True
        save.save({
            "unlocked": self.unlocked,
            "stars": {str(k): v for k, v in self.stars.items()},
            "session": {
                "level": self.level_index,
                "random": self.level_index >= levels.TOTAL_LEVELS,
                "random_level": (self.logic._custom_level
                                 if self.level_index >= levels.TOTAL_LEVELS
                                 else None),
                "snap": self.logic.snapshot(),
                "elapsed": self.elapsed,
                "undo": self.undo_stack,
            },
        })

    def _resume_session(self):
        """从存档恢复上一次对局(进行中的局面/用时/撤销栈可完整还原)。"""
        data = save.load()
        session = data.get("session") if data else None
        if not session:
            return
        if session.get("random") and session.get("random_level"):
            self.level_index = levels.TOTAL_LEVELS
            self.logic = logic.GameLogic(level=session["random_level"],
                                         mistakes=settings.MISTAKES_PER_LEVEL)
        else:
            self.level_index = int(session.get("level", 0))
            self.logic = logic.GameLogic(self.level_index,
                                         mistakes=settings.MISTAKES_PER_LEVEL)
        self._reset_play_state()
        snap = session.get("snap")
        if snap and snap.get("status") == logic.STATUS_PLAYING:
            self.logic.restore(snap)  # 进行中的局: 完整还原
            self.elapsed = float(session.get("elapsed", 0.0))
            self.undo_stack = list(session.get("undo", []))
        else:
            self.elapsed = 0.0  # 已结算的局: 恢复为全新开局
        self._recolor_arrows()
        self.state = self.STATE_GAME

    # ------------------------------------------------------------ 坐标换算

    def _grid_origin(self):
        """棋盘左上角坐标(棋盘整体在信息栏下方居中)。"""
        rows, cols = self.logic.rows, self.logic.cols
        board_w = cols * (settings.CELL_SIZE + settings.CELL_GAP) - settings.CELL_GAP
        board_h = rows * (settings.CELL_SIZE + settings.CELL_GAP) - settings.CELL_GAP
        ox = (settings.WINDOW_WIDTH - board_w) // 2
        area_top = settings.HUD_HEIGHT + 10
        area_bottom = settings.WINDOW_HEIGHT - 26
        oy = area_top + (area_bottom - area_top - board_h) // 2
        return ox, oy

    def _cell_rect(self, r, c):
        ox, oy = self._grid_origin()
        x = ox + c * (settings.CELL_SIZE + settings.CELL_GAP)
        y = oy + r * (settings.CELL_SIZE + settings.CELL_GAP)
        return pygame.Rect(x, y, settings.CELL_SIZE, settings.CELL_SIZE)

    def _cell_at(self, pos):
        """返回鼠标位置所在的格子 (r, c), 不在棋盘内返回 None。"""
        for r in range(self.logic.rows):
            for c in range(self.logic.cols):
                if self._cell_rect(r, c).collidepoint(pos):
                    return r, c
        return None

    # ------------------------------------------------------------ 输入处理

    def on_click(self, pos):
        """按当前画面分发点击事件。"""
        if self.state == self.STATE_START:
            if self.btn_continue.enabled and self.btn_continue.hovered(pos):
                self._resume_session()
            elif self.btn_start.hovered(pos):
                self.load_level(0)  # 从第 1 关开始
                self.state = self.STATE_GAME
            elif self.btn_select.hovered(pos):
                self.state = self.STATE_SELECT
        elif self.state == self.STATE_SELECT:
            for i, btn in enumerate(self.level_buttons):
                if btn.hovered(pos):
                    if i >= levels.TOTAL_LEVELS:
                        self.load_random_level()
                    else:
                        self.load_level(i)
                    self.state = self.STATE_GAME
                    return
            if self.btn_back.hovered(pos):
                self.state = self.STATE_START
        elif self.state == self.STATE_GAME:
            if self.btn_restart.hovered(pos):
                self.restart_level()
                return
            if self.pending_state is not None:
                return  # 正在结算, 其余操作忽略
            if self.btn_undo.enabled and self.btn_undo.hovered(pos):
                self._undo()
                return
            if self.btn_hint.hovered(pos):
                self._show_hint()
                return
            if self.btn_solve.hovered(pos):
                self.auto_solving = not self.auto_solving
                self.auto_timer = 0.2
                return
            cell = self._cell_at(pos)
            if cell is None:
                return
            self.auto_solving = False  # 手动操作打断自动求解
            self.hint_cells = set()
            self._click_cell(*cell)
        elif self.state == self.STATE_WIN:
            if self.btn_next.hovered(pos):
                if self.level_index >= levels.TOTAL_LEVELS:
                    self.load_random_level()  # 无限挑战: 再开一局
                else:
                    self.load_level(self.level_index + 1)
                self.state = self.STATE_GAME
            elif self.btn_menu.hovered(pos):
                self.state = self.STATE_START
        elif self.state == self.STATE_FAIL:
            if self.btn_retry.hovered(pos):
                self.restart_level()
                self.state = self.STATE_GAME
            elif self.btn_menu.hovered(pos):
                self.state = self.STATE_START
        elif self.state == self.STATE_ALL_CLEAR:
            if self.btn_replay.hovered(pos):
                self.load_level(0)
                self.state = self.STATE_GAME
            elif self.btn_menu.hovered(pos):
                self.state = self.STATE_START

    def _undo(self):
        """撤销上一步: 恢复最近一次飞出前的局面, 并立即存档。"""
        if not self.undo_stack:
            return
        self.logic.restore(self.undo_stack.pop())
        self.flying = []
        self.collisions = {}
        self.hint_cells = set()
        self.auto_solving = False
        self.pending_state = None
        self.pending_timer = 0.0
        self._save_progress()

    def _show_hint(self):
        """高亮一个当前可飞出的箭头(持续约 2.5 秒)。"""
        cell = self.logic.find_solvable_cell()
        if cell is None:
            return
        idx = self.logic._path_owner(*cell)
        if idx is not None:
            self.hint_cells = set(self.logic.paths[idx]["cells"])
        else:
            self.hint_cells = {cell}
        self.hint_timer = 2.5

    def _play(self, name):
        """播放音效; 无音频设备时静音跳过。"""
        if self.sounds:
            try:
                self.sounds[name].play()
            except pygame.error:
                pass

    def _click_cell(self, r, c):
        """处理一次棋盘格点击(手动与自动求解共用)。"""
        snap = self.logic.snapshot()
        result, arrow = self.logic.click(r, c)
        if result == logic.RESULT_FLY:
            self.undo_stack.append(snap)
            if len(self.undo_stack) > 100:
                self.undo_stack.pop(0)
            if isinstance(arrow, dict):  # 多格拐弯箭头
                self._spawn_path_flying_arrow(arrow)
            else:
                self._spawn_flying_arrow(r, c, arrow)
            self._play("fly")
            if self.logic.status == logic.STATUS_CLEARED:
                if self.level_index < levels.TOTAL_LEVELS:
                    # 记录星级(剩余失误次数即星级)与解锁进度
                    self.stars[self.level_index] = max(
                        self.stars.get(self.level_index, 0),
                        self.logic.mistakes_left)
                    self.unlocked = min(levels.TOTAL_LEVELS - 1,
                                        max(self.unlocked,
                                            self.level_index + 1))
                if self.level_index >= levels.TOTAL_LEVELS:
                    self._schedule_state(self.STATE_WIN, 0.55)  # 随机关卡
                elif self.level_index + 1 >= levels.TOTAL_LEVELS:
                    self._schedule_state(self.STATE_ALL_CLEAR, 0.55)
                else:
                    self._schedule_state(self.STATE_WIN, 0.55)
            self._save_progress()  # 每次操作后存档, 存档永远是当前关卡
        elif result == logic.RESULT_BLOCKED:
            if isinstance(arrow, dict):
                key = ("path", arrow["cells"][-1])  # 以头部格子作键
                effect = CollisionEffect(arrow["dir"])
            else:
                key = (r, c)
                effect = CollisionEffect(arrow)
            self.collisions[key] = effect
            self.mistake_flash = 0.6
            self._play("blocked")
            if self.logic.status == logic.STATUS_FAILED:
                self._schedule_state(self.STATE_FAIL, 0.7)
            self._save_progress()

    def _schedule_state(self, state, delay):
        """等动画播放一段时间后再切换到结算画面。"""
        self.pending_state = state
        self.pending_timer = delay
        self.auto_solving = False
        if state in (self.STATE_WIN, self.STATE_ALL_CLEAR):
            self.confetti = Confetti()

    def _spawn_flying_arrow(self, r, c, arrow):
        """生成 (r, c) 处单格箭头沿其方向飞出棋盘的动画。"""
        rect = self._cell_rect(r, c)
        start = rect.center
        dr, dc = logic.DIRECTIONS[arrow]
        dist = settings.CELL_SIZE * max(self.logic.rows, self.logic.cols) + 150
        end = (start[0] + dc * dist, start[1] + dr * dist)
        self.flying.append(FlyingArrow(start, end, arrow))

    def _spawn_path_flying_arrow(self, arrow):
        """生成多格拐弯箭头沿自身轨道滑出棋盘的动画。"""
        head = tuple(arrow["cells"][-1])
        color = self.arrow_colors.get(head, settings.ARROW_COLORS[arrow["dir"]])
        self.flying.append(PathFlyingArrow(arrow["cells"], arrow["dir"], color,
                                           self._cell_rect,
                                           self.logic.rows, self.logic.cols))

    # ------------------------------------------------------------ 更新与绘制

    def update(self, dt):
        for f in self.flying:
            f.update(dt)
        self.flying = [f for f in self.flying if f.alive]
        for eff in self.collisions.values():
            eff.update(dt)
        self.collisions = {k: v for k, v in self.collisions.items() if v.alive}
        if self.confetti:
            self.confetti.update(dt)
        if self.mistake_flash > 0:
            self.mistake_flash = max(0.0, self.mistake_flash - dt)
        # 通关计时
        if (self.state == self.STATE_GAME
                and self.logic.status == logic.STATUS_PLAYING
                and self.pending_state is None):
            self.elapsed += dt
        # 提示高亮计时
        if self.hint_timer > 0:
            self.hint_timer = max(0.0, self.hint_timer - dt)
            if self.hint_timer == 0:
                self.hint_cells = set()
        # AI 自动求解
        if self.auto_solving:
            self.auto_timer -= dt
            if self.auto_timer <= 0:
                if (self.logic.status != logic.STATUS_PLAYING
                        or self.pending_state is not None):
                    self.auto_solving = False
                else:
                    cell = self.logic.find_solvable_cell()
                    if cell is None:
                        self.auto_solving = False
                    else:
                        self._click_cell(*cell)
                        self.auto_timer = 0.65
        # 结算切换(带音效)
        if self.pending_state is not None:
            self.pending_timer -= dt
            if self.pending_timer <= 0:
                self.state = self.pending_state
                self.pending_state = None
                if self.state in (self.STATE_WIN, self.STATE_ALL_CLEAR):
                    self._play("win")
                elif self.state == self.STATE_FAIL:
                    self._play("fail")

    def draw(self):
        self.screen.fill(settings.BG_COLOR)
        if self.state == self.STATE_START:
            self._draw_start()
            return
        if self.state == self.STATE_SELECT:
            self._draw_select()
            return
        self._draw_hud()
        self._draw_board()
        if self.state == self.STATE_WIN:
            self._draw_win_overlay()
        elif self.state == self.STATE_FAIL:
            self._draw_fail_overlay()
        elif self.state == self.STATE_ALL_CLEAR:
            self._draw_all_clear_overlay()

    def _draw_start(self):
        """开始界面: 标题、装饰箭头、玩法说明面板、开始按钮。"""
        cx = settings.WINDOW_WIDTH // 2
        # 标题(带阴影)
        draw_text(self.screen, "一箭又一箭", 76, (20, 22, 38),
                  center=(cx + 4, 184), bold=True)
        draw_text(self.screen, "一箭又一箭", 76, settings.ACCENT,
                  center=(cx, 180), bold=True)
        draw_text(self.screen, "点 击 箭 头 解 谜", 28, settings.TEXT_DIM,
                  center=(cx, 250))
        draw_arrow(self.screen, (cx - 150, 314), "→", 46,
                   settings.ARROW_COLORS["→"])
        draw_arrow(self.screen, (cx, 314), "↑", 46,
                   settings.ARROW_COLORS["↑"])
        draw_arrow(self.screen, (cx + 150, 314), "←", 46,
                   settings.ARROW_COLORS["←"])
        # 玩法说明面板
        panel = pygame.Rect(0, 0, 580, 132)
        panel.center = (cx, 422)
        pygame.draw.rect(self.screen, settings.PANEL_COLOR, panel,
                         border_radius=16)
        pygame.draw.rect(self.screen, settings.CELL_LIGHT, panel, width=2,
                         border_radius=16)
        rules = [
            "点击箭头(长箭点身体任意位置), 让它飞出棋盘",
            "头部前方有其他箭头阻挡时无法飞出, 并消耗一次失误机会",
            "清空全部箭头即可过关; 失误耗尽则本关失败",
        ]
        for i, line in enumerate(rules):
            draw_text(self.screen, line, 22, settings.TEXT_COLOR,
                      center=(cx, 388 + i * 34))
        self.btn_continue.enabled = save.load() is not None
        self.btn_continue.draw(self.screen, self.mouse_pos)
        self.btn_start.draw(self.screen, self.mouse_pos)
        self.btn_select.draw(self.screen, self.mouse_pos)
        draw_text(self.screen,
                  f"共 {levels.TOTAL_LEVELS} 关 · 长箭玩法 · 含无限挑战 · "
                  f"每关 {settings.MISTAKES_PER_LEVEL} 次失误机会",
                  20, settings.TEXT_DIM, center=(cx, 650))
        draw_text(self.screen, "AIGC 辅助开发作业 · Claude Code · Pygame",
                  18, settings.TEXT_DIM, center=(cx, 686))

    def _draw_hud(self):
        """顶部信息栏, 分为三个不重叠的区域:
        左区(关卡名) / 中区(剩余箭头·用时·失误机会) / 右区(操作按钮)。"""
        hud = pygame.Rect(0, 0, settings.WINDOW_WIDTH, settings.HUD_HEIGHT)
        pygame.draw.rect(self.screen, settings.HUD_COLOR, hud)
        pygame.draw.line(self.screen, settings.ACCENT,
                         (0, settings.HUD_HEIGHT),
                         (settings.WINDOW_WIDTH, settings.HUD_HEIGHT), 3)

        # 左区: 标题 + 关卡名(去掉"进阶 · "前缀, 控制宽度)
        draw_text(self.screen, "一箭又一箭", 20, settings.ACCENT,
                  topleft=(24, 14), bold=True)
        if self.level_index >= levels.TOTAL_LEVELS:
            draw_text(self.screen, "无限挑战 · 随机生成", 24,
                      settings.TEXT_COLOR, topleft=(24, 48), bold=True)
        else:
            level = levels.LEVELS[self.level_index]
            name = level["name"].replace("进阶 · ", "")
            draw_text(self.screen,
                      f"第 {self.level_index + 1}/{levels.TOTAL_LEVELS} 关 · {name}",
                      24, settings.TEXT_COLOR, topleft=(24, 48), bold=True)

        # 中区: 竖排三项数据
        draw_text(self.screen, f"剩余箭头  {self.logic.arrows_left}", 22,
                  settings.TEXT_COLOR, center=(410, 20), bold=True)
        draw_text(self.screen, f"用时  {self._fmt_time()}", 18,
                  settings.TEXT_DIM, center=(410, 56))

        # 失误机会: 剩余用实心圆点, 已消耗用空心圆点
        draw_text(self.screen, "失误机会", 16, settings.TEXT_DIM,
                  center=(325, 92))
        n = self.logic.total_mistakes
        left = self.logic.mistakes_left
        start_x = 405 - (n - 1) * 14
        for i in range(n):
            cx = start_x + i * 28
            if i < left:
                pygame.draw.circle(self.screen, settings.MISTAKE_COLOR,
                                   (cx, 92), 10)
            elif self.mistake_flash > 0 and i == left:
                # 刚消耗的失误: 红色圆点闪烁提示
                r2 = 10 + 3 * math.sin(self.mistake_flash * 30)
                pygame.draw.circle(self.screen, settings.DANGER,
                                   (cx, 92), int(r2))
            else:
                pygame.draw.circle(self.screen, settings.TEXT_DIM,
                                   (cx, 92), 10, width=2)

        # 右区: 重新开始(上排) + 撤销/提示/自动求解(下排)
        self.btn_restart.draw(self.screen, self.mouse_pos)
        self.btn_undo.enabled = bool(self.undo_stack)
        self.btn_undo.draw(self.screen, self.mouse_pos)
        self.btn_hint.draw(self.screen, self.mouse_pos)
        self.btn_solve.draw(self.screen, self.mouse_pos)

    def _fmt_time(self):
        """把秒数格式化为 MM:SS。"""
        total = int(self.elapsed)
        return f"{total // 60:02d}:{total % 60:02d}"

    def _draw_board(self):
        """棋盘格子 + 箭头(含碰撞效果) + 飞出动画 + 碰撞飘字 + 底部提示。"""
        rows, cols = self.logic.rows, self.logic.cols
        hover_cell = (self._cell_at(self.mouse_pos)
                      if self.state == self.STATE_GAME
                      and self.pending_state is None
                      and self.logic.status == logic.STATUS_PLAYING
                      else None)
        hover_path = (self.logic._path_owner(*hover_cell)
                      if hover_cell is not None else None)

        # 格子
        for r in range(rows):
            for c in range(cols):
                rect = self._cell_rect(r, c)
                color = (settings.CELL_LIGHT if (r + c) % 2 == 0
                         else settings.CELL_DARK)
                in_hover = ((r, c) == hover_cell
                            or (hover_path is not None
                                and (r, c) in self.logic.paths[hover_path]["cells"]))
                if in_hover and self.logic.occupied(r, c):
                    color = settings.CELL_HOVER
                pygame.draw.rect(self.screen, color, rect, border_radius=14)
                # 提示高亮: 脉冲描边
                if (r, c) in self.hint_cells and self.hint_timer > 0:
                    pulse = 3 + 2 * math.sin(self.hint_timer * 12)
                    pygame.draw.rect(self.screen, settings.ACCENT_LIGHT,
                                     rect, width=int(pulse), border_radius=14)

        # 箭头(带碰撞效果: 抖动偏移 + 由红变回橙色 + 格子红色闪光)
        for r in range(rows):
            for c in range(cols):
                cell = self.logic.grid[r][c]
                if cell == ".":
                    continue
                rect = self._cell_rect(r, c)
                eff = self.collisions.get((r, c))
                if eff:
                    p = eff.progress()
                    color = lerp_color(settings.DANGER,
                                       settings.ARROW_COLORS[cell], p)
                    ox2, oy2 = eff.shake_offset()
                    center = (rect.centerx + ox2, rect.centery + oy2)
                    flash = pygame.Surface(rect.size, pygame.SRCALPHA)
                    flash.fill((*settings.DANGER, int(90 * (1 - p))))
                    self.screen.blit(flash, rect)
                else:
                    color = settings.ARROW_COLORS[cell]
                    center = rect.center
                draw_arrow(self.screen, center, cell,
                           settings.CELL_SIZE * 0.62, color)

        # 多格拐弯箭头
        self._draw_path_arrows()

        # 飞出动画
        for f in self.flying:
            f.draw(self.screen)

        # 碰撞飘字
        for key, eff in self.collisions.items():
            if isinstance(key, tuple) and key and isinstance(key[0], str):
                cell_rect = self._cell_rect(*key[1])  # 多格箭头: 画在头部格子
            else:
                cell_rect = self._cell_rect(*key)
            eff.draw_text_hint(self.screen, cell_rect)

        # 通关撒花(结算画面背景)
        if self.confetti:
            self.confetti.draw(self.screen)

        # 底部提示
        if self.logic.status == logic.STATUS_PLAYING:
            draw_text(self.screen,
                      "提示: 点击前进方向没有其他箭头的箭头使其飞出 · ESC 返回主菜单",
                      20, settings.TEXT_DIM,
                      center=(settings.WINDOW_WIDTH // 2,
                              settings.WINDOW_HEIGHT - 16))

    def _draw_path_arrows(self):
        """绘制多格拐弯箭头: 与普通箭头等粗的箭身线 + 同尺寸三角箭头。"""
        for p in self.logic.paths:
            cells = p["cells"]
            head = cells[-1]
            pts = [self._cell_rect(r, c).center for r, c in cells]
            eff = self.collisions.get(("path", head))
            offset = (0, 0)
            color = self.arrow_colors.get(head, settings.ARROW_COLORS[p["dir"]])
            if eff:
                pr = eff.progress()
                color = lerp_color(settings.DANGER, color, pr)
                offset = eff.shake_offset()
                head_rect = self._cell_rect(*head)
                flash = pygame.Surface(head_rect.size, pygame.SRCALPHA)
                flash.fill((*settings.DANGER, int(90 * (1 - pr))))
                self.screen.blit(flash, head_rect)
            pts = [(x + offset[0], y + offset[1]) for x, y in pts]
            # 箭身宽度与普通箭头的箭杆一致(约 CELL*0.14)
            width = int(settings.CELL_SIZE * 0.14)
            outline = tuple(max(0, c2 - 60) for c2 in color)
            pygame.draw.lines(self.screen, outline, False, pts, width + 4)
            pygame.draw.lines(self.screen, color, False, pts, width)
            # 拐弯处补画实心圆, 保证箭尾在转弯处的连贯
            for x, y in pts[1:-1]:
                pygame.draw.circle(self.screen, outline,
                                   (int(x), int(y)), width // 2 + 2)
            for x, y in pts[1:-1]:
                pygame.draw.circle(self.screen, color,
                                   (int(x), int(y)), width // 2)
            draw_arrow_head(self.screen, pts[-1], p["dir"],
                            settings.CELL_SIZE * 0.62,
                            tuple(min(255, x + 55) for x in color))

    def _draw_select(self):
        """关卡选择界面: 1~8 关 + 无限挑战, 显示历史最佳星级。"""
        cx = settings.WINDOW_WIDTH // 2
        draw_text(self.screen, "选 择 关 卡", 52, settings.ACCENT,
                  center=(cx, 100), bold=True)
        draw_text(self.screen, "点击进入关卡, 星星为历史最佳评价", 20,
                  settings.TEXT_DIM, center=(cx, 150))
        for i, btn in enumerate(self.level_buttons):
            if i >= levels.TOTAL_LEVELS:
                btn.text = "∞\n无限挑战\n随机生成"
            else:
                name = levels.LEVELS[i]["name"].replace("进阶 · ", "")
                s = self.stars.get(i, 0)
                stars_text = ("★" * s + "☆" * (3 - s)) if s > 0 else "未挑战"
                btn.text = f"{i + 1}\n{name}\n{stars_text}"
            btn.draw(self.screen, self.mouse_pos)
        self.btn_back.draw(self.screen, self.mouse_pos)

    # ------------------------------------------------------------ 结算画面

    def _draw_overlay_panel(self, title, color):
        """绘制半透明遮罩 + 中央结算面板, 返回面板矩形。"""
        dim = pygame.Surface((settings.WINDOW_WIDTH, settings.WINDOW_HEIGHT),
                             pygame.SRCALPHA)
        dim.fill(settings.OVERLAY)
        self.screen.blit(dim, (0, 0))
        panel = pygame.Rect(0, 0, 520, 300)
        panel.center = (settings.WINDOW_WIDTH // 2,
                        settings.WINDOW_HEIGHT // 2)
        pygame.draw.rect(self.screen, settings.PANEL_COLOR, panel,
                         border_radius=20)
        pygame.draw.rect(self.screen, settings.ACCENT, panel, width=3,
                         border_radius=20)
        draw_text(self.screen, title, 44, color,
                  center=(panel.centerx, panel.top + 66), bold=True)
        return panel

    def _draw_win_overlay(self):
        """单关通关结算界面(含星级与用时)。"""
        if self.level_index >= levels.TOTAL_LEVELS:
            title = "无限挑战通过!"
            self.btn_next.text = "再来一关"
        else:
            title = f"第 {self.level_index + 1} 关通过!"
            self.btn_next.text = "下一关"
        self._draw_overlay_panel(title, settings.SUCCESS)
        stars = self.logic.mistakes_left  # 通关后剩余失误 1~3, 即星级
        draw_text(self.screen, "★" * stars + "☆" * (3 - stars), 40,
                  settings.ACCENT,
                  center=(settings.WINDOW_WIDTH // 2, 352), bold=True)
        draw_text(self.screen,
                  f"用时 {self._fmt_time()} · 剩余失误 {stars}",
                  22, settings.TEXT_DIM,
                  center=(settings.WINDOW_WIDTH // 2, 404))
        self.btn_next.draw(self.screen, self.mouse_pos)
        self.btn_menu.draw(self.screen, self.mouse_pos)

    def _draw_fail_overlay(self):
        """失败结算界面。"""
        self._draw_overlay_panel("失误次数耗尽", settings.DANGER)
        draw_text(self.screen,
                  f"第 {self.level_index + 1} 关挑战失败, 再试一次吧!",
                  24, settings.TEXT_DIM,
                  center=(settings.WINDOW_WIDTH // 2, 410))
        self.btn_retry.draw(self.screen, self.mouse_pos)
        self.btn_menu.draw(self.screen, self.mouse_pos)

    def _draw_all_clear_overlay(self):
        """全部关卡通关结算界面。"""
        self._draw_overlay_panel("恭喜通关!", settings.SUCCESS)
        draw_text(self.screen,
                  f"你已通关全部 {levels.TOTAL_LEVELS} 个关卡",
                  24, settings.TEXT_DIM,
                  center=(settings.WINDOW_WIDTH // 2, 410))
        self.btn_replay.draw(self.screen, self.mouse_pos)
        self.btn_menu.draw(self.screen, self.mouse_pos)

    # ------------------------------------------------------------ 主循环

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(settings.FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif (event.type == pygame.MOUSEBUTTONDOWN
                      and event.button == 1):
                    self.on_click(event.pos)
                elif (event.type == pygame.KEYDOWN
                      and event.key == pygame.K_ESCAPE
                      and self.state != self.STATE_START):
                    self.state = self.STATE_START
            self.mouse_pos = pygame.mouse.get_pos()
            self.update(dt)
            self.draw()
            pygame.display.flip()
        # 退出时存档: 仅在已有存档(即确实玩过)时写, 避免打开即关覆盖进度
        if self._saved_once:
            self._save_progress()
        pygame.quit()
