"""
Bot Logger — logs trades and performance to file and console
"""

import logging
import json
import os
from datetime import datetime
from typing import List, Dict

log = logging.getLogger('bot_logger')


class BotLogger:
    def __init__(self):
        self.trade_log_file = 'trades.jsonl'
        self.stats = {
            'total_cycles': 0,
            'total_signals': 0,
            'total_trades': 0,
            'dry_run_trades': 0,
        }

    def log_trade(self, trade: Dict, result: Dict):
        """Log a trade execution to file."""
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'market_id': trade['market']['id'],
            'question': trade['market']['question'],
            'direction': trade['direction'],
            'size_usdc': trade.get('position_size_usdc'),
            'edge': trade.get('edge'),
            'confidence': trade.get('confidence'),
            'type': trade.get('type'),
            'source': trade.get('source'),
            'result': result,
        }

        with open(self.trade_log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        status = result.get('status', 'unknown')
        log.info(f"Trade logged: {trade['direction']} | status={status} | ${trade.get('position_size_usdc', 0):.2f}")
        self.stats['total_trades'] += 1
        if status == 'dry_run':
            self.stats['dry_run_trades'] += 1

    def log_cycle(self, cycle: int, markets: List, opportunities: List, trades: List):
        """Log a summary of each scan cycle."""
        self.stats['total_cycles'] = cycle
        self.stats['total_signals'] += len(opportunities)

        log.info(
            f"Cycle #{cycle} Summary | "
            f"Markets: {len(markets)} | "
            f"Signals: {len(opportunities)} | "
            f"Trades: {len(trades)} | "
            f"Total trades: {self.stats['total_trades']}"
        )

    def print_performance_summary(self):
        """Print overall bot performance stats."""
        log.info("=" * 50)
        log.info("BOT PERFORMANCE SUMMARY")
        log.info(f"  Total cycles run:    {self.stats['total_cycles']}")
        log.info(f"  Total signals found: {self.stats['total_signals']}")
        log.info(f"  Total trades:        {self.stats['total_trades']}")
        log.info(f"  Dry run trades:      {self.stats['dry_run_trades']}")
        log.info("=" * 50)
