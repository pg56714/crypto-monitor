# Backtest 系統說明

## 架構

```
src/backtest/
├── data.py          # 歷史資料下載（Binance Futures API）
├── trade.py         # Trade 資料類別 + 逐根K棒出場模擬
├── five_factor.py   # 五因子策略回測邏輯
├── accumulation.py  # 收籌/埋伏策略回測邏輯
└── report.py        # Quantstats HTML 報告 + 文字摘要

script/
├── backtest_quantstats.py   # 主要入口（兩策略 + HTML 報告）
└── backtest_five_factor.py  # 分數頻率統計（無進出場模擬）
```

## 執行

```bash
# 兩策略，前 20 大幣種，30 天
uv run -m script.backtest_quantstats

# 只跑五因子，指定幣種
uv run -m script.backtest_quantstats --strategy ff --symbols BTCUSDT ETHUSDT SOLUSDT

# 分數頻率分析（不含進出場）
uv run -m script.backtest_five_factor --days 7 --top-n 20
```

| 參數 | 預設 | 說明 |
|------|------|------|
| `--days` | 30 | 回測天數 |
| `--symbols` | — | 指定幣種，不填則取前 N 大 |
| `--top-n` | 20 | 取前 N 大交易量幣種 |
| `--strategy` | both | `ff` / `acc` / `both` |
| `--output` | backtest_output/ | HTML 報告輸出資料夾 |
| `--ff-session-tz` | UTC | FiveFactor 進場時段判斷時區 |
| `--ff-session-start-hour` | — | FiveFactor 允許進場起始小時（含） |
| `--ff-session-end-hour` | — | FiveFactor 允許進場結束小時（不含） |

報告輸出至 `backtest_output/five_factor.html` 和 `backtest_output/accumulation.html`（已加入 `.gitignore`）。

---

## 策略參數

### 五因子（FiveFactor）

| 項目 | 設定 |
|------|------|
| 時間框架 | 讀取 `src/config/notification.json` 的 `FiveFactor.timeframe` |
| 信號閾值 | score ≥ 4 或 ≤ −4（滿分 ±6） |
| 去重視窗 | 同方向 4 小時內不重複進場 |
| 停損 | 24根K棒最低/高點；距離 > 8% 改用 1.5% fallback |
| 目標1 | 進場 + 2R |
| 目標2 | 進場 + 3R |
| 最長持有 | 72 小時（依時間框架換算 K 棒數） |

### 收籌/埋伏（Accumulation）

| 項目 | 設定 |
|------|------|
| 時間框架 | 1h（掃描）/ 1d（Pool 計算） |
| Pool 更新 | 每天重算一次，需 90 天以上日線資料 |
| 進場條件 | `score_ambush_signal ≥ 20` + 有效進場計畫 |
| 有效進場計畫 | `vol_breakout ≥ 2×` 且 `d6h > 0` |
| 停損 | 壓力區下緣 × 0.97（低3%） |
| 目標1 | 壓力區上緣（resistance） |
| 目標2 | 壓力區上緣 × 1.2 |
| 最長持有 | 240 根（10 天） |

---

## 進出場邏輯

**進場：** 信號蠟燭收盤後，**下一根K棒開盤價**成交（假設市價單立即成交，無滑點）。

**出場優先順序（每根K棒依序判斷）：**
1. 開盤價跳空穿越停損 → 以開盤價出場
2. 最低/高點觸及停損 → 以停損價出場
3. 未到 TP1：觸及 TP1 → 50% 出場，繼續等 TP2 或停損
4. 已到 TP1：觸及 TP2 或停損 → 剩餘 50% 出場
5. 超過最長持有根數 → 全倉以收盤價出場

**手續費：** 0.1%（來回，各 0.05%），每筆交易扣除。

**P&L 計算：**
- 全倉出場：`exit / entry − 1 − fee`
- TP2 完整達標：`0.5 × (TP1/entry − 1) + 0.5 × (TP2/entry − 1) − fee`
- TP1 + 超時：`0.5 × (TP1/entry − 1) + 0.5 × (close/entry − 1) − fee`
- TP1 + 停損：`0.5 × (TP1/entry − 1) + 0.5 × (stop/entry − 1) − fee`

---

## 資料限制

| 端點 | 限制 |
|------|------|
| K線（signal timeframe / 1h / 1d） | 依 `startTime` / `endTime` 分頁抓取 |
| OI 歷史（signal timeframe / 1h） | 依 `startTime` / `endTime` 分頁抓取，保守請求最近 29 天 |
| 多空比（LSR） | 依 `startTime` / `endTime` 分頁抓取，保守請求最近 29 天 |
| 資金費率 | 依 `startTime` / `endTime` 分頁抓取 |

必要資料端點若失敗，該幣種會略過並列出錯誤，不會用空資料靜默替代。
下載結果會快取在 `backtest_output/cache/`，重跑相同區間時會優先使用快取，降低 Binance rate limit 風險。

---

## 已知誤差來源

1. **進場假設過樂觀** — 實際可能掛限價等不到，或滑點讓成本更高
2. **無完整倉位管理** — 報表以已結束交易的日報酬複合序列估算，未做逐根 K 棒資金佔用與同時持倉市值重估
3. **收籌 Pool 每天重算** — 實際運行中 Pool 在程序重啟前不會清除，行為略有差異
