# crypto-monitor

`crypto-monitor` 是以 APScheduler、ccxt async、polars 與 Discord webhook 為核心的加密貨幣策略通知服務。

策略流程放在 `src/strategies/`，共用的資料、指標、評分與報告邏輯分層放在對應目錄。

## 目錄結構

```text
src/
├── clients/        # Binance、CoinGecko、OpenRouter 等外部 API client
├── config/         # env 與 notification.json
├── core/           # scheduler、registry、Discord 輸出、共用設定與路徑
├── data/           # 資料模型
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
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openrouter/free
```

目前 `DISCORD_CHANNEL_TEST`、`DISCORD_CHANNEL_CRITICAL` 仍是啟動基本需求。OpenRouter 是可選功能，沒有 `OPENROUTER_API_KEY` 與 `OPENROUTER_MODEL` 時不會啟用 AI 摘要。`OPENROUTER_MODEL` 預設 `openrouter/free`（只路由免費模型），可改成 [openrouter.ai/models](https://openrouter.ai/models) 上任一 model id。

## 安裝與執行

```sh
uv venv
uv sync
uv run main.py
```

## 檢查

```sh
uv run ruff check .
uv run ruff format --check .
```

## 排程

APScheduler 目前明確使用 UTC。`AccumulationPool` 排程在 `18:00 UTC`，對應台北時間隔日 `02:00`。

`src/core/registry.py` 的 `schedule()` 讀取 `src/config/notification.json` 的 `enabled` 欄位，只註冊 `enabled: true` 的策略。
