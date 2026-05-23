# crypto-monitor

`crypto-monitor` 是以 APScheduler、ccxt async 與 Discord webhook 為核心的加密貨幣策略通知服務。

策略流程放在 `src/strategies/`，共用的指標、評分與報告邏輯分層放在對應目錄。

## 目錄結構

```text
src/
├── clients/        # Binance、CoinGecko 等外部 API client
├── config/         # env 與 notification.json
├── core/           # scheduler、registry、Discord 輸出、共用設定與路徑
├── indicators/     # OI、Funding、CVD、LSR、Volatility
├── reports/        # 各策略 Discord 訊息格式
├── scoring/        # five-factor、accumulation、entry engine 評分
└── strategies/     # 策略流程
```

詳細 `src` 分層說明見 [src/README.md](src/README.md)。

## 策略說明

2 個策略的用途、邏輯、排程與輸出頻道見 [docs/strategies.md](docs/strategies.md)。

## 環境變數

參考 `.env.sample`：

```text
DISCORD_CHANNEL_TEST=
DISCORD_CHANNEL_CRITICAL=
DISCORD_CHANNEL_ACCUMULATION=
DISCORD_CHANNEL_FIVE_FACTOR=
```

`DISCORD_CHANNEL_TEST` 是啟動檢查頻道。程式啟動時會先送出 boot check 訊息，用來確認 Discord webhook 與通知管線可用。

`DISCORD_CHANNEL_CRITICAL` 是監控錯誤頻道。排程工作發生未捕捉例外時，錯誤會送到此頻道，訊息開頭格式為 `[monitor] <JobName> error at <timestamp>`，後面附上 traceback 摘要。

`DISCORD_CHANNEL_ACCUMULATION` 與 `DISCORD_CHANNEL_FIVE_FACTOR` 是策略輸出頻道；只有在 `src/config/notification.json` 內對應策略 `enabled: true` 時才是啟動必要環境變數。

## 安裝與執行

```sh
uv venv
uv sync
uv run main.py
```

## 部署

```sh
chmod +x script/deploy.sh
./script/deploy.sh
```

## 檢查

```sh
uv run ruff check .
uv run ruff format --check .
```

## 排程

APScheduler 目前明確使用 UTC。`AccumulationPool` 排程在 `18:00 UTC`，對應台北時間隔日 `02:00`。

程式啟動時若 `Accumulation` 啟用且行程內 `POOL` 尚未建立，會先執行一次 `AccumulationPool`，讓後續每小時的收籌掃描有標的池可用。`AccumulationScanner` 只掃描 `POOL` 內標的並輸出埋伏候選。

`src/core/registry.py` 的 `schedule()` 讀取 `src/config/notification.json` 的 `enabled` 欄位，只註冊 `enabled: true` 的策略。
