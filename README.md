# Polymarket Trading Bot

Autonomous prediction market trading bot with AI news analysis, statistical modeling, and arbitrage detection.

## Strategy
- **AI Signal Engine**: Claude analyzes recent news against market prices to find mispriced contracts
- **Arbitrage Detector**: Finds pricing inconsistencies between correlated markets
- **Risk Manager**: Quarter-Kelly position sizing, daily loss limits, max concurrent positions
- **Safety First**: Runs in DRY RUN mode by default — no real money until you flip the switch

## Setup on Railway

### 1. Connect GitHub
- Fork or upload this repo to GitHub
- In Railway: New Project → Deploy from GitHub repo → select your repo

### 2. Set Environment Variables
In Railway, go to your service → **Variables** tab and add:

```
POLYMARKET_API_KEY=<your key>
POLYMARKET_WALLET_ADDRESS=<your address>
POLYMARKET_PRIVATE_KEY=<your private key>
ANTHROPIC_API_KEY=<your key>
NEWS_API_KEY=<your key>
BANKROLL_USDC=1000
DRY_RUN=true
```

### 3. Deploy
Railway will auto-detect Python and install requirements. The bot starts automatically.

### 4. Monitor
- Check the **Logs** tab in Railway to watch the bot run
- Trades are logged to `trades.jsonl`
- The bot scans markets every 5 minutes by default

### 5. Go Live
Once you've watched it run in dry-run mode for a few days and you're happy with the signals, change:
```
DRY_RUN=false
```

⚠️ **Only do this after funding your Polymarket wallet with USDC on Polygon.**

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| BANKROLL_USDC | 1000 | Total bankroll to manage |
| MAX_POSITION_PCT | 0.05 | Max 5% of bankroll per trade |
| MIN_EDGE | 0.04 | Minimum 4% edge required to trade |
| SCAN_INTERVAL | 300 | Seconds between market scans |
| MIN_PROBABILITY | 0.55 | Don't bet on outcomes below 55% |
| MAX_PROBABILITY | 0.92 | Don't bet on near-certainties |
| MIN_LIQUIDITY | 5000 | Minimum market liquidity in USDC |
| DRY_RUN | true | Paper trade mode (no real money) |

## Safety Features
- Daily loss limit: stops trading if down 10% in a day
- Max 10 concurrent positions
- Max 3 new trades per scan cycle
- Quarter-Kelly position sizing for conservative bankroll management
- Dry run mode on by default
