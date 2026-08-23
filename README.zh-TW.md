# crypto-monitor

[English](README.md) | [繁體中文](README.zh-TW.md)

`crypto-monitor` 是以 APScheduler、ccxt async 與 Discord webhook 為核心的加密貨幣市場監控與策略通知服務。程式分析 Binance Futures 與 CoinGecko 的公開市場資料，再將策略訊號傳送到指定的 Discord 頻道；它不會自動下單或管理交易。

> [!WARNING]
> 本專案僅供教育與研究用途，不構成任何金融、投資、交易或其他專業建議。加密貨幣市場具有高度波動與風險，使用本軟體或依據其輸出採取行動前，應自行評估並承擔相關風險。

## 主要功能

- 透過排程傳送 Discord 策略通知，並集中回報執行錯誤。
- FiveFactor：綜合 Funding、CVD、OI、LSR 與價格方向產生訊號。
- Accumulation：每日建立收籌標的池，再每小時掃描候選標的。
- 使用公開市場資料進行歷史回測，並產生 QuantStats 報告。
- 透過設定檔啟用或停用個別策略。
- 支援 Docker 部署與容器自動重啟。

## 使用需求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- 已啟用通知頻道的 Discord webhook URL
- 可連線至 Binance Futures 與 CoinGecko 公開 API
- 僅在使用容器部署時需要 Docker

## 快速開始

```sh
git clone https://github.com/pg56714/crypto-monitor.git
cd crypto-monitor
cp .env.sample .env
uv sync --locked
uv run main.py
```

PowerShell 可使用以下指令建立環境變數檔案：

```powershell
Copy-Item .env.sample .env
```

啟動服務前，請將 Discord webhook URL 填入 `.env`，並檢查 [`src/config/notification.json`](src/config/notification.json) 中啟用的策略。

## 環境變數

| 變數 | 用途 | 必要條件 |
| --- | --- | --- |
| `DISCORD_CHANNEL_TEST` | 接收程式啟動檢查訊息。 | 一律需要 |
| `DISCORD_CHANNEL_CRITICAL` | 接收排程工作未捕捉的錯誤。 | 一律需要 |
| `DISCORD_CHANNEL_ACCUMULATION` | 接收 Accumulation 策略通知。 | 啟用 Accumulation 時 |
| `DISCORD_CHANNEL_FIVE_FACTOR` | 接收 FiveFactor 策略通知。 | 啟用 FiveFactor 時 |

請以 [`.env.sample`](.env.sample) 為範本，切勿提交真實的 webhook URL。

## 策略

### FiveFactor

每小時掃描 USDT 永續合約，綜合 Funding、CVD、OI、LSR 與近期價格方向。分數大於等於 `4` 時傳送做多訊號，小於等於 `-4` 時傳送做空訊號。

### Accumulation

每日建立長期盤整且 Funding 或 OI 開始變化的標的池，再由每小時執行的掃描器評估池內標的是否符合收籌進場條件。

策略是否註冊到排程，由 [`src/config/notification.json`](src/config/notification.json) 中的 `enabled` 欄位控制。

## 排程

APScheduler 統一使用 UTC：

- FiveFactor：每小時的 `01:10` 執行。
- AccumulationPool：每日 `18:00 UTC` 執行，對應台北時間隔日 `02:00`。
- AccumulationScanner：每小時的 `30:00` 執行。
- 啟用 Accumulation 時，如果行程內的標的池尚未建立，程式啟動時會先初始化一次。

## 回測

使用預設的 30 天期間執行兩種策略：

```sh
uv run -m scripts.backtest_quantstats
```

只對指定標的執行 FiveFactor：

```sh
uv run -m scripts.backtest_quantstats --strategy ff --symbols BTCUSDT ETHUSDT SOLUSDT
```

報告與市場資料快取會輸出到已排除於 Git 的 `backtest_output/`。

## Docker 部署

先建立 `.env`，再執行：

```sh
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

部署腳本會建立映像、取代既有的 `crypto-monitor` 容器、確認新容器正常執行，並設定 `--restart unless-stopped`。

## 測試與品質檢查

```sh
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
```

## 專案結構

```text
src/
├── backtest/       # 歷史資料、交易模擬與報告
├── clients/        # Binance、CoinGecko 等外部 API client
├── config/         # 環境變數與策略設定
├── core/           # scheduler、registry、Discord 與共用路徑
├── indicators/     # OI、Funding、CVD、LSR 與 Volatility
├── reports/        # Discord 訊息格式
├── scoring/        # 策略評分與進場計畫計算
└── strategies/     # 排程策略流程
```

進階文件：

- [策略說明](docs/strategies.md)
- [回測操作手冊](docs/backtest_runbook.md)
- [原始碼架構](src/README.md)
- [回測架構](src/backtest/README.md)

## 授權

本專案採用 [Apache License 2.0](LICENSE)。
