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

# Configure logging
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
    log.info("  Polymarket Trading Bot Starting Up")
    log.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    # Validate environment variables
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

    # Configuration
    config = {
        'bankroll': float(os.getenv('BANKROLL_USDC', '1000')),
        'max_position_pct': float(os.getenv('MAX_POSITION_PCT', '0.05')),  # 5% max per trade
        'min_edge': float(os.getenv('MIN_EDGE', '0.04')),                  # 4% min edge required
        'scan_interval_seconds': int(os.getenv('SCAN_INTERVAL', '300')),   # scan every 5 min
        'min_probability': float(os.getenv('MIN_PROBABILITY', '0.55')),    # favor favorites
        'max_probability': float(os.getenv('MAX_PROBABILITY', '0.92')),    # avoid near-certainties
        'min_liquidity': float(os.getenv('MIN_LIQUIDITY', '5000')),        # min market liquidity
        'dry_run': os.getenv('DRY_RUN', 'true').lower() == 'true',         # paper trade by default
    }

    log.info(f"Config: bankroll=${config['bankroll']}, max_position={config['max_position_pct']*100}%, dry_run={config['dry_run']}")

    # Initialize components
    scanner = MarketScanner()
    ai_engine = AISignalEngine()
    arbitrage = ArbitrageDetector()
    risk_manager = RiskManager(config)
    executor = TradeExecutor(config)
    bot_logger = BotLogger()

    # Graceful shutdown
    running = True
    def shutdown(sig, frame):
        nonlocal running
        log.info("Shutdown signal received. Stopping bot gracefully...")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("Bot initialized. Starting main loop...")
    if config['dry_run']:
        log.info("*** DRY RUN MODE — No real trades will be placed ***")

    cycle = 0
    while running:
        cycle += 1
        log.info(f"\n--- Scan Cycle #{cycle} ---")

        try:
            # Step 1: Scan all active markets
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
            top_markets = markets[:20]  # analyze top 20 by volume
            ai_signals = await ai_engine.analyze_markets(top_markets)
            log.info(f"AI generated {len(ai_signals)} signals")

            # Step 3: Arbitrage detection
            log.info("Checking for arbitrage opportunities...")
            arb_opportunities = await arbitrage.find_opportunities(markets)
            log.info(f"Found {len(arb_opportunities)} arbitrage opportunities")

            # Step 4: Combine and rank opportunities
            all_opportunities = ai_signals + arb_opportunities
            all_opportunities.sort(key=lambda x: x.get('expected_value', 0), reverse=True)

            # Step 5: Risk manager filters and sizes positions
            log.info("Applying risk management filters...")
            approved_trades = risk_manager.filter_and_size(all_opportunities)
            log.info(f"{len(approved_trades)} trades approved by risk manager")

            # Step 6: Execute approved trades
            for trade in approved_trades:
                result = await executor.execute(trade)
                bot_logger.log_trade(trade, result)

            # Step 7: Log cycle summary
            bot_logger.log_cycle(cycle, markets, all_opportunities, approved_trades)

        except Exception as e:
            log.error(f"Error in scan cycle: {e}", exc_info=True)

        # Wait for next scan
        log.info(f"Cycle complete. Next scan in {config['scan_interval_seconds']}s...")
        for _ in range(config['scan_interval_seconds']):
            if not running:
                break
            await asyncio.sleep(1)

    log.info("Bot stopped cleanly.")


if __name__ == '__main__':
    asyncio.run(main())
