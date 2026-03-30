#!/usr/bin/env python3
"""
Polymarket Trading Bot
Autonomous trading with AI news analysis, statistical modeling, and arbitrage detection.
"""

import asyncio
import logging
import os
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

    running = True
    def shutdown(sig, frame):
        nonlocal running
        log.info("Shutdown signal received. Stopping bot gracefully...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start web dashboard
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
            # Step 1: Scan markets
            log.info("Scanning active markets...")
            markets = await scanner.get_active_markets(
                min_liquidity=config['min_liquidity']
            )
            log.info(f"Found {len(markets)} qualifying markets")

            if not markets:
                log.warning("No markets found. Waiting before retry...")
                await asyncio.sleep(60)
                continue

            # Step 2: AI signal analysis
            log.info("Running AI signal analysis on top markets...")
            top_markets = markets[:20]
            ai_signals = await ai_engine.analyze_markets(top_markets)
            log.info(f"AI generated {len(ai_signals)} signals")

            # Step 3: Arbitrage detection
            log.info("Checking for arbitrage opportunities...")
            arb_opportunities = await arbitrage.find_opportunities(markets)
            log.info(f"Found {len(arb_opportunities)} arbitrage opportunities")

            # Step 4: Combine and rank
            all_opportunities = ai_signals + arb_opportunities
            all_opportunities.sort(key=lambda x: x.get('expected_value', 0), reverse=True)

            # Step 5: Risk manager
            log.info("Applying risk management filters...")
            approved_trades = risk_manager.filter_and_size(all_opportunities)
            log.info(f"{len(approved_trades)} trades approved by risk manager")

            # Step 6: Execute or simulate
            for trade in approved_trades:
                result = await executor.execute(trade)
                bot_logger.log_trade(trade, result)

               # Track all trades for performance analysis
                if result.get('status') in ('dry_run', 'filled'):
                    tracker.record_simulated_trade(trade, result)

            # Step 7: Check if any previous simulated trades have resolved
            await tracker.check_resolutions()

            # Step 8: Log cycle summary
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
