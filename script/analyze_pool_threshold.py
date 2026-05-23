"""Compare accumulation backtest performance across pool score thresholds."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from src.backtest.accumulation import run_accumulation_backtest
from src.backtest.data import SymbolData, load_all
from src.backtest.trade import Trade

_STEP_MS = 3_600_000
_DAY_MS = 86_400_000

# Pool symbols from current scan, grouped by score tier.
# Append USDT suffix for API calls.
_POOL_SYMBOLS_BY_SCORE: list[tuple[str, int]] = [
    ("RONINUSDT", 83), ("ALTUSDT", 82), ("HEIUSDT", 81),
    ("1000CHEEMSUSDT", 80), ("KAIAUSDT", 80), ("COOKIEUSDT", 80),
    ("MTLUSDT", 80), ("BEAMXUSDT", 80), ("GOATUSDT", 79),
    ("EDENUSDT", 79), ("TOWNSUSDT", 79), ("2ZUSDT", 79),
    ("SOPHUSDT", 78), ("SYNUSDT", 78), ("GMTUSDT", 78),
    ("HANAUSDT", 78), ("PROMPTUSDT", 78), ("LSKUSDT", 77),
    ("EPICUSDT", 77), ("NXPCUSDT", 77), ("STORJUSDT", 77),
    ("CTKUSDT", 77), ("AWEUSDT", 76), ("FOGOUSDT", 75),
    ("BBUSDT", 75), ("DIAUSDT", 74), ("VELODROMEUSDT", 74),
    ("SQDUSDT", 74), ("CHZUSDT", 73), ("1MBABYDOGEUSDT", 73),
    # ── score 72 (大族群) ──
    ("BNTUSDT", 73), ("CARVUSDT", 73), ("ARPAUSDT", 73),
    ("SHELLUSDT", 72), ("HFTUSDT", 72), ("FLOCKUSDT", 72),
    ("CKBUSDT", 72), ("WALUSDT", 72), ("STABLUSDT", 72),
    ("AVAUSDT", 72), ("TUSDT", 72), ("KMNOUSDT", 72),
    ("UMAUSDT", 72), ("MEWUSDT", 72), ("MOCAUSDT", 72),
    # ── score 71 ──
    ("ALLUSDT", 71), ("SYRUPUSDT", 71), ("IOSTUSDT", 71),
    ("MEUSDT", 71), ("LQTYUSDT", 71), ("HOMEUSD", 71),
    ("STEEMUSDT", 66), ("HIVEUSDT", 70), ("ZORAUSUSDT", 68),
]


def _summary(trades: list[Trade], label: str) -> dict[str, float]:
    done = [t for t in trades if t.pnl_pct is not None]
    if not done:
        print(f"  {label}: 無交易")
        return {}
    wins = [t for t in done if (t.pnl_pct or 0) > 0]
    total_pnl = sum(t.pnl_pct or 0 for t in done)
    win_rate = len(wins) / len(done) * 100
    avg = total_pnl / len(done) * 100
    exit_cnt: dict[str, int] = {}
    for t in done:
        k = t.exit_reason or "?"
        exit_cnt[k] = exit_cnt.get(k, 0) + 1
    exits = " ".join(f"{k}={v}" for k, v in sorted(exit_cnt.items()))
    print(
        f"  {label}: {len(done)}筆  勝率{win_rate:.0f}%  "
        f"均報酬{avg:+.2f}%  累計{total_pnl*100:.1f}%  [{exits}]"
    )
    return {"n": len(done), "win_rate": win_rate, "total_pnl": total_pnl * 100}


async def main() -> None:
    now = datetime.now(UTC)
    end_ms = (int(now.timestamp() * 1000) // _STEP_MS) * _STEP_MS
    start_ms = end_ms - 30 * 24 * _STEP_MS
    daily_start_ms = end_ms - 240 * _DAY_MS

    symbols = [s for s, _ in _POOL_SYMBOLS_BY_SCORE]
    score_map = {s: sc for s, sc in _POOL_SYMBOLS_BY_SCORE}

    print(f"下載 {len(symbols)} 個 Pool 幣種的 30 天歷史資料...")
    all_data = await load_all(
        symbols, start_ms=start_ms, end_ms=end_ms, daily_start_ms=daily_start_ms
    )
    print(f"成功取得 {len(all_data)} 個幣種\n")

    # Run backtest for all symbols, collect trades with pool score tag
    trades_with_score: list[tuple[Trade, int]] = []
    for symbol, data in all_data.items():
        score = score_map.get(symbol, 0)
        trades = run_accumulation_backtest(data, start_ms=start_ms, end_ms=end_ms)
        for t in trades:
            trades_with_score.append((t, score))

    print(f"總回測交易數（無門檻）：{len(trades_with_score)} 筆\n")

    # Top 20 exact: first 20 symbols in the score-sorted list that have data
    top20_symbols = {s for s, _ in _POOL_SYMBOLS_BY_SCORE[:20]}

    thresholds = [
        (77,  "Top ~20  (score ≥ 77)"),
        (74,  "Top ~29  (score ≥ 74)"),
        (73,  "Top ~33  (score ≥ 73)"),
        (72,  "Top ~44  (score ≥ 72)"),
        (0,   "全 Pool  (無門檻)    "),
    ]

    print("── 各門檻回測結果比較 ──")

    # 特別案例：完全照 Pool 顯示的 Top 20
    top20_trades = [t for t, _ in trades_with_score if t.symbol in top20_symbols]
    _summary(top20_trades, "Top 20 完全一致（僅掃這20個）")

    for min_score, label in thresholds:
        filtered = [t for t, sc in trades_with_score if sc >= min_score]
        _summary(filtered, label)


if __name__ == "__main__":
    asyncio.run(main())
