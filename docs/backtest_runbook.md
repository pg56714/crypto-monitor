# 回測操作 Runbook

## 目的

這份文件整理目前兩個策略的回測指令、FiveFactor 時段比較方式，以及 Binance API `418` 暫時封鎖時的處理方式。

## FiveFactor

### 全時段回測

```powershell
uv run -m scripts.backtest_quantstats --days 30 --top-n 20 --strategy ff --output backtest_output\ff_all
```

輸出：

```text
backtest_output\ff_all\five_factor.html
```

### 指定 FiveFactor 時間框架

```powershell
uv run -m scripts.backtest_quantstats --days 30 --top-n 20 --strategy ff --ff-timeframe 30m --output backtest_output\ff_30m
```

```powershell
uv run -m scripts.backtest_quantstats --days 30 --top-n 20 --strategy ff --ff-timeframe 1h --output backtest_output\ff_1h
```

### 台北時間日盤

```powershell
uv run -m scripts.backtest_quantstats --days 30 --top-n 20 --strategy ff --output backtest_output\ff_tpe_day --ff-session-tz Asia/Taipei --ff-session-start-hour 8 --ff-session-end-hour 16
```

輸出：

```text
backtest_output\ff_tpe_day\five_factor.html
```

### 台北時間美盤

```powershell
uv run -m scripts.backtest_quantstats --days 30 --top-n 20 --strategy ff --output backtest_output\ff_tpe_us --ff-session-tz Asia/Taipei --ff-session-start-hour 21 --ff-session-end-hour 5
```

輸出：

```text
backtest_output\ff_tpe_us\five_factor.html
```

### 比較重點

- `總交易數`
- `勝率`
- `平均報酬`
- `複合報酬`
- `Sharpe`
- `最大回撤`

單純指定 `--ff-session-tz` 但不指定 `--ff-session-start-hour` / `--ff-session-end-hour` 時，不會改變交易結果。時區參數只用來判斷「哪些本地小時允許進場」。

## Accumulation

### Pool 門檻比較

```powershell
uv run -m scripts.analyze_pool_threshold
```

用途：

- 使用 `scripts/analyze_pool_threshold.py` 內建的 Pool 標的清單。
- 比較不同 Pool score 門檻下的交易表現。
- 主要輸出在終端機，不產生 QuantStats HTML。

### Pool 標的產生 HTML 報表

```powershell
$poolSymbols = @(
  "RONINUSDT", "ALTUSDT", "HEIUSDT", "1000CHEEMSUSDT", "KAIAUSDT",
  "COOKIEUSDT", "MTLUSDT", "BEAMXUSDT", "GOATUSDT", "EDENUSDT",
  "TOWNSUSDT", "2ZUSDT", "SOPHUSDT", "SYNUSDT", "GMTUSDT",
  "HANAUSDT", "PROMPTUSDT", "LSKUSDT", "EPICUSDT", "NXPCUSDT",
  "STORJUSDT", "CTKUSDT", "AWEUSDT", "FOGOUSDT", "BBUSDT",
  "DIAUSDT", "VELODROMEUSDT", "SQDUSDT", "CHZUSDT", "1MBABYDOGEUSDT",
  "BNTUSDT", "CARVUSDT", "ARPAUSDT", "SHELLUSDT", "HFTUSDT",
  "FLOCKUSDT", "CKBUSDT", "WALUSDT", "STABLUSDT", "AVAUSDT",
  "TUSDT", "KMNOUSDT", "UMAUSDT", "MEWUSDT", "MOCAUSDT",
  "ALLUSDT", "SYRUPUSDT", "IOSTUSDT", "MEUSDT", "LQTYUSDT",
  "HOMEUSDT", "STEEMUSDT", "HIVEUSDT", "ZORAUSDT"
)

uv run -m scripts.backtest_quantstats --days 30 --strategy acc --symbols $poolSymbols --output backtest_output\acc_pool
```

輸出：

```text
backtest_output\acc_pool\accumulation.html
```

如果沒有產生 `accumulation.html`，代表該次回測沒有完成交易，或資料抓取被 Binance rate limit 阻擋。

## Binance 418 處理

`418` 表示 IP 因為在收到 `429` 後仍持續送出請求而被自動封鎖。Binance 官方文件說明，IP ban 會依重複違規程度延長，範圍是 2 分鐘到 3 天；`418` 或 `429` 回應會帶 `Retry-After` header，表示需要等待的秒數。

官方文件：

- [Binance Spot API Docs - Limits](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md)

### 檢查是否已解除

```powershell
.\scripts\check_binance_ban.ps1
```

判斷：

- 回 `200`：可以重跑回測。
- 回 `418` 且有 `Retry-After`：等待該秒數後再跑。
- 回 `418` 但沒有 `Retry-After`：不知道精確解除時間；保守先等 15 至 30 分鐘，再用上面的檢查指令確認。
- 連續重試會延長封鎖時間，最長可到 3 天。

## 建議流程

1. 先跑 FiveFactor 全時段。
2. 再跑台北日盤與美盤。
3. 等 Binance API 正常後跑 Accumulation Pool。
4. 若遇到 `429` 或 `418`，停止回測，先等 `Retry-After` 或至少 15 至 30 分鐘。
5. 重跑相同區間會使用 `backtest_output\cache`，可降低再次觸發 rate limit 的機率。
