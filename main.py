#!/usr/bin/env python3
import asyncio
import logging
import os
import json
import signal
import sys
from datetime import datetime

from bot.scanner import MarketScanner
from bot.ai_engine import AISignalEngine
from bot.arbitrage import ArbitrageDetector
from bot.risk_manager import RiskManager
from bot.executor import TradeExecutor
from bot.logger import BotLogger
from bot.performance_tracker import PerformanceTracker
from bot.profit_taker import ProfitTaker
from dashboard import start_dashboard

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
log = logging.getLogger('main')

POSITIONS_FILE = 'open_positions.json'


def load_open_positions():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}


def save_open_positions(positions):
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(positions, f)


async def sync_positions_from_kalshi():
    """Pull real open positions from Kalshi API to prevent double-betting."""
    import time as _time
    import base64 as _base64
    import aiohttp as _aiohttp
    from cryptography.hazmat.primitives import hashes as _hashes, serialization as _serial
    from cryptography.hazmat.primitives.asymmetric import padding as _padding
    from cryptography.hazmat.backends import default_backend as _default_backend

    api_key = os.getenv('KALSHI_API_KEY')
    private_key_str = os.getenv('KALSHI_PRIVATE_KEY', '')
    timestamp = str(int(_time.time() * 1000))
    path = '/trade-api/v2/portfolio/positions'
    message = timestamp + 'GET' + path
    key_str = private_key_str.strip().replace('\\n', '\n')
    positions = {}
    try:
        private_key = _serial.load_pem_private_key(key_str.encode(), password=None, backend=_default_backend())
        sig = private_key.sign(message.encode(), _padding.PSS(mgf=_padding.MGF1(_hashes.SHA256()), salt_length=_hashes.SHA256.digest_size), _hashes.SHA256())
        headers = {
            'KALSHI-ACCESS-KEY': api_key,
            'KALSHI-ACCESS-SIGNATURE': _base64.b64encode(sig).decode(),
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
        async with _aiohttp.ClientSession() as session:
            url = f"https://api.elections.kalshi.com{path}"
            async with session.get(url, headers=headers, timeout=_aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for pos in data.get('market_positions', []):
                        if float(pos.get('position', 0)) != 0:
                            positions[pos['ticker']] = float(pos.get('total_cost', 0)) / 100
    except Exception as e:
        log.warning(f"Could not sync positions from Kalshi: {e}")
    return positions


async def main():
    log.info("=" * 60)
    log.info("  Kalshi Trading Bot Starting Up")
    log.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    required_env = [
        'KALSHI_API_KEY',
        'KALSHI_PRIVATE_KEY',
        'ANTHROPIC_API_KEY',
        'NEWS_API_KEY',
    ]
    missing = [v for v in required_env if not os.getenv(v)]
    if missing:
        log.error(f"Missing required environment variables: {missing}")
        sys.exit(1)

    config = {
        'bankroll': float(os.getenv('BANKROLL_USDC', '1500')),
        'max_position_pct': float(os.getenv('MAX_POSITION_PCT', '0.02')),
        'min_edge': float(os.getenv('MIN_EDGE', '0.04')),
        'scan_interval_seconds': int(os.getenv('SCAN_INTERVAL', '600')),
        'min_probability': float(os.getenv('MIN_PROBABILITY', '0.55')),
        'max_probability': float(os.getenv('MAX_PROBABILITY', '0.92')),
        'min_liquidity': float(os.getenv('MIN_LIQUIDITY', '100')),
        'dry_run': os.getenv('DRY_RUN', 'true').lower() == 'true',
    }

    log.info(f"Config: bankroll=${config['bankroll']}, max_position={config['max_position_pct']*100}%, dry_run={config['dry_run']}")

    scanner = MarketScanner()
    ai_engine = AISignalEngine()
    arbitrage = ArbitrageDetector()
    risk_manager = RiskManager(config)
    executor = TradeExecutor(config)
    bot_logger = BotLogger()
    tracker = PerformanceTracker()
    profit_taker = ProfitTaker(config)

    # Sync open positions from Kalshi API (source of truth)
    open_positions = await sync_positions_from_kalshi()
    risk_manager.open_positions = open_positions
    log.info(f"Synced {len(open_positions)} open positions from Kalshi")

    running = True
    def shutdown(sig, frame):
        nonlocal running
        log.info("Shutdown signal received. Stopping bot gracefully...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    dashboard = await start_dashboard()
    log.info("Dashboard started — view at your Railway public URL")
    log.info("Bot initialized. Starting main loop...")

    if config['dry_run']:
        log.info("*** DRY RUN MODE — Trades simulated & tracked for performance analysis ***")

    cycle = 0
    while running:
        cycle += 1
        log.info(f"\n--- Scan Cycle #{cycle} ---")

        try:
            log.info("Scanning active markets...")
            markets = await scanner.get_active_markets(min_liquidity=config['min_liquidity'])
            log.info(f"Found {len(markets)} qualifying markets")

            if not markets:
                log.warning("No markets found. Waiting before retry...")
                await asyncio.sleep(60)
                continue

            log.info("Running AI signal analysis on top markets...")
            top_markets = markets  # Pass all markets, AI engine handles filtering
            ai_signals = await ai_engine.analyze_markets(top_markets)
            log.info(f"AI generated {len(ai_signals)} signals")

            log.info("Checking for arbitrage opportunities...")
            arb_opportunities = await arbitrage.find_opportunities(markets)
            log.info(f"Found {len(arb_opportunities)} arbitrage opportunities")

            all_opportunities = ai_signals + arb_opportunities
            all_opportunities.sort(key=lambda x: x.get('expected_value', 0), reverse=True)

            # Re-sync positions from Kalshi each cycle to auto-clear resolved bets
            open_positions = await sync_positions_from_kalshi()
            risk_manager.open_positions = open_positions

            # Check for profit-taking and stop-loss opportunities
            exits = await profit_taker.check_and_exit_positions(open_positions)
            if exits:
                for exit in exits:
                    log.info(f"[PROFIT_TAKER] Exited {exit['ticker']}: {exit['action']} at {exit['exit_price']:.2%} (entry {exit['entry_price']:.2%})")
                # Re-sync after exits
                open_positions = await sync_positions_from_kalshi()
                risk_manager.open_positions = open_positions

            log.info("Applying risk management filters...")
            approved_trades = risk_manager.filter_and_size(all_opportunities)
            log.info(f"{len(approved_trades)} trades approved by risk manager")

            for trade in approved_trades:
                result = await executor.execute(trade)
                bot_logger.log_trade(trade, result)

                # Track all trades for dashboard
                if result.get('status') in ('dry_run', 'filled'):
                    tracker.record_simulated_trade(trade, result)

                # Persist position and record entry for profit-taking
                if result.get('status') == 'filled':
                    market_id = trade['market']['id']
                    open_positions[market_id] = trade.get('position_size_usdc', 0)
                    risk_manager.open_positions = open_positions
                    save_open_positions(open_positions)
                    # Record entry data for profit-taking
                    market = trade['market']
                    direction = trade['direction']
                    side = 'YES' if direction == 'BUY_YES' else 'NO'
                    entry_price = market['yes_price'] if direction == 'BUY_YES' else market['no_price']
                    contracts = trade.get('position_size_usdc', 15) / entry_price
                    market_type = market.get('market_type', 'sports')
                    profit_taker.record_entry(
                        ticker=market_id,
                        side=side,
                        entry_price=entry_price,
                        contracts=contracts,
                        cost_basis=trade.get('position_size_usdc', 15),
                        market_type=market_type,
                    )

            # Check if any tracked markets have resolved
            await tracker.check_resolutions()

            bot_logger.log_cycle(cycle, markets, all_opportunities, approved_trades)

        except Exception as e:
            log.error(f"Error in scan cycle: {e}", exc_info=True)

        log.info(f"Cycle complete. Next scan in {config['scan_interval_seconds']}s...")
        for _ in range(config['scan_interval_seconds']):
            if not running:
                break
            await asyncio.sleep(1)

    log.info("Bot stopped cleanly.")


if __name__ == '__main__':
    asyncio.run(main())
