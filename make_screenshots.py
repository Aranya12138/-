"""生成 README 用的游戏截图(无需打开窗口, 使用虚拟显示驱动)。

运行方法(项目根目录下):
    py tools/make_screenshots.py
输出: screenshots/ 目录下的 PNG 文件
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

import game  # noqa: E402
import logic  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "screenshots")


def shot(app, name):
    app.draw()
    path = os.path.join(OUT_DIR, f"{name}.png")
    pygame.image.save(app.screen, path)
    print(f"saved: {path}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    app = game.ArrowGame()

    # 开始界面
    app.state = app.STATE_START
    shot(app, "start")

    # 关卡选择界面(带历史星级)
    app.state = app.STATE_SELECT
    app.stars[0] = 3
    app.stars[2] = 2
    shot(app, "select")

    # 游戏界面(第 3 关, 棋盘更大更丰富)
    app.load_level(2)
    app.state = app.STATE_GAME
    shot(app, "game")

    # 碰撞反馈: 点击第 3 关 (0,0) 的长箭(被 (0,4) 的竖长箭阻挡), 动画推进到中间时刻
    app.on_click(app._cell_rect(0, 0).center)
    assert app.collisions, "碰撞效果未创建"
    eff = list(app.collisions.values())[0]
    eff.time = eff.duration * 0.35
    app.mistake_flash = 0.3
    shot(app, "collision")

    # 进阶关卡(第 6 关): 横跨多格、带拐角的长箭
    app.load_level(5)
    app.state = app.STATE_GAME
    shot(app, "advanced")

    # 通关结算界面(带撒花)
    app.state = app.STATE_WIN
    app.confetti = game.Confetti()
    for _ in range(120):
        app.confetti.update(1 / 60)
    shot(app, "win")

    # 失败结算界面
    app.state = app.STATE_FAIL
    shot(app, "fail")

    # 全部通关结算界面
    app.state = app.STATE_ALL_CLEAR
    shot(app, "all_clear")

    pygame.quit()
    print("所有截图生成完毕")


if __name__ == "__main__":
    main()
