"""
Risk Manager — dynamic position sizing based on conviction level.
Sports: flat sizing by conviction (HIGH=$25, MEDIUM=$15, LOW=skip)
Macro: Kelly criterion quarter-Kelly
"""

import logging
import os
from typing import List, Dict

log = logging.getLogger('risk_manager')


class RiskManager:
    def __init__(self, config: Dict):
        self.bankroll = config['bankroll']
        self.max_position_pct = config['max_position_pct']
        self.min_edge = config['min_edge']
        self.min_probability = config['min_probability']
        self.max_probability = config['max_probability']
        self.open_positions = {}
        self.daily_loss_limit_pct = 0.10
        self.daily_pnl = 0.0
        self.max_concurrent_positions = int(os.getenv('MAX_CONCURRENT_POSITIONS', '15'))

    @property
    def available_bankroll(self):
        committed = sum(self.open_positions.values())
        return max(0, self.bankroll - committed)

    def filter_and_size(self, opportunities: List[Dict]) -> List[Dict]:
        approved = []

        if self.daily_pnl < -(self.bankroll * self.daily_loss_limit_pct):
            log.warning(f"Daily loss limit hit (PnL: ${self.daily_pnl:.2f}). No new trades today.")
            return []

        if len(self.open_positions) >= self.max_concurrent_positions:
            log.warning(f"Max concurrent positions ({self.max_concurrent_positions}) reached.")
            return []

        for opp in opportunities:
            result = self._evaluate_opportunity(opp)
            if result:
                approved.append(result)
                if len(approved) >= 3:
                    break

        return approved

    def _evaluate_opportunity(self, opp: Dict) -> Dict:
        market = opp.get('market', {})
        market_id = market.get('id')
        edge = opp.get('edge', 0)
        direction = opp.get('direction', '')
        source = opp.get('source', '')
        conviction = opp.get('conviction', 'MEDIUM')

        if market_id in self.open_positions:
            log.debug(f"Skipping {market_id}: already have position")
            return None

        # Edge thresholds by source
        min_edge = 0.03 if source == 'sports_engine' else self.min_edge
        if edge < min_edge:
            log.info(f"Skipping: edge {edge:.2%} below minimum {min_edge:.2%} ({source})")
            return None

        # Probability range filter
        if direction in ('BUY_YES', 'BUY_NO'):
            yes_price = market.get('yes_price', 0.5)
            bet_price = yes_price if direction == 'BUY_YES' else market.get('no_price', 0.5)

            if bet_price < self.min_probability:
                log.info(f"Skipping: price {bet_price:.2%} below min {self.min_probability:.2%}")
                return None
            if bet_price > self.max_probability:
                log.info(f"Skipping: price {bet_price:.2%} above max {self.max_probability:.2%}")
                return None

        # Dynamic position sizing
        if source == 'sports_engine':
            # Conviction-based flat sizing for sports
            if conviction == 'HIGH':
                position_size = self.bankroll * 0.02   # $30 on $1500
            elif conviction == 'MEDIUM':
                position_size = self.bankroll * 0.015  # $22.50
            else:
                position_size = self.bankroll * 0.01   # $15
        else:
            # Kelly for macro
            position_size = self._kelly_size(opp)

        # Cap at max position
        max_position = self.bankroll * self.max_position_pct
        position_size = min(position_size, max_position)

        if position_size < 10:
            log.info(f"Skipping: position size ${position_size:.2f} too small")
            return None

        if position_size > self.available_bankroll:
            position_size = min(self.available_bankroll * 0.9, position_size)
            if position_size < 10:
                log.info("Skipping: insufficient bankroll")
                return None

        log.info(f"Approved: {direction} ${position_size:.2f} edge={edge:.2%} conviction={conviction} [{source}]")

        return {**opp, 'position_size_usdc': round(position_size, 2)}

    def _kelly_size(self, opp: Dict) -> float:
        edge = opp.get('edge', 0)
        true_prob = opp.get('true_probability', 0.6)
        market_price = opp.get('market_price', 0.5)

        if market_price <= 0 or market_price >= 1:
            return self.bankroll * 0.01

        b = (1 / market_price) - 1
        p = true_prob
        q = 1 - p

        if b <= 0:
            return self.bankroll * 0.01

        kelly_fraction = (b * p - q) / b
        kelly_fraction = max(0, min(kelly_fraction, 0.25))
        safe_fraction = kelly_fraction * 0.25

        return self.bankroll * safe_fraction

    def record_position(self, market_id: str, size: float):
        self.open_positions[market_id] = size

    def close_position(self, market_id: str, pnl: float):
        if market_id in self.open_positions:
            del self.open_positions[market_id]
        self.daily_pnl += pnl
        self.bankroll += pnl
        log.info(f"Position closed. PnL: ${pnl:.2f} | Bankroll: ${self.bankroll:.2f}")
