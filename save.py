"""游戏进度存档: 读写本地 JSON 文件, 无任何外部依赖。

存档内容:
  unlocked  已解锁的最大关卡下标
  stars     各固定关卡的历史最高星级 {"0": 3, "2": 1}
  session   当前对局(关卡/随机关卡数据/局面快照/用时/撤销栈)
"""

import json
import os
import sys


def save_path():
    """存档文件路径: 开发环境在项目目录, 打包后在 exe 同目录。"""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "save.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "save.json")


def load_from(path):
    """从指定路径读取存档, 文件缺失/损坏时返回 None。"""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_to(path, data):
    """把数据写入指定路径, 成功返回 True。"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def load():
    return load_from(save_path())


def save(data):
    return save_to(save_path(), data)
