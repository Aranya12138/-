"""合成音效: 用标准库 struct/math 直接生成音频字节并交给 pygame 播放,
无需任何外部音频素材。无音频设备时静音降级, 不影响游戏运行。"""

import math
import random
import struct

import pygame

RATE = 22050  # 采样率


def _sweep(f0, f1, duration, volume=0.45):
    """频率从 f0 滑到 f1 的正弦扫频(箭头飞出时的"嗖"声)。"""
    n = int(RATE * duration)
    phase = 0.0
    buf = bytearray()
    for i in range(n):
        t = i / n
        freq = f0 + (f1 - f0) * t
        phase += 2 * math.pi * freq / RATE
        env = 1 - t
        buf += struct.pack("<h", int(math.sin(phase) * env * volume * 32767))
    return bytes(buf)


def _tone(freq, duration, volume=0.5, decay=True):
    """固定频率音(结算音用)。"""
    n = int(RATE * duration)
    buf = bytearray()
    for i in range(n):
        t = i / RATE
        env = (1 - i / n) if decay else 1.0
        buf += struct.pack("<h", int(math.sin(2 * math.pi * freq * t)
                                     * env * volume * 32767))
    return bytes(buf)


def _thud(freq, duration, volume=0.6):
    """低频闷响 + 噪声(碰撞反馈)。"""
    n = int(RATE * duration)
    buf = bytearray()
    for i in range(n):
        env = 1 - i / n
        v = (math.sin(2 * math.pi * freq * i / RATE) * 0.7
             + random.uniform(-0.3, 0.3)) * env * volume
        buf += struct.pack("<h", int(v * 32767))
    return bytes(buf)


def build_sounds():
    """构建音效字典 {'fly', 'blocked', 'win', 'fail'}; 无音频设备返回 None。"""
    try:
        pygame.mixer.init(frequency=RATE, size=-16, channels=1)
    except pygame.error:
        return None
    try:
        win = (_tone(523, 0.12, decay=False)   # C5
               + _tone(659, 0.12, decay=False)  # E5
               + _tone(784, 0.25))              # G5
        fail = _tone(392, 0.15) + _tone(262, 0.35)
        return {
            "fly": pygame.mixer.Sound(buffer=_sweep(400, 1400, 0.18)),
            "blocked": pygame.mixer.Sound(buffer=_thud(110, 0.16)),
            "win": pygame.mixer.Sound(buffer=win),
            "fail": pygame.mixer.Sound(buffer=fail),
        }
    except pygame.error:
        return None
