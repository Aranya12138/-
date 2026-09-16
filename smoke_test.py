"""自动化"试玩"脚本: 模拟真实点击, 验证游戏整体流程。

不需要打开窗口(使用虚拟显示驱动), 覆盖:
  1. 8 个关卡全部可以按"先点可飞出的箭头"的顺序通关
  2. 界面层通关流程: 点击 -> 飞出动画 -> 通关结算 -> 下一关
  3. 界面层失败流程: 失误耗尽 -> 失败结算 -> 重新开始

运行方法(项目根目录下):
    py tools/smoke_test.py
退出码 0 表示全部通过。
"""

import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game  # noqa: E402
import levels  # noqa: E402
import logic  # noqa: E402
import save  # noqa: E402

MAX_STEPS = 500


def play_level_through_logic(index):
    """逻辑层: 反复点击当前可飞出的箭头, 把第 index 关通关。"""
    g = logic.GameLogic(index, mistakes=3)
    clicks = 0
    while g.status == logic.STATUS_PLAYING and clicks < MAX_STEPS:
        clicked = False
        # 单格箭头
        for r in range(g.rows):
            for c in range(g.cols):
                if g.grid[r][c] != "." and not g.is_blocked(r, c):
                    result, _ = g.click(r, c)
                    assert result == logic.RESULT_FLY, \
                        f"第 {index + 1} 关点击 ({r}, {c}) 失败"
                    clicks += 1
                    clicked = True
                    break
            if clicked:
                break
        # 多格拐弯箭头: 点击其头部格子
        if not clicked:
            for i in range(len(g.paths)):
                if not g.path_blocked(i):
                    result, _ = g.click(*g.paths[i]["cells"][-1])
                    assert result == logic.RESULT_FLY, \
                        f"第 {index + 1} 关长箭 {i} 点击失败"
                    clicks += 1
                    clicked = True
                    break
        if not clicked:
            break
    assert g.status == logic.STATUS_CLEARED, f"第 {index + 1} 关无法通关"
    return clicks


def find_free_cell(g):
    """找一个当前可飞出箭头的身体格, 返回 (r, c) 或 None。"""
    for r in range(g.rows):
        for c in range(g.cols):
            if g.grid[r][c] != "." and not g.is_blocked(r, c):
                return r, c
    for i in range(len(g.paths)):
        if not g.path_blocked(i):
            return g.paths[i]["cells"][0]
    return None


def test_ui_clear_flow():
    """界面层: 第 1 关自动通关 -> 出现通关结算 -> 点"下一关"进入第 2 关。"""
    app = game.ArrowGame()
    app.state = app.STATE_GAME
    steps = 0
    while app.state == app.STATE_GAME and steps < MAX_STEPS:
        cell = find_free_cell(app.logic)
        assert cell is not None, f"第 {app.level_index + 1} 关找不到可飞出的箭头"
        app.on_click(app._cell_rect(*cell).center)
        for _ in range(40):  # 推进动画与结算等待
            app.update(1 / 60)
        steps += 1
    assert app.state == app.STATE_WIN, f"期望通关界面, 实际: {app.state}"
    app.on_click(app.btn_next.rect.center)
    assert app.state == app.STATE_GAME and app.level_index == 1
    print("界面层通关流程: 通关结算 -> 下一关 OK")


def test_ui_fail_flow():
    """界面层: 失误耗尽 -> 失败结算 -> 点"重新开始"恢复本关。"""
    app = game.ArrowGame()
    app.state = app.STATE_GAME
    for _ in range(3):  # 第 1 关 (2,3) 的长箭被挡住, 连点 3 次耗尽失误
        app.on_click(app._cell_rect(2, 3).center)
        app.update(1.0)
    assert app.state == app.STATE_FAIL, f"期望失败界面, 实际: {app.state}"
    app.on_click(app.btn_retry.rect.center)
    assert app.state == app.STATE_GAME
    assert app.logic.mistakes_left == 3 and app.logic.arrows_left == 4
    print("界面层失败流程: 失败结算 -> 重新开始 OK")


def test_ui_auto_solve():
    """界面层: "自动求解"一键演示通关第 1 关。"""
    app = game.ArrowGame()
    app.state = app.STATE_GAME
    app.auto_solving = True
    app.auto_timer = 0.05
    steps = 0
    while app.state == app.STATE_GAME and steps < MAX_STEPS:
        app.update(1 / 60)
        steps += 1
    assert app.state == app.STATE_WIN, f"期望通关界面, 实际: {app.state}"
    print("界面层自动求解: 一键通关 OK")


def test_random_level_play():
    """界面层: 随机生成的"无限挑战"关卡可以通关。"""
    app = game.ArrowGame()
    app.load_random_level()
    app.state = app.STATE_GAME
    steps = 0
    while app.state == app.STATE_GAME and steps < MAX_STEPS:
        cell = find_free_cell(app.logic)
        assert cell is not None, "随机关卡死锁!"
        app.on_click(app._cell_rect(*cell).center)
        for _ in range(40):
            app.update(1 / 60)
        steps += 1
    assert app.state == app.STATE_WIN, f"期望通关界面, 实际: {app.state}"
    print("界面层无限挑战: 随机关卡通关 OK")


def test_save_and_resume():
    """界面层: 通关自动存档; 切关后存档立即跟随当前关卡; 重建应用可恢复。"""
    app = game.ArrowGame()
    app.state = app.STATE_GAME
    app.auto_solving = True
    app.auto_timer = 0.05
    steps = 0
    while app.state == app.STATE_GAME and steps < MAX_STEPS:
        app.update(1 / 60)
        steps += 1
    assert app.state == app.STATE_WIN
    data = save.load()
    assert data["unlocked"] == 1 and data["stars"]["0"] == 3

    # 点"下一关"后, 存档立即变为当前关卡(第 2 关, 进行中)
    app.on_click(app.btn_next.rect.center)
    assert app.state == app.STATE_GAME and app.level_index == 1
    data = save.load()
    assert data["session"]["level"] == 1
    assert data["session"]["snap"]["status"] == "playing"

    # 模拟重启: 进度与星级自动恢复, 继续游戏回到第 2 关开局
    app2 = game.ArrowGame()
    assert app2.unlocked == 1 and app2.stars[0] == 3
    app2._resume_session()
    assert app2.state == app2.STATE_GAME
    assert app2.logic.status == logic.STATUS_PLAYING
    assert app2.logic.arrows_left == 6
    # 回归: 恢复后的长箭格子须为元组(JSON 会变成列表), 碰撞键与绘制不崩溃
    app2.on_click(app2._cell_rect(0, 0).center)  # 第 2 关被阻挡的长箭
    app2.draw()
    print("界面层存档: 进度/星级持久化 + 存档跟随当前关卡 OK")


def test_render_all_screens():
    """每个画面都能正常绘制(不抛异常)。"""
    app = game.ArrowGame()
    app.draw()  # 开始界面
    app.state = app.STATE_SELECT
    app.draw()  # 关卡选择界面
    for i in range(levels.TOTAL_LEVELS):
        app.load_level(i)
        app.state = app.STATE_GAME
        app.draw()
        assert len(set(app.arrow_colors.values())) >= 3, \
            f"第 {i + 1} 关箭头颜色少于 3 种"
    app.load_random_level()
    app.state = app.STATE_GAME
    app.draw()
    app.confetti = game.Confetti()
    for st in (app.STATE_WIN, app.STATE_FAIL, app.STATE_ALL_CLEAR):
        app.state = st
        app.draw()
    print("全部画面渲染自检 OK")


def main():
    # 全程使用临时存档路径, 不污染真实存档
    tmp = os.path.join(tempfile.gettempdir(), "arrow_smoke_save.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    save.save_path = lambda: tmp

    print("== 1. 逻辑层: 逐关自动通关 ==")
    for i in range(levels.TOTAL_LEVELS):
        clicks = play_level_through_logic(i)
        print(f"第 {i + 1} 关: 共点击 {clicks} 次, 通关 OK")

    print("== 2. 界面层流程 ==")
    test_ui_clear_flow()
    test_ui_fail_flow()
    test_ui_auto_solve()
    test_random_level_play()
    test_save_and_resume()

    print("== 3. 渲染自检 ==")
    test_render_all_screens()

    if os.path.exists(tmp):
        os.remove(tmp)
    print("smoke test 全部通过")


if __name__ == "__main__":
    main()
