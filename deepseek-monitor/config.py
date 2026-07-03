"""
DeepSeek Token 用量监控 — 配置常量
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

# ── 模型定价 (每 1M tokens, USD) ─────────────────────────────────
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

# ── UI 颜色 ───────────────────────────────────────────────────────
TRANSPARENT = "#010101"        # 透明色键

BG_MAIN = "#1a1a2e"            # 主背景
BG_GRADIENT_TOP = "#1e1e38"    # 顶部渐变
BG_CARD = "#252540"            # 卡片
BG_INPUT = "#2e2e48"           # 输入框
BG_HANDLE = "#14142a"          # 拖拽条
BG_STRIP = "#2a2a4a"           # 统计行背景色块
TEXT_PRIMARY = "#e8e8f8"       # 主文字
TEXT_SECONDARY = "#9d9dc8"     # 次要
TEXT_ACCENT = "#7ec8ff"        # 数值
TEXT_TITLE = "#f0f0ff"         # 标题
GREEN = "#4fe381"              # 正常
YELLOW = "#f5c842"             # 警告
RED = "#ff5e7a"                # 超支
ORANGE = "#ff8c42"             # 中间色
BORDER = "#3d3d5c"             # 边框
BORDER_OUTER = "#4a4a78"       # 外边框 (发光)
CHART_BAR = "#5a7ade"          # 柱色
CHART_BAR_TODAY = "#a78bfa"    # 今日柱色
SHADOW = "#0d0d1a"             # 阴影

# ── 预算阈值 ──────────────────────────────────────────────────────
BUDGET_GREEN_PCT = 0.70
BUDGET_YELLOW_PCT = 1.00

# ── 窗口尺寸 ──────────────────────────────────────────────────────
COMPACT_WIDTH = 320
COMPACT_HEIGHT = 370
EXPANDED_WIDTH = 370
EXPANDED_HEIGHT = 540
OVERLAY_MARGIN = 16
REFRESH_MS = 2000
CORNER_RADIUS = 20
PAD_X = 18

# ── 字体 (放大醒目) ───────────────────────────────────────────────
FONT_FAMILY = "Microsoft YaHei UI"
FONT_SIZE_XS = 9       # 柱状图标签、底部
FONT_SIZE_SM = 10      # 副标签
FONT_SIZE_MD = 12      # 正文数值
FONT_SIZE_LG = 15      # 标题
FONT_SIZE_XL = 20      # 主数值 (今日/本月/总计)
FONT_SIZE_XXL = 28     # 超大数值头部
