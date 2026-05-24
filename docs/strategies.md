# 策略說明

crypto-monitor 目前包含兩組策略，排程入口在 `src/core/registry.py`，設定檔在
`src/config/notification.json`。

## 1. Accumulation

Accumulation 用來尋找長時間盤整、資金費率與 OI 開始出現異動的標的。它分成兩個排程：

- 啟動初始化：程式啟動且 `Accumulation` 啟用時，若行程內 `POOL` 尚未建立，會先執行一次 `AccumulationPool`。
- `AccumulationPool`：每日更新收籌標的池。
- `AccumulationScanner`：每小時只掃描標的池，輸出埋伏候選。

`#accumulation` 頻道已代表策略類型，因此推播內容不再附加「埋伏」區塊標題。訊號會在條件足夠時附上單一限價、有效時間、停損、目標與風報比。短線追價與共振類訊號由 FiveFactor 負責。

## 2. FiveFactor

FiveFactor 每小時掃描 USDT 永續合約，綜合以下五類資料：

- Funding：資金費率過熱或轉向。
- CVD：主動買賣量差。
- OI：未平倉量變化。
- LSR：多空比與大戶部位分歧。
- Price：最近 K 線價格方向。

分數由各因子方向相加，範圍約為 `-6` 到 `+6`，其中 LSR 最高可提供 `+2` 或 `-2`。

推播規則固定為：

- `score >= 4`：做多進場。
- `score <= -4`：做空進場。
- 其他分數不推播。

FiveFactor 不再輸出 Watch 訊號，推播門檻固定在 `abs(score) >= 4`。同一標的會依多空方向分開冷卻，預設冷卻時間為 4 小時。

推播內容包含目前價格、分數、判定、資金費率、OI 變化、CVD、多空比、可偵測型態，以及市價進場、停損、目標與風報比。若沒有偵測到型態，訊息不會顯示型態欄位。
