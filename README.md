# crypto-monitor

[English](README.md) | [繁體中文](README.zh-TW.md)

`crypto-monitor` is a scheduled cryptocurrency market-monitoring service built with APScheduler, async ccxt clients, and Discord webhooks. It analyzes public Binance Futures and CoinGecko market data, then sends strategy alerts to configured Discord channels. It does not place or manage trades.

> [!WARNING]
> This project is provided for educational and research purposes only. Nothing in this repository constitutes financial, investment, trading, or other professional advice. Cryptocurrency markets are highly volatile, and you are solely responsible for evaluating the risks of using this software or acting on its output.

## Features

- Scheduled Discord alerts with centralized error reporting.
- FiveFactor signals based on funding, CVD, open interest, long/short ratios, and price action.
- Accumulation pool discovery and hourly candidate scanning.
- Historical backtesting with cached public market data and QuantStats reports.
- Strategy-level configuration without changing scheduler code.
- Docker deployment with automatic container restart.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Discord webhook URLs for the enabled notification channels
- Network access to the Binance Futures and CoinGecko public APIs
- Docker, only when using the container deployment workflow

## Quick start

```sh
git clone https://github.com/pg56714/crypto-monitor.git
cd crypto-monitor
cp .env.sample .env
uv sync --locked
uv run main.py
```

On PowerShell, create the environment file with:

```powershell
Copy-Item .env.sample .env
```

Before starting the service, add your Discord webhook URLs to `.env` and review the enabled strategies in [`src/config/notification.json`](src/config/notification.json).

## Environment variables

| Variable | Purpose | Required |
| --- | --- | --- |
| `DISCORD_CHANNEL_TEST` | Receives the startup boot check. | Always |
| `DISCORD_CHANNEL_CRITICAL` | Receives uncaught scheduler errors. | Always |
| `DISCORD_CHANNEL_ACCUMULATION` | Receives Accumulation alerts. | When Accumulation is enabled |
| `DISCORD_CHANNEL_FIVE_FACTOR` | Receives FiveFactor alerts. | When FiveFactor is enabled |

Use [`.env.sample`](.env.sample) as the template. Never commit real webhook URLs.

## Strategies

### FiveFactor

Runs hourly and evaluates USDT perpetual markets using funding, CVD, open interest, long/short ratios, and recent price direction. It sends long alerts at a score of `4` or higher and short alerts at `-4` or lower.

### Accumulation

Builds a daily pool of markets showing prolonged consolidation and changing funding or open-interest conditions. An hourly scanner then evaluates only the pooled symbols for potential accumulation entries.

Strategy registration is controlled by the `enabled` fields in [`src/config/notification.json`](src/config/notification.json).

## Scheduling

All APScheduler jobs use UTC:

- FiveFactor runs at minute `01:10` of every hour.
- AccumulationPool runs daily at `18:00 UTC` (`02:00` the following day in Taipei).
- AccumulationScanner runs at minute `30:00` of every hour.
- When Accumulation is enabled, the pool is initialized once at startup if necessary.

## Backtesting

Run both strategies for the default 30-day window:

```sh
uv run -m scripts.backtest_quantstats
```

Run FiveFactor for selected symbols:

```sh
uv run -m scripts.backtest_quantstats --strategy ff --symbols BTCUSDT ETHUSDT SOLUSDT
```

Generated reports and cached market data are stored in `backtest_output/`, which is excluded from Git.

## Docker deployment

Create `.env` first, then run:

```sh
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

The script builds the image, replaces the existing `crypto-monitor` container, verifies that the new container is running, and configures it with `--restart unless-stopped`.

## Tests and quality checks

```sh
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
```

## Project structure

```text
src/
├── backtest/       # Historical data, trade simulation, and reports
├── clients/        # Binance and CoinGecko API clients
├── config/         # Environment and strategy configuration
├── core/           # Scheduler, registry, Discord, and shared paths
├── indicators/     # OI, funding, CVD, LSR, and volatility indicators
├── reports/        # Discord message formatting
├── scoring/        # Strategy scores and entry-plan calculations
└── strategies/     # Scheduled strategy workflows
```

Additional documentation:

- [Strategy reference](docs/strategies.md) (Traditional Chinese)
- [Backtest runbook](docs/backtest_runbook.md) (Traditional Chinese)
- [Source architecture](src/README.md) (Traditional Chinese)
- [Backtest architecture](src/backtest/README.md) (Traditional Chinese)

## License

Licensed under the [Apache License 2.0](LICENSE).
