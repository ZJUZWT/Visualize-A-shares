"""
TradeValidator — A股虚拟盘交易规则校验
"""
from __future__ import annotations


class TradeValidator:
    """虚拟盘交易规则校验"""

    # 允许交易的股票代码前缀（沪深主板）
    ALLOWED_PREFIXES = ("600", "601", "603", "605", "000", "001", "002", "003")

    # 禁止交易的代码前缀
    BLOCKED_PREFIXES = ("300", "301", "688", "689", "8", "4")

    # 主板涨跌停幅度
    LIMIT_PCT = 10.0

    # 滑点
    SLIPPAGE_BUY = 0.002   # +0.2%
    SLIPPAGE_SELL = 0.002  # -0.2%

    # 手续费
    COMMISSION_RATE = 0.00025   # 万2.5
    MIN_COMMISSION = 5.0        # 最低佣金 5 元
    STAMP_TAX_RATE = 0.001      # 印花税 千1（仅卖出）
    TRANSFER_FEE_RATE = 0.00001 # 过户费 十万分之1（仅沪市）

    def validate_code(self, stock_code: str, stock_name: str) -> tuple[bool, str]:
        """校验股票代码白名单 + ST 检查"""
        # ST 检查
        if "ST" in stock_name.upper():
            return False, f"禁止交易 ST 股票: {stock_name}"

        # 黑名单优先
        for prefix in self.BLOCKED_PREFIXES:
            if stock_code.startswith(prefix):
                board = {
                    "300": "创业板", "301": "创业板",
                    "688": "科创板", "689": "科创板",
                    "8": "北交所", "4": "北交所/三板",
                }.get(prefix, "非主板")
                return False, f"不允许交易{board}股票: {stock_code}"

        # 白名单
        if not stock_code.startswith(self.ALLOWED_PREFIXES):
            return False, f"股票代码不在允许范围内: {stock_code}"

        return True, ""

    def validate_quantity(self, quantity: int) -> tuple[bool, str]:
        """校验交易数量（100 的整数倍，且 > 0）"""
        if quantity <= 0:
            return False, "交易数量必须大于 0"
        if quantity % 100 != 0:
            return False, f"交易数量必须是 100 的整数倍，当前: {quantity}"
        return True, ""

    def validate_t_plus_1(
        self, action: str, entry_date: str, trade_date: str
    ) -> tuple[bool, str]:
        """T+1 检查：sell/reduce 时持仓必须是昨天或更早买入的"""
        if action in ("buy", "add"):
            return True, ""
        if entry_date >= trade_date:
            return False, f"T+1 限制: 持仓买入日 {entry_date}，不能在 {trade_date} 卖出"
        return True, ""

    def validate_limit(
        self, action: str, pct_change: float
    ) -> tuple[bool, str]:
        """涨跌停检查"""
        if action in ("buy", "add") and pct_change >= self.LIMIT_PCT:
            return False, f"涨停({pct_change:.1f}%)不能买入"
        if action in ("sell", "reduce") and pct_change <= -self.LIMIT_PCT:
            return False, f"跌停({pct_change:.1f}%)不能卖出"
        return True, ""

    def validate_cash(
        self, action: str, price: float, quantity: int, cash: float
    ) -> tuple[bool, str]:
        """资金充足检查（仅买入）"""
        if action in ("sell", "reduce"):
            return True, ""
        needed = price * quantity
        if cash < needed:
            return False, f"资金不足: 需要 {needed:.2f}，可用 {cash:.2f}"
        return True, ""

    def validate_position_qty(
        self, action: str, current_qty: int, sell_qty: int
    ) -> tuple[bool, str]:
        """持仓充足检查（仅卖出）"""
        if action in ("buy", "add"):
            return True, ""
        if current_qty < sell_qty:
            return False, f"持仓不足: 持有 {current_qty}，卖出 {sell_qty}"
        return True, ""

    def apply_slippage(self, action: str, price: float) -> float:
        """计算含滑点的成交价"""
        if action in ("buy", "add"):
            return round(price * (1 + self.SLIPPAGE_BUY), 2)
        return round(price * (1 - self.SLIPPAGE_SELL), 2)

    def calc_fee(
        self, action: str, price: float, quantity: int, stock_code: str
    ) -> float:
        """计算手续费"""
        amount = price * quantity

        # 佣金（买卖双向）
        commission = max(amount * self.COMMISSION_RATE, self.MIN_COMMISSION)

        # 印花税（仅卖出）
        stamp = amount * self.STAMP_TAX_RATE if action in ("sell", "reduce") else 0.0

        # 过户费（仅沪市 6 开头）
        transfer = amount * self.TRANSFER_FEE_RATE if stock_code.startswith("6") else 0.0

        return round(commission + stamp + transfer, 2)
