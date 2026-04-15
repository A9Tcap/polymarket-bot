"""
Risk Manager — Kelly criterion sizing with win rate feedback loop.

Sizing logic:
1. Start with base size by conviction (HIGH=$30, MEDIUM=$22, LOW=$15)
2. Apply Kelly fraction based on edge and true probability
3. Apply win rate multiplier from historical data (if enough trades)
4. Cap at max position size (2% of bankroll)
5. Never exceed available bankroll
"""

import logging
import os
from typing import List, Dict, Optional

log = logging.getLogger('risk_manager')


class RiskManager:
    def __init__(self, config: Dict, win_rate_tracker=None):
        self.bankroll = config['bankroll']
        self.max_position_pct = config['max_position_pct']
        self.min_edge = config['min_edge']
        self.min_probability = config['min_probability']
        self.max_probability = config['max_probability']
        self.open_positions = {}
        self.daily_loss_limit_pct = 0.10
        self.daily_pnl = 0.0
        self.max_concurrent_positions = int(os.getenv('MAX_CONCURRENT_POSITIONS', '20'))
        self.win_rate_tracker = win_rate_tracker  # Optional — for sizing multiplier

    @property
    def available_bankroll(self):
        committed = sum(self.open_positions.values())
        return max(0, self.bankroll - committed)

    def filter_and_size(self, opportunities: List[Dict]) -> List[Dict]:
        approved = []

        if self.daily_pnl < -(self.bankroll * self.daily_loss_limit_pct):
            log.warning(f"Daily loss limit hit (PnL: ${self.daily_pnl:.2f}). No new trades.")
            return []

        if len(self.open_positions) >= self.max_concurrent_positions:
            log.warning(f"Max concurrent positions ({self.max_concurrent_positions}) reached.")
            return []

        for opp in opportunities:
            result = self._evaluate(opp)
            if result:
                approved.append(result)
                if len(approved) >= 3:
                    break

        return approved

    def _evaluate(self, opp: Dict) -> Optional[Dict]:
        market = opp.get('market', {})
        market_id = market.get('id') or market.get('ticker', '')
        edge = opp.get('edge', 0)
        direction = opp.get('direction', '')
        source = opp.get('source', '')
        conviction = opp.get('conviction', 'MEDIUM')

        # Skip if already have this position
        if market_id in self.open_positions:
            log.debug(f"Skipping {market_id}: already have position")
            return None

        # Minimum edge threshold
        min_edge = 0.03 if source == 'sports_engine' else self.min_edge
        if edge < min_edge:
            log.info(f"Skipping: edge {edge:.2%} below minimum {min_edge:.2%}")
            return None

        # Probability range check
        if direction in ('BUY_YES', 'BUY_NO'):
            yes_price = market.get('yes_price', 0.5)
            bet_price = yes_price if direction == 'BUY_YES' else (1 - yes_price)
            if bet_price < self.min_probability:
                log.info(f"Skipping: price {bet_price:.2%} below min {self.min_probability:.2%}")
                return None
            if bet_price > self.max_probability:
                log.info(f"Skipping: price {bet_price:.2%} above max {self.max_probability:.2%}")
                return None

        # Calculate position size
        position_size = self._calculate_size(opp, market_id)
        if position_size < 10:
            log.info(f"Skipping: size ${position_size:.2f} too small")
            return None

        if position_size > self.available_bankroll:
            position_size = min(self.available_bankroll * 0.9, position_size)
            if position_size < 10:
                log.info("Skipping: insufficient bankroll")
                return None

        log.info(
            f"Approved: {direction} ${position_size:.2f} "
            f"edge={edge:.2%} conviction={conviction} [{source}]"
        )
        return {**opp, 'position_size_usdc': round(position_size, 2)}

    def _calculate_size(self, opp: Dict, market_id: str) -> float:
        source = opp.get('source', '')
        conviction = opp.get('conviction', 'MEDIUM')
        edge = opp.get('edge', 0)
        true_prob = opp.get('true_probability', 0.85)
        market_price = opp.get('market_price', 0.85)
        market = opp.get('market', {})
        ticker = market.get('ticker', market_id)

        if source == 'sports_engine' or source == 'cross_platform':
            # Base conviction sizing for sports
            if conviction == 'HIGH':
                base = self.bankroll * 0.020   # $30 on $1500
            elif conviction == 'MEDIUM':
                base = self.bankroll * 0.015   # $22.50
            else:
                base = self.bankroll * 0.010   # $15

            # Apply win rate multiplier if tracker available
            if self.win_rate_tracker:
                multiplier = self.win_rate_tracker.get_sizing_multiplier(
                    ticker, market_price
                )
                base *= multiplier
                if multiplier != 1.0:
                    log.info(
                        f"Win rate multiplier {multiplier:.2f}x applied to {ticker}"
                    )

            return min(base, self.bankroll * self.max_position_pct)

        else:
            # Kelly criterion for macro
            return self._kelly_size(edge, true_prob, market_price)

    def _kelly_size(self, edge: float, true_prob: float, market_price: float) -> float:
        """Quarter-Kelly position sizing."""
        if market_price <= 0 or market_price >= 1:
            return self.bankroll * 0.01

        # b = net odds (what you win per $1 bet)
        b = (1 / market_price) - 1
        p = true_prob
        q = 1 - p

        if b <= 0:
            return self.bankroll * 0.01

        # Full Kelly fraction
        kelly = (b * p - q) / b
        kelly = max(0, min(kelly, 0.25))  # Cap raw Kelly at 25%

        # Quarter Kelly for safety
        safe_fraction = kelly * 0.25

        size = self.bankroll * safe_fraction
        return min(size, self.bankroll * self.max_position_pct)

    def record_position(self, market_id: str, size: float):
        self.open_positions[market_id] = size

    def close_position(self, market_id: str, pnl: float):
        if market_id in self.open_positions:
            del self.open_positions[market_id]
        self.daily_pnl += pnl
        self.bankroll += pnl
        log.info(f"Position closed. PnL: ${pnl:.2f} | Bankroll: ${self.bankroll:.2f}")
