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
        self.open_positions = {}
        self.daily_loss_limit_pct = 0.10
        self.daily_pnl = 0.0
        self.max_concurrent_positions = 10

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
        opp_type = opp.get('type', '')

        if market_id in self.open_positions:
            return None

        if edge < self.min_edge:
            log.debug(f"Skipping: edge {edge:.2%} below minimum {self.min_edge:.2%}")
            return None

        # Position sizing
        position_size = self._kelly_size(opp)
        max_position = self.bankroll * self.max_position_pct
        position_size = min(position_size, max_position)

        if position_size < 5:
            log.debug(f"Skipping: position size ${position_size:.2f} too small")
            return None

        if position_size > self.available_bankroll:
            position_size = min(self.available_bankroll * 0.9, position_size)
            if position_size < 5:
                log.debug("Skipping: insufficient bankroll")
                return None

        log.info(f"Approved: {direction} ${position_size:.2f} edge={edge:.2%} [{opp_type}]")

        return {
            **opp,
            'position_size_usdc': round(position_size, 2),
        }

    def _kelly_size(self, opp: Dict) -> float:
        edge = opp.get('edge', 0)
        true_prob = opp.get('true_probability', 0.6)
        direction = opp.get('direction', 'BUY_YES')
        market = opp.get('market', {})

        # Use the correct side's price for Kelly calculation
        if direction == 'BUY_NO':
            bet_price = market.get('no_price', 1 - opp.get('market_price', 0.5))
            win_prob = 1 - true_prob
        else:
            bet_price = opp.get('market_price', 0.5)
            win_prob = true_prob

        if bet_price <= 0 or bet_price >= 1:
            return self.bankroll * 0.01

        b = (1 / bet_price) - 1
        p = win_prob
        q = 1 - p

        if b <= 0:
            return self.bankroll * 0.01

        kelly_fraction = (b * p - q) / b
        kelly_fraction = max(0, min(kelly_fraction, 0.20))

        # Quarter Kelly for safety
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
