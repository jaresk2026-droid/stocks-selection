"""全局配置：路径与基础参数。"""
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = ROOT / "data"
MINUTE_DIR = DATA_DIR / "minute"      # 分钟线 Parquet 分区
OUTPUT_DIR = ROOT / "output"          # 选股结果导出
STRATEGY_DIR = ROOT / "strategies"    # 策略配置 yaml

# SQLite 数据库文件（日/周/月线 + 基础信息 + 板块）
DB_PATH = DATA_DIR / "stocks.db"

# 分钟级周期（优先 60/15/5 分钟）
MINUTE_PERIODS = ["60", "15", "5"]

# 复权方式：qfq=前复权（指标计算用），hfq=后复权，""=不复权
ADJUST = "qfq"

# 全量初始化时的起始日期
HISTORY_START = "20200101"

# akshare 调用之间的间隔（秒），避免触发限频
REQUEST_SLEEP = 0.3


def ensure_dirs() -> None:
    """确保所有数据/输出目录存在。"""
    for d in (DATA_DIR, MINUTE_DIR, OUTPUT_DIR, STRATEGY_DIR):
        d.mkdir(parents=True, exist_ok=True)
