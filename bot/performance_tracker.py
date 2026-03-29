"""
Performance Tracker — tracks simulated trades and calculates P&L when markets resolve
"""

import logging
import json
import os
import aiohttp
from datetime import datetime
from typing import List, Dict, Optional

log = logging.getLogger('performance_tracker')

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
TRACKER_FILE = "simulated_trades.jsonl"
RESULTS_FILE = "performance_results.json"


class PerformanceTracker:
    def __init__(self):
        self.session = None
        self.results = self._load_results()

    def _load_results(self) -> Dict:
        if os.path.exists(RESULTS_FILE):
            with open(RESULTS_FILE, 'r') as f:
                return json.load(f)
        return {
            'total_simulated': 0,
            'resolved': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'total_staked': 0.0,
            'trades': []
        }

    def _save_results(self):
        with open(RESULTS_FILE, 'w') as f:
            json.dump(self.results, f, indent=2)

    def record_simulated_trade(self, trade: Dict, result: Dict):
        """Record a dry run trade for later outcome tracking."""
        market = trade['market']
        entry = {
            'id': f"{market['id']}_{int(datetime.utcnow().timestamp())}",
            'timestamp': datetime.utcnow().isoformat(),
            'ticker': market.get('ticker') or market.get('id'),
            'question': market['question'],
            'direction': trade['direction'],
            'size_usdc': trade.get('position_size_usdc', 0),
            'entry_yes_price': market['yes_price'],
            'entry_no_price': market['no_price'],
            'edge': trade.get('edge', 0),
            'confidence': trade.get('confidence', 'UNKNOWN'),
            'reasoning': trade.get('reasoning', ''),
            'end_date': market.get('end_date'),
            'resolved': False,
            'outcome': None,
            'pnl': None,
        }

        # Append to trade log
        with open(TRACKER_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        self.results['total_simulated'] += 1
        self.results['total_staked'] += entry['size_usdc']
        self.results['trades'].append(entry)
        self._save_results()

        log.info(
            f"[TRACKER] Recorded simulated trade: {trade['direction']} "
            f"${trade.get('position_size_usdc', 0):.2f} on '{market['question'][:50]}'"
        )

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def check_resolutions(self):
        """Check if any tracked markets have resolved and calculate P&L."""
        if not os.path.exists(TRACKER_FILE):
            return

        # Load all unresolved trades
        unresolved = []
        with open(TRACKER_FILE, 'r') as f:
            for line in f:
                try:
                    trade = json.loads(line.strip())
                    if not trade.get('resolved'):
                        unresolved.append(trade)
                except:
                    pass

        if not unresolved:
            log.info("[TRACKER] No unresolved trades to check")
            return

        log.info(f"[TRACKER] Checking {len(unresolved)} unresolved trades...")

        session = await self._get_session()
        resolved_count = 0

        for trade in unresolved:
            ticker = trade.get('ticker')
            if not ticker:
                continue

            try:
                url = f"{KALSHI_API}/markets/{ticker}"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    market = data.get('market', {})

                    status = market.get('status')
                    result = market.get('result')  # 'yes' or 'no'

                    if status == 'finalized' and result:
                        # Calculate P&L
                        direction = trade['direction']
                        size = trade['size_usdc']
                        entry_price = trade['entry_yes_price'] if direction == 'BUY_YES' else trade['entry_no_price']

                        # Did we win?
                        won = (direction == 'BUY_YES' and result == 'yes') or \
                              (direction == 'BUY_NO' and result == 'no')

                        if won:
                            # Profit = size * (1/entry_price - 1)
                            pnl = size * ((1 / entry_price) - 1)
                        else:
                            pnl = -size

                        trade['resolved'] = True
                        trade['outcome'] = result
                        trade['pnl'] = round(pnl, 2)
                        trade['won'] = won
                        trade['resolved_at'] = datetime.utcnow().isoformat()

                        # Update results
                        self.results['resolved'] += 1
                        self.results['total_pnl'] += pnl
                        if won:
                            self.results['wins'] += 1
                            log.info(f"[TRACKER] WIN +${pnl:.2f} | '{trade['question'][:50]}'")
                        else:
                            self.results['losses'] += 1
                            log.info(f"[TRACKER] LOSS -${abs(pnl):.2f} | '{trade['question'][:50]}'")

                        resolved_count += 1

            except Exception as e:
                log.warning(f"[TRACKER] Error checking {ticker}: {e}")

        if resolved_count > 0:
            self._save_results()
            self._print_summary()

    def _print_summary(self):
        r = self.results
        win_rate = (r['wins'] / r['resolved'] * 100) if r['resolved'] > 0 else 0
        roi = (r['total_pnl'] / r['total_staked'] * 100) if r['total_staked'] > 0 else 0

        log.info("=" * 55)
        log.info("  PERFORMANCE TRACKER SUMMARY")
        log.info(f"  Simulated trades:  {r['total_simulated']}")
        log.info(f"  Resolved:          {r['resolved']}")
        log.info(f"  Wins:              {r['wins']}")
        log.info(f"  Losses:            {r['losses']}")
        log.info(f"  Win rate:          {win_rate:.1f}%")
        log.info(f"  Total staked:      ${r['total_staked']:.2f}")
        log.info(f"  Total P&L:         ${r['total_pnl']:.2f}")
        log.info(f"  ROI:               {roi:.1f}%")
        log.info("=" * 55)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
