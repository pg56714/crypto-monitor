# src 架構說明

這個目錄採用「策略流程」與「共用能力」分離的結構。策略不直接處理通知輸出細節，也不重複實作 OI、Funding、CVD、LSR 等共用指標。

## 分層職責

| 目錄 | 職責 |
| ---- | ---- |
| `clients/` | 外部 API client。Binance、CoinGecko、OpenRouter 等都放這裡。 |
| `config/` | 環境變數讀取與策略設定。 |
| `core/` | scheduler、registry、Discord 輸出、共用 config 與路徑。 |
| `indicators/` | 可重用指標計算，例如 OI、Funding、CVD、LSR、Volatility。 |
| `reports/` | 各策略的訊息格式與報告渲染。 |
| `scoring/` | 各策略評分公式與跨策略 entry engine。 |
| `strategies/` | 策略流程，例如 FiveFactor、AccumulationPool。 |

## 策略放置規則

策略流程一律放在 `src/strategies/`，目前採平鋪命名：

```text
strategies/
├── five_factor.py
├── accumulation_pool.py
└── accumulation_scanner.py
```

`accumulation` 不再獨立成子資料夾，避免策略數量尚少時目錄過深。

## 排程啟用規則

排程註冊集中在 `src/core/registry.py` 的 `schedule()`，只註冊 `enabled: true` 的策略。

所有策略註冊都會讀取 `src/config/notification.json` 的 `enabled` 欄位。APScheduler 使用 UTC，因此固定時間排程應以 UTC 填寫。

## OI 指標

OI 是共用指標：

```text
src/indicators/open_interest.py
```

策略需要 OI 時，應 import 共用函數，而不是另建 OI 策略。

## OpenRouter 的位置

AI 摘要透過 OpenRouter 的 OpenAI 相容 API 取得。相關程式放在：

```text
src/clients/openrouter.py
src/clients/ai_summary.py
```

OpenRouter 需要 `OPENROUTER_API_KEY`。`OPENROUTER_MODEL` 預設 `openrouter/free`，沒有 API key 時，AI 摘要層會回傳 `None`，策略應自然省略 AI 段落。
