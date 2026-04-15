"""
Win Rate Tracker — tracks performance by sport, league, price range,
and conviction level. Learns from results to improve future sizing.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict

log = logging.getLogger('win_rate_tracker')
DATA_FILE = 'win_rate_data.json'


class WinRateTracker:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> Dict:
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {
            'by_sport': {},
            'by_price_range': {},
            'by_market_type': {},
            'by_conviction': {},
            'all_trades': [],
        }

    def _save(self):
        try:
            with open(DATA_FILE, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            log.debug(f"Save error: {e}")

    def _sport_from_ticker(self, ticker: str) -> str:
        t = ticker.upper()
        if 'NBA' in t: return 'NBA'
        if 'NHL' in t: return 'NHL'
        if 'MLB' in t: return 'MLB'
        if 'EPL' in t: return 'EPL'
        if 'LALIGA' in t: return 'La Liga'
        if 'SERIEA' in t: return 'Serie A'
        if 'UCL' in t: return 'UCL'
        if 'BUNDESLIGA' in t: return 'Bundesliga'
        if 'LIGUE1' in t: return 'Ligue 1'
        if 'MLSGAME' in t or 'KXMLS' in t: return 'MLS'
        if 'ATP' in t: return 'ATP'
        if 'WTA' in t: return 'WTA'
        return 'Other'

    def _price_bucket(self, price: float) -> str:
        p = price * 100
        if p >= 95: return '95-99%'
        if p >= 90: return '90-94%'
        if p >= 85: return '85-89%'
        if p >= 80: return '80-84%'
        if p >= 75: return '75-79%'
        return '<75%'

    def _update(self, d: Dict, key: str, won: bool, profit: float, cost: float):
        if key not in d:
            d[key] = {'wins': 0, 'losses': 0, 'total': 0, 'profit': 0.0, 'cost': 0.0}
        d[key]['total'] += 1
        d[key]['profit'] += profit
        d[key]['cost'] += cost
        if won:
            d[key]['wins'] += 1
        else:
            d[key]['losses'] += 1

    def record_trade(self, ticker: str, side: str, entry_price: float,
                     market_type: str, conviction: str, cost: float, question: str = ''):
        self.data['all_trades'].append({
            'ticker': ticker, 'side': side, 'entry_price': entry_price,
            'market_type': market_type, 'conviction': conviction, 'cost': cost,
            'question': question[:80], 'placed_at': datetime.utcnow().isoformat(),
            'resolved': False, 'won': None, 'payout': 0.0,
        })
        if len(self.data['all_trades']) > 1000:
            self.data['all_trades'] = self.data['all_trades'][-1000:]
        self._save()

    def record_resolution(self, ticker: str, won: bool, payout: float):
        for trade in reversed(self.data['all_trades']):
            if trade['ticker'] == ticker and not trade['resolved']:
                trade['resolved'] = True
                trade['won'] = won
                trade['payout'] = payout
                trade['resolved_at'] = datetime.utcnow().isoformat()

                profit = payout - trade['cost']
                sport = self._sport_from_ticker(ticker)
                price_range = self._price_bucket(trade['entry_price'])

                self._update(self.data['by_sport'], sport, won, profit, trade['cost'])
                self._update(self.data['by_price_range'], price_range, won, profit, trade['cost'])
                self._update(self.data['by_market_type'], trade.get('market_type', 'unknown'), won, profit, trade['cost'])
                self._update(self.data['by_conviction'], trade.get('conviction', 'MEDIUM'), won, profit, trade['cost'])
                break

        self.data['last_updated'] = datetime.utcnow().isoformat()
        self._save()
        log.info(f"[WIN_RATE] {ticker}: {'WIN' if won else 'LOSS'} payout=${payout:.2f}")

    def get_sizing_multiplier(self, ticker: str, entry_price: float) -> float:
        """Returns 0.5-2.0x multiplier based on historical win rate in this category."""
        sport = self._sport_from_ticker(ticker)
        price_range = self._price_bucket(entry_price)
        multiplier = 1.0

        sport_data = self.data['by_sport'].get(sport, {})
        if sport_data.get('total', 0) >= 15:
            wr = sport_data['wins'] / sport_data['total']
            if wr >= 0.88: multiplier *= 1.30
            elif wr >= 0.82: multiplier *= 1.15
            elif wr < 0.70: multiplier *= 0.75

        price_data = self.data['by_price_range'].get(price_range, {})
        if price_data.get('total', 0) >= 15:
            wr = price_data['wins'] / price_data['total']
            if wr >= 0.90: multiplier *= 1.20
            elif wr < 0.72: multiplier *= 0.80

        return min(2.0, max(0.5, multiplier))

    def log_summary(self):
        log.info("=== WIN RATE SUMMARY ===")
        for label, data in [
            ('By Sport', self.data['by_sport']),
            ('By Price Range', self.data['by_price_range']),
            ('By Conviction', self.data['by_conviction']),
        ]:
            if not data:
                continue
            log.info(f"  {label}:")
            for key, s in sorted(data.items(), key=lambda x: x[1]['total'], reverse=True):
                if s['total'] == 0:
                    continue
                wr = s['wins'] / s['total'] * 100
                roi = (s['profit'] / s['cost'] * 100) if s['cost'] > 0 else 0
                log.info(
                    f"    {key}: {s['wins']}W/{s['losses']}L "
                    f"({wr:.0f}% WR) ROI={roi:+.1f}% profit=${s['profit']:+.2f}"
                )
