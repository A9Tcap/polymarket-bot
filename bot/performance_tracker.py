"""
Performance Tracker — accurately tracks simulated trades against real Kalshi outcomes.
Uses authenticated Kalshi API to fetch actual market resolutions.
"""

import logging
import json
import os
import time
import base64
import asyncio
import aiohttp
from datetime import datetime
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

log = logging.getLogger('performance_tracker')

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
TRACKER_FILE = "simulated_trades.jsonl"
RESULTS_FILE = "performance_results.json"


def get_auth_headers(method, path):
    api_key = os.getenv('KALSHI_API_KEY')
    private_key_str = os.getenv('KALSHI_PRIVATE_KEY', '')
    timestamp = str(int(time.time() * 1000))
    path_to_sign = path.split('?')[0]
    message = timestamp + method.upper() + path_to_sign
    key_str = private_key_str.strip().replace('\\n', '\n')
    try:
        private_key = serialization.load_pem_private_key(
            key_str.encode(), password=None, backend=default_backend()
        )
        sig = private_key.sign(
            message.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size),
            hashes.SHA256()
        )
        return {
            'KALSHI-ACCESS-KEY': api_key,
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
    except Exception as e:
        log.error(f"Auth error: {e}")
        return {'Content-Type': 'application/json'}


class PerformanceTracker:
    def __init__(self):
        self.session = None
        self.results = self._load_results()

    def _load_results(self):
        if os.path.exists(RESULTS_FILE):
            try:
                with open(RESULTS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
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

    def record_simulated_trade(self, trade: dict, result: dict):
        """Record a dry run trade for outcome tracking."""
        market = trade['market']
        ticker = market.get('ticker') or market.get('id', '')
        
        entry = {
            'id': f"{ticker}_{int(datetime.utcnow().timestamp())}",
            'timestamp': datetime.utcnow().isoformat(),
            'ticker': ticker,
            'question': market.get('question', ''),
            'direction': trade['direction'],
            'size_usdc': trade.get('position_size_usdc', 0),
            'entry_yes_price': market.get('yes_price', 0.5),
            'entry_no_price': market.get('no_price', 0.5),
            'edge': trade.get('edge', 0),
            'confidence': trade.get('confidence', ''),
            'reasoning': trade.get('reasoning', ''),
            'end_date': market.get('end_date', ''),
            'resolved': False,
            'outcome': None,
            'pnl': None,
            'won': None,
        }

        with open(TRACKER_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')

        self.results['total_simulated'] += 1
        self.results['total_staked'] += entry['size_usdc']
        self.results['trades'].append(entry)
        self._save_results()

        log.info(f"[TRACKER] Recorded: {trade['direction']} ${trade.get('position_size_usdc', 0):.2f} on '{market.get('question', '')[:50]}'")

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def check_resolutions(self):
        """Check Kalshi API for actual market outcomes."""
        if not os.path.exists(TRACKER_FILE):
            return

        # Load unresolved trades
        unresolved = []
        with open(TRACKER_FILE, 'r') as f:
            for line in f:
                try:
                    t = json.loads(line.strip())
                    if not t.get('resolved') and t.get('ticker'):
                        unresolved.append(t)
                except:
                    pass

        if not unresolved:
            return

        log.info(f"[TRACKER] Checking {len(unresolved)} unresolved trades against Kalshi...")
        session = await self._get_session()
        resolved_count = 0

        for trade in unresolved:
            ticker = trade.get('ticker', '')
            if not ticker:
                continue

            try:
                path = f'/trade-api/v2/markets/{ticker}'
                headers = get_auth_headers('GET', path)
                url = f"https://api.elections.kalshi.com{path}"

                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    market = data.get('market', {})

                status = market.get('status', '')
                result = market.get('result', '')  # 'yes' or 'no'

                if status == 'finalized' and result in ('yes', 'no'):
                    direction = trade['direction']
                    size = trade.get('size_usdc', 0)
                    entry_price = trade['entry_yes_price'] if direction == 'BUY_YES' else trade['entry_no_price']

                    # Did our bet win?
                    won = (direction == 'BUY_YES' and result == 'yes') or \
                          (direction == 'BUY_NO' and result == 'no')

                    if won and entry_price > 0:
                        pnl = size * ((1 / entry_price) - 1)
                    else:
                        pnl = -size

                    trade['resolved'] = True
                    trade['outcome'] = result
                    trade['won'] = won
                    trade['pnl'] = round(pnl, 2)
                    trade['resolved_at'] = datetime.utcnow().isoformat()

                    self.results['resolved'] += 1
                    self.results['total_pnl'] += pnl
                    if won:
                        self.results['wins'] += 1
                        log.info(f"[TRACKER] WIN +${pnl:.2f} | {ticker} | '{trade['question'][:50]}'")
                    else:
                        self.results['losses'] += 1
                        log.info(f"[TRACKER] LOSS -${abs(pnl):.2f} | {ticker} | '{trade['question'][:50]}'")

                    resolved_count += 1

            except Exception as e:
                log.debug(f"[TRACKER] Error checking {ticker}: {e}")

        if resolved_count > 0:
            # Rewrite tracker file with updated statuses
            all_trades = []
            ticker_map = {t['id']: t for t in unresolved if t.get('resolved')}

            with open(TRACKER_FILE, 'r') as f:
                for line in f:
                    try:
                        t = json.loads(line.strip())
                        if t.get('id') in ticker_map:
                            all_trades.append(ticker_map[t['id']])
                        else:
                            all_trades.append(t)
                    except:
                        pass

            with open(TRACKER_FILE, 'w') as f:
                for t in all_trades:
                    f.write(json.dumps(t) + '\n')

            self._save_results()
            self._print_summary()

    def _print_summary(self):
        r = self.results
        win_rate = (r['wins'] / r['resolved'] * 100) if r['resolved'] > 0 else 0
        roi = (r['total_pnl'] / r['total_staked'] * 100) if r['total_staked'] > 0 else 0
        log.info("=" * 55)
        log.info("  DRY RUN PERFORMANCE SUMMARY")
        log.info(f"  Simulated trades:  {r['total_simulated']}")
        log.info(f"  Resolved:          {r['resolved']}")
        log.info(f"  Wins / Losses:     {r['wins']} / {r['losses']}")
        log.info(f"  Win rate:          {win_rate:.1f}%")
        log.info(f"  Total staked:      ${r['total_staked']:.2f}")
        log.info(f"  Total P&L:         ${r['total_pnl']:.2f}")
        log.info(f"  ROI:               {roi:.1f}%")
        log.info("=" * 55)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
