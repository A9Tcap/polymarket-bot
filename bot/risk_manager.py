"""
Risk Manager — filters opportunities and sizes positions based on bankroll and risk rules
"""

import logging
from typing import List, Dict

log = logging.getLogger('risk_manager')


class RiskManager:
    def __init__(self, config: Dict):
        self.bankroll = config['bankroll']
        self.max_position_pct = config['max_position_pct']
        self.min_edge = config['min_edge']
        self.min_probability = config['min_probability']
        self.max_probability = config['max_probability']
        self.open_positions = {}  # market_id -> position size
        self.daily_loss_limit_pct = 0.10  # stop trading if down 10% in a day
        self.daily_pnl = 0.0
        self.max_concurrent_positions = 10

    @property
    def available_bankroll(self):
        committed = sum(self.open_positions.values())
        return max(0, self.bankroll - committed)

    def filter_and_size(self, opportunities: List[Dict]) -> List[Dict]:
        """Apply risk rules and return approved trades with position sizes."""
        approved = []

        # Check daily loss limit
        if self.daily_pnl < -(self.bankroll * self.daily_loss_limit_pct):
            log.warning(f"Daily loss limit hit (PnL: ${self.daily_pnl:.2f}). No new trades today.")
            return []

        # Check concurrent position limit
        if len(self.open_positions) >= self.max_concurrent_positions:
            log.warning(f"Max concurrent positions ({self.max_concurrent_positions}) reached.")
            return []

        for opp in opportunities:
            result = self._evaluate_opportunity(opp)
            if result:
                approved.append(result)
                # Limit to 3 new trades per cycle
                if len(approved) >= 3:
                    break

        return approved

    def _evaluate_opportunity(self, opp: Dict) -> Dict:
        """Evaluate a single opportunity against risk rules."""
        market = opp.get('market', {})
        market_id = market.get('id')
        edge = opp.get('edge', 0)
        direction = opp.get('direction', '')
        opp_type = opp.get('type', '')

        # Skip if already in this market
        if market_id in self.open_positions:
            log.debug(f"Skipping {market_id}: already have position")
            return None

        # Minimum edge requirement — lower threshold for sports (heavy fav strategy)
        source = opp.get('source', '')
        min_edge = 0.03 if source == "sports_engine" else self.min_edge
        if edge < min_edge:
            log.info(f"Skipping: edge {edge:.2%} below minimum {min_edge:.2%} ({source})")
            return None

        # Probability range filter (for directional trades)
        if direction in ('BUY_YES', 'BUY_NO'):
            yes_price = market.get('yes_price', 0.5)
            bet_price = yes_price if direction == 'BUY_YES' else market.get('no_price', 0.5)

            if bet_price < self.min_probability:
                log.debug(f"Skipping: price {bet_price:.2%} below min probability {self.min_probability:.2%}")
                return None
            if bet_price > self.max_probability:
                log.debug(f"Skipping: price {bet_price:.2%} above max probability {self.max_probability:.2%}")
                return None

        # Position sizing using Kelly Criterion (quarter Kelly for safety)
        position_size = self._kelly_size(opp)

        # Cap at max position size
        max_position = self.bankroll * self.max_position_pct
        position_size = min(position_size, max_position)

        # Minimum trade size
        if position_size < 10:
            log.debug(f"Skipping: position size ${position_size:.2f} too small")
            return None

        # Check available bankroll
        if position_size > self.available_bankroll:
            position_size = min(self.available_bankroll * 0.9, position_size)
            if position_size < 10:
                log.debug("Skipping: insufficient bankroll")
                return None

        log.info(f"Approved: {direction} ${position_size:.2f} edge={edge:.2%} [{opp_type}]")

        return {
            **opp,
            'position_size_usdc': round(position_size, 2),
        }

    def _kelly_size(self, opp: Dict) -> float:
        """
        Quarter-Kelly position sizing for safety.
        Kelly fraction = (bp - q) / b
        where b = odds - 1, p = win probability, q = 1 - p
        """
        edge = opp.get('edge', 0)
        true_prob = opp.get('true_probability', 0.6)
        market_price = opp.get('market_price', 0.5)

        if market_price <= 0 or market_price >= 1:
            return self.bankroll * 0.02

        # Decimal odds from market price
        b = (1 / market_price) - 1
        p = true_prob
        q = 1 - p

        if b <= 0:
            return self.bankroll * 0.02

        kelly_fraction = (b * p - q) / b
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # cap at 25%

        # Quarter Kelly
        safe_fraction = kelly_fraction * 0.25

        return self.bankroll * safe_fraction

    def record_position(self, market_id: str, size: float):
        self.open_positions[market_id] = size

    def close_position(self, market_id: str, pnl: float):
        if market_id in self.open_positions:
            del self.open_positions[market_id]
        self.daily_pnl += pnl
        self.bankroll += pnl
        log.info(f"Position closed. PnL: ${pnl:.2f} | Bankroll: ${self.bankroll:.2f} | Daily PnL: ${self.daily_pnl:.2f}")
