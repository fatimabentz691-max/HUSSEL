"""
DeepSeek Token 用量监控 — 配置常量
Apple 风格 · 全粗体 · 动态过渡
"""

import os

# ── 路径 ──────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "usage_data.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

# ── 代理 ──────────────────────────────────────────────────────────
DEFAULT_PROXY_PORT = 7890
PROXY_HOST = "127.0.0.1"
DEEPSEEK_API_BASE = "https://api.deepseek.com"

# ── 模型定价 ─────────────────────────────────────────────────────
MODELS = {
    "deepseek-chat": {
        "label": "DeepSeek V3/Flash",
        "input": 0.14, "input_cache_hit": 0.014, "output": 1.10,
    },
    "deepseek-reasoner": {
        "label": "DeepSeek R1/Pro",
        "input": 0.55, "input_cache_hit": 0.055, "output": 2.19,
    },
}
DEFAULT_MODEL = "deepseek-chat"

# ── 预算 ──────────────────────────────────────────────────────────
DEFAULT_DAILY_BUDGET = 1.00
DEFAULT_MONTHLY_BUDGET = 30.00

# ── 配色 · macOS Dark ────────────────────────────────────────────
BG_BASE        = "#0d0d0f"
BG_MAIN        = "#161618"
BG_CARD        = "#1e1e22"
BG_INPUT       = "#26262b"
BG_HANDLE      = "#0a0a0c"
BG_HOVER       = "#2a2a30"

TEXT_PRIMARY   = "#f5f5f7"
TEXT_SECONDARY = "#98989d"
TEXT_TITLE     = "#ffffff"
TEXT_MUTED     = "#6e6e73"

ACCENT       = "#0a84ff"
ACCENT_SOFT  = "#409cff"

GREEN        = "#30d158"
ORANGE       = "#ff9f0a"
RED          = "#ff453a"

CHART_BAR       = "#2c2c30"
CHART_BAR_TODAY = "#0a84ff"
BORDER          = "#2c2c30"

# ── 预算阈值 ──────────────────────────────────────────────────────
BUDGET_GREEN_PCT  = 0.70
BUDGET_YELLOW_PCT = 1.00

# ── 窗口尺寸 ─────────────────────────────────────────────────────
COMPACT_WIDTH  = 340
COMPACT_HEIGHT = 500
OVERLAY_MARGIN = 20
REFRESH_MS     = 2000
CORNER_RADIUS  = 18
PAD_X          = 24

# ── 字体 · 全粗体 · 苹果风格 ─────────────────────────────────────
FONT_FAMILY  = "Microsoft YaHei UI"

# 字号统一 (全部 bold)
S_BASE   = 11   # 正文标签 / 图表日期 / 底部状态
S_XL     = 38   # 今日 Token 大数字
S_LG     = 17   # 今日费用
S_MD     = 14   # 本月/累计 Token 数
S_SM     = 12   # 本月/累计 费用
S_XS     = 10   # 图表上方数值

# ── 动画 ──────────────────────────────────────────────────────────
ANIM_STEPS    = 12    # 数字滚动的帧数
ANIM_INTERVAL = 30    # 每帧间隔 (ms)
ANIM_EASING   = "ease_out"  # 缓动类型
