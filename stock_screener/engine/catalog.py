"""条件目录：描述每个可用条件的元信息（类别、参数、构建函数）。

界面（Streamlit）按这个目录自动渲染勾选框与参数控件，无需为每个条件写界面代码；
也是后续「策略 YAML 配置」的基础。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from stock_screener.engine import conditions as C
from stock_screener.engine.conditions import Condition


@dataclass
class ParamSpec:
    key: str                  # 参数名（传给 builder 的关键字）
    label: str                # 界面显示名
    default: float
    min: float
    max: float
    step: float = 1.0
    is_int: bool = False


@dataclass
class ConditionSpec:
    key: str                          # 唯一标识
    label: str                        # 界面显示名
    category: str                     # "技术面" / "基本面"
    builder: Callable[..., Condition] # (**params) -> Condition
    params: list[ParamSpec] = field(default_factory=list)
    help: str = ""

    def build(self, values: dict) -> Condition:
        kwargs = {p.key: (int(values[p.key]) if p.is_int else values[p.key])
                  for p in self.params if p.key in values}
        return self.builder(**kwargs)


CATALOG: list[ConditionSpec] = [
    # ---------------- 技术面 ----------------
    ConditionSpec("macd_golden_cross", "MACD 金叉", "技术面",
                  lambda **k: C.macd_golden_cross(), help="DIF 上穿 DEA"),
    ConditionSpec("macd_above_zero", "MACD 零轴上方", "技术面",
                  lambda **k: C.macd_above_zero(), help="DIF > 0"),
    ConditionSpec("rsi_below", "RSI 低于阈值", "技术面",
                  lambda threshold=30, **k: C.rsi_below(threshold),
                  [ParamSpec("threshold", "RSI <", 30, 0, 100, 1)]),
    ConditionSpec("rsi_between", "RSI 区间", "技术面",
                  lambda low=30, high=70, **k: C.rsi_between(low, high),
                  [ParamSpec("low", "下限", 30, 0, 100, 1),
                   ParamSpec("high", "上限", 70, 0, 100, 1)]),
    ConditionSpec("kdj_golden_cross", "KDJ 金叉", "技术面",
                  lambda **k: C.kdj_golden_cross(), help="K 上穿 D"),
    ConditionSpec("ma_bullish", "均线多头排列", "技术面",
                  lambda **k: C.ma_bullish(), help="MA5 > MA10 > MA20"),
    ConditionSpec("price_above_ma", "价格站上均线", "技术面",
                  lambda window=20, **k: C.price_above_ma(window),
                  [ParamSpec("window", "均线周期", 20, 5, 250, 5, is_int=True)]),
    ConditionSpec("new_high", "创 N 日新高", "技术面",
                  lambda window=60, **k: C.new_high(window),
                  [ParamSpec("window", "回看天数", 60, 5, 250, 5, is_int=True)]),
    ConditionSpec("volume_ratio_above", "量比大于", "技术面",
                  lambda threshold=1.5, **k: C.volume_ratio_above(threshold),
                  [ParamSpec("threshold", "量比 >", 1.5, 0.5, 10, 0.1)]),
    ConditionSpec("volume_price_up", "量价齐升", "技术面",
                  lambda **k: C.volume_price_up(), help="较昨日价涨且量增"),

    # ---------------- 基本面 ----------------
    ConditionSpec("pe_below", "市盈率低于", "基本面",
                  lambda threshold=30, **k: C.pe_below(threshold),
                  [ParamSpec("threshold", "PE <", 30, 1, 300, 1)],
                  help="默认只看正 PE（排除亏损）"),
    ConditionSpec("pe_between", "市盈率区间", "基本面",
                  lambda low=0, high=30, **k: C.pe_between(low, high),
                  [ParamSpec("low", "下限", 0, -100, 300, 1),
                   ParamSpec("high", "上限", 30, 1, 300, 1)]),
    ConditionSpec("pb_below", "市净率低于", "基本面",
                  lambda threshold=3, **k: C.pb_below(threshold),
                  [ParamSpec("threshold", "PB <", 3, 0.1, 30, 0.1)]),
    ConditionSpec("market_cap_between", "总市值区间(亿)", "基本面",
                  lambda low_yi=0, high_yi=10000, **k: C.market_cap_between(low_yi, high_yi),
                  [ParamSpec("low_yi", "下限(亿)", 50, 0, 100000, 10),
                   ParamSpec("high_yi", "上限(亿)", 1000, 0, 100000, 10)]),
    ConditionSpec("roe_above", "ROE 高于", "基本面",
                  lambda threshold=10, **k: C.roe_above(threshold),
                  [ParamSpec("threshold", "ROE(%) >", 10, -50, 100, 1)]),
    ConditionSpec("eps_above", "每股收益高于", "基本面",
                  lambda threshold=0, **k: C.eps_above(threshold),
                  [ParamSpec("threshold", "EPS >", 0, -10, 20, 0.1)]),
    ConditionSpec("gross_margin_above", "毛利率高于", "基本面",
                  lambda threshold=30, **k: C.gross_margin_above(threshold),
                  [ParamSpec("threshold", "毛利率(%) >", 30, 0, 100, 1)]),
    ConditionSpec("revenue_yoy_above", "营收同比高于", "基本面",
                  lambda threshold=20, **k: C.revenue_yoy_above(threshold),
                  [ParamSpec("threshold", "营收同比(%) >", 20, -50, 300, 5)]),
    ConditionSpec("profit_yoy_above", "净利同比高于", "基本面",
                  lambda threshold=20, **k: C.profit_yoy_above(threshold),
                  [ParamSpec("threshold", "净利同比(%) >", 20, -50, 300, 5)]),
]

CATALOG_BY_KEY = {spec.key: spec for spec in CATALOG}


def categories() -> list[str]:
    """返回有序的类别列表。"""
    seen = []
    for spec in CATALOG:
        if spec.category not in seen:
            seen.append(spec.category)
    return seen


def build_conditions(selection: dict[str, dict]) -> list[Condition]:
    """根据界面选择构建条件列表。

    selection: {condition_key: {param_key: value, ...}}，只含被勾选的条件。
    """
    out = []
    for key, values in selection.items():
        spec = CATALOG_BY_KEY.get(key)
        if spec is not None:
            out.append(spec.build(values or {}))
    return out
