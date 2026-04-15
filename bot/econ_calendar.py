"""
Economic Calendar Pre-Positioner

Tracks upcoming scheduled economic releases and identifies
pre-release positioning opportunities on Kalshi.

Strategy:
- Before CPI: if consensus expects 3.1% and Kalshi prices "above 3.0%" at 35%,
  that's a mispricing we can exploit
- Before FOMC: if 89% chance of hold, find markets priced differently
- Before Jobs: position based on ADP preview and consensus
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

log = logging.getLogger('econ_calendar')

# Upcoming economic events — update monthly
# Format: (date_str, event_name, series_tickers, consensus_note)
ECONOMIC_CALENDAR_2026 = [
    # April 2026
    ('2026-04-28', 'FOMC Meeting (no cut expected)', ['KXEFFR', 'KXFED', 'KXRATECUT'], 'Fed holds at 3.50-3.75%, 89% probability'),
    ('2026-04-30', 'GDP Q1 Advance + PCE', ['KXGDP', 'KXPCECORE'], 'GDP ~2.0% expected, PCE ~2.7%'),
    # May 2026
    ('2026-05-08', 'Jobs Report April', ['KXPAYROLLS', 'KXU3'], 'Consensus ~150k jobs, unemployment 4.4%'),
    ('2026-05-13', 'CPI April', ['KXCPI', 'KXCPIYOY', 'KXCPICORE'], 'Expected to moderate as Iran energy shock fades'),
    ('2026-05-14', 'PPI April', ['KXPCECORE'], 'Watch for tariff pass-through'),
    ('2026-05-15', 'Retail Sales April', ['KXUSRETAIL'], 'Consumer spending key indicator'),
    # June 2026
    ('2026-06-05', 'Jobs Report May', ['KXPAYROLLS', 'KXU3'], 'Labor market stability key'),
    ('2026-06-11', 'CPI May', ['KXCPI', 'KXCPIYOY', 'KXCPICORE'], 'Energy base effects should help'),
    ('2026-06-17', 'FOMC Meeting', ['KXEFFR', 'KXFED', 'KXRATECUT'], 'First cut possible under new chair Warsh'),
    ('2026-06-25', 'GDP Q1 Final', ['KXGDP'], 'Revision to advance estimate'),
]


class EconomicCalendar:
    def __init__(self):
        self.calendar = ECONOMIC_CALENDAR_2026

    def get_upcoming_events(self, days_ahead: int = 14) -> List[Dict]:
        """Get economic events in the next N days."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days_ahead)
        upcoming = []

        for date_str, event_name, tickers, consensus in self.calendar:
            try:
                event_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(
                    tzinfo=timezone.utc, hour=13, minute=30  # 8:30am ET
                )
                if now <= event_dt <= cutoff:
                    days_until = (event_dt - now).days
                    upcoming.append({
                        'date': date_str,
                        'event': event_name,
                        'tickers': tickers,
                        'consensus': consensus,
                        'days_until': days_until,
                        'is_imminent': days_until <= 2,  # Within 48 hours
                    })
            except:
                continue

        return sorted(upcoming, key=lambda x: x['days_until'])

    def get_pre_positioning_context(self) -> str:
        """Generate context string for AI engine about upcoming catalysts."""
        upcoming = self.get_upcoming_events(days_ahead=7)
        if not upcoming:
            return "No major economic releases in the next 7 days."

        lines = ["UPCOMING ECONOMIC CATALYSTS (next 7 days):"]
        for event in upcoming:
            urgency = "⚡ IMMINENT" if event['is_imminent'] else f"T-{event['days_until']}d"
            lines.append(
                f"  [{urgency}] {event['date']} — {event['event']}"
                f"\n    Consensus: {event['consensus']}"
                f"\n    Related Kalshi series: {', '.join(event['tickers'])}"
            )

        lines.append("\nPRE-POSITIONING STRATEGY:")
        lines.append("  If Kalshi price differs from consensus by 5%+, signal a pre-release bet.")
        lines.append("  Imminent events (within 48h) have highest conviction — size UP.")
        lines.append("  Post-release: fade any overreaction — prices often overcorrect.")

        return "\n".join(lines)

    def is_release_day(self, ticker: str) -> bool:
        """Check if today is a release day for markets related to this ticker."""
        upcoming = self.get_upcoming_events(days_ahead=1)
        series = ticker.split('-')[0].upper()
        for event in upcoming:
            if any(series in t for t in event['tickers']):
                return True
        return False

    def get_release_context(self, ticker: str) -> Optional[str]:
        """Get specific context for a ticker if it has an imminent release."""
        upcoming = self.get_upcoming_events(days_ahead=3)
        series = ticker.split('-')[0].upper()
        for event in upcoming:
            if any(series in t for t in event['tickers']):
                return (
                    f"CALENDAR ALERT: {event['event']} on {event['date']} "
                    f"(T-{event['days_until']}d). Consensus: {event['consensus']}"
                )
        return None
