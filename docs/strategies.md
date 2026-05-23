# 策略說明

crypto-monitor 共有 2 個策略,流程放在 `src/strategies/`,排程註冊於 `src/core/registry.py`,各自的設定在 `src/config/notification.json`(以區塊內的 `enabled` 開關)。APScheduler 以 UTC 排程。

> 2 個策略預設 `enabled: false`,各自實機驗證後再於 `notification.json` 開啟。若設定 OpenRouter 金鑰,各策略推播會自動附上一段 AI 摘要(無金鑰則略過)。

## 1. Accumulation — 吸籌偵測

每日對全市場做結構掃描,找出長期橫盤、低量、近期出現量能突破的中長線「埋伏」標的。分兩個排程、共用同一頻道:

- **AccumulationPool**(每日掃描):從日線判斷吸籌特徵 —— 需 ≥90 天資料、排除穩定幣與指數幣、近 7 日均價較前期漲幅超過 300% 則視為已啟動而排除;接著找出最長的橫盤窗口(≥45 天、振幅 ≤80%、日均量 ≤$50M),再算近 7 日量能相對橫盤期的突破倍數。0–100 分:橫盤天數(25)+ 振幅越窄越高(20)+ 量能越低越高(20)+ 量能突破(15)+ 估算市值 <$50M(20)。
- **AccumulationScanner**(每小時跟進):對候選標的做 OI 異動等跟進掃描;埋伏候選再用 Entry Engine 以橫盤窗口的高低點推算進出場區間(進場區、停損、目標、風報比)。

| 項目 | 內容 |
| --- | --- |
| 程式 | `src/strategies/accumulation_pool.py`、`accumulation_scanner.py` |
| 排程 | Pool:每日 18:00 UTC(台北 02:00);Scanner:每小時第 30 分 |
| 頻道 | `ACCUMULATION` |
| 設定 | `notification.json` 的 `Accumulation` |

## 2. Five-Factor — 五件套訊號掃描

每 5 分鐘對全市場永續合約跑「五件套」組合訊號,涵蓋動能(OI / Funding / CVD)、情緒(LSR)與價格驗證(ΔPrice),用來找短中線進出場點,降低單一指標的假訊號。

五個維度各給方向分 ±1(LSR 偵測到巨鯨分歧時給 ±2),加總範圍 −6 ~ +6:

- **維度**:OI 持倉量趨勢、Funding 資金費率(剛轉正 / 負、過熱)、CVD taker 買賣累積差、LSR 多空比三口徑(散戶 vs 巨鯨)、ΔPrice 收盤價變化方向。
- **訊號模式**:嘎空、多殺多、四象限狀態(健康漲跌 / 上漲衰竭 / 多頭投降)、巨鯨吸籌或派發、多空擠壓預警。
- **判定**:分數 ≥ +4 Entry Long、≥ +2 Watch Long、0 Ignore、≤ −2 Watch Short、≤ −4 Entry Short。同一標的 24 小時內只推一次。
- **輸出**:推播內容是「分數 + 判定」本身。FiveFactor 屬動能 / 時機訊號 —— 訊號出現即代表「現在市價進場」的時點,因此不附進場區間、停損、目標(那類需要像 Accumulation 的橫盤價格區間才推算得出)。

| 項目 | 內容 |
| --- | --- |
| 程式 | `src/strategies/five_factor.py`;評分 `src/scoring/five_factor.py`,指標 `src/indicators/` |
| 排程 | 每 5 分鐘 |
| 頻道 | `FIVE_FACTOR` |
| 設定 | `notification.json` 的 `FiveFactor`(`valid_symbol` / `timeframe` / `min_volume_usdt` / `score_threshold` / `dedup_hours`) |
