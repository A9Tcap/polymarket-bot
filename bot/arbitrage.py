"""
Arbitrage Detector — finds pricing inconsistencies between correlated markets
"""

import logging
from typing import List, Dict
from itertools import combinations

log = logging.getLogger('arbitrage')


class ArbitrageDetector:
    def __init__(self):
        self.min_arb_edge = 0.03  # minimum 3% arbitrage edge

    async def find_opportunities(self, markets: List[Dict]) -> List[Dict]:
        """Find arbitrage opportunities across correlated markets."""
        opportunities = []

        # Strategy 1: Same-event YES+NO mispricing (should sum to ~1.0)
        overround_opps = self._find_overround_arbitrage(markets)
        opportunities.extend(overround_opps)

        # Strategy 2: Correlated markets (same topic, conflicting prices)
        correlated_opps = self._find_correlated_arbitrage(markets)
        opportunities.extend(correlated_opps)

        if opportunities:
            log.info(f"Found {len(opportunities)} arbitrage opportunities")

        return opportunities

    def _find_overround_arbitrage(self, markets: List[Dict]) -> List[Dict]:
        """
        Find markets where YES + NO prices don't sum to ~1.0
        If YES=0.45 and NO=0.45, we can buy both for 0.90 and collect 1.0 = 10% edge
        """
        opportunities = []
        for market in markets:
            yes = market['yes_price']
            no = market['no_price']
            total = yes + no

            # If total < 0.97, there's an arbitrage (buy both YES and NO)
            if total < (1.0 - self.min_arb_edge):
                edge = 1.0 - total
                opportunities.append({
                    'type': 'overround_arbitrage',
                    'market': market,
                    'direction': 'BUY_BOTH',
                    'edge': edge,
                    'expected_value': edge,
                    'confidence': 'HIGH',
                    'reasoning': f"YES({yes:.2%}) + NO({no:.2%}) = {total:.2%}, arbitrage edge of {edge:.2%}",
                    'source': 'arbitrage',
                    'yes_price': yes,
                    'no_price': no,
                })
                log.info(f"Overround arb: '{market['question'][:60]}' edge={edge:.2%}")

        return opportunities

    def _find_correlated_arbitrage(self, markets: List[Dict]) -> List[Dict]:
        """
        Find pairs of markets that are logically correlated but priced inconsistently.
        E.g., "Will X win?" at 60% and "Will X lose?" at 60% — both can't be right.
        """
        opportunities = []

        # Group markets by category
        by_category = {}
        for market in markets:
            cat = market.get('category', 'other')
            by_category.setdefault(cat, []).append(market)

        for category, cat_markets in by_category.items():
            if len(cat_markets) < 2:
                continue

            # Check pairs for keyword overlap suggesting correlation
            for m1, m2 in combinations(cat_markets[:30], 2):  # limit pairs checked
                opp = self._check_pair_correlation(m1, m2)
                if opp:
                    opportunities.append(opp)

        return opportunities

    def _check_pair_correlation(self, m1: Dict, m2: Dict) -> Dict:
        """
        Check if two markets are correlated and mispriced relative to each other.
        Simple heuristic: shared key terms + prices that conflict logically.
        """
        q1 = m1['question'].lower()
        q2 = m2['question'].lower()

        # Extract meaningful words (>4 chars)
        words1 = set(w for w in q1.split() if len(w) > 4)
        words2 = set(w for w in q2.split() if len(w) > 4)

        overlap = words1 & words2
        if len(overlap) < 3:
            return None  # Not correlated enough

        # Check for logical conflict: both YES prices high for mutually exclusive outcomes
        # e.g., "Will A win?" 70% and "Will B win?" 70% in same competition
        conflict_keywords = ['win', 'lose', 'beat', 'defeat', 'first', 'champion']
        has_conflict = any(kw in q1 and kw in q2 for kw in conflict_keywords)

        if has_conflict:
            total = m1['yes_price'] + m2['yes_price']
            if total > 1.05:  # Both priced too high for mutually exclusive events
                edge = total - 1.0
                if edge >= self.min_arb_edge:
                    return {
                        'type': 'correlated_arbitrage',
                        'market': m1,
                        'market2': m2,
                        'direction': 'SELL_BOTH_YES',
                        'edge': edge,
                        'expected_value': edge * 0.5,
                        'confidence': 'MEDIUM',
                        'reasoning': (
                            f"Correlated markets sum to {total:.2%} for mutually exclusive outcomes. "
                            f"Shared terms: {', '.join(list(overlap)[:5])}"
                        ),
                        'source': 'arbitrage',
                    }

        return None
