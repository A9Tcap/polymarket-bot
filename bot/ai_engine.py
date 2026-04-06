"""
Expert AI Signal Engine — Maximum Edge Edition

Improvements:
1. ESPN injury reports fetched for every NBA/NHL/MLB game
2. Sportsbook consensus odds via The Odds API (free tier)
3. Economic calendar context for macro markets
4. Dynamic position sizing — bigger bets on higher conviction
5. Favourite-longshot bias exploitation
6. Multi-source live intelligence
"""

import logging
import asyncio
import os
import json
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from anthropic import AsyncAnthropic

log = logging.getLogger('ai_engine')

NEWS_API_BASE = "https://newsapi.org/v2"
FINNHUB_BASE = "https://finnhub.io/api/v1"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

RSS_FEEDS = {
    'Federal Reserve': 'https://www.federalreserve.gov/feeds/press_all.xml',
    'BLS (Jobs/CPI)': 'https://www.bls.gov/feed/bls_latest.rss',
    'Reuters Business': 'https://feeds.reuters.com/reuters/businessNews',
    'AP Markets': 'https://rsshub.app/apnews/topics/financial-markets',
}

NEWSAPI_TOPICS = [
    'Federal Reserve FOMC interest rate 2026',
    'CPI inflation jobs report April 2026',
    'NBA injury report tonight 2026',
    'NHL injury report tonight 2026',
    'Trump tariffs economy recession 2026',
]

GOOGLE_NEWS_TOPICS = [
    'NBA injury report out tonight April 2026',
    'NHL injury lineup tonight April 2026',
    'Federal Reserve rate cut April 2026',
    'CPI inflation data release April 2026',
    'soccer injury Champions League April 2026',
]

# Economic calendar — key dates for macro trading
ECON_CALENDAR = """
UPCOMING ECONOMIC RELEASES (April 2026):
- April 4  (Fri): Nonfarm Payrolls, Unemployment Rate — MAJOR MARKET MOVER
- April 10 (Thu): CPI Inflation MoM and YoY — MAJOR MARKET MOVER  
- April 11 (Fri): PPI Producer Price Index
- April 14 (Mon): Import/Export Prices
- April 16 (Thu): Retail Sales MoM
- April 17 (Fri): Housing Starts, Building Permits
- April 24 (Thu): Jobless Claims
- April 28 (Tue): Consumer Confidence
- April 28-29: Fed FOMC Meeting — MAJOR MARKET MOVER (rate decision)
- April 30 (Thu): GDP Q1 Advance, PCE Core Inflation
"""


class AISignalEngine:
    def __init__(self):
        self.anthropic = AsyncAnthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            timeout=20.0
        )
        self.news_api_key = os.getenv('NEWS_API_KEY')
        self.finnhub_key = os.getenv('FINNHUB_API_KEY', '')
        self.odds_api_key = os.getenv('ODDS_API_KEY', '')
        self.session = None
        self.live_context = ""
        self.injury_cache = {}  # Cache injury reports per cycle

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self.session

    # ── News fetchers ──────────────────────────────────────────────────────────

    async def fetch_newsapi(self, query: str) -> List[str]:
        session = await self._get_session()
        try:
            params = {'q': query, 'sortBy': 'publishedAt', 'pageSize': 3, 'language': 'en', 'apiKey': self.news_api_key}
            async with session.get(f"{NEWS_API_BASE}/everything", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    f"[{a.get('source',{}).get('name','')} | {a.get('publishedAt','')[:10]}] {a['title']}: {(a.get('description') or '')[:120]}"
                    for a in data.get('articles', [])[:3] if a.get('title')
                ]
        except:
            return []

    async def fetch_rss(self, name: str, url: str) -> List[str]:
        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
            root = ET.fromstring(text)
            items = []
            for item in root.iter('item'):
                title = item.findtext('title', '').strip()
                desc = item.findtext('description', '').strip()[:100]
                date = item.findtext('pubDate', '')[:16]
                if title:
                    items.append(f"[{name} | {date}] {title}: {desc}")
                if len(items) >= 3:
                    break
            return items
        except:
            return []

    async def fetch_google_news(self, query: str) -> List[str]:
        session = await self._get_session()
        try:
            url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
            root = ET.fromstring(text)
            items = []
            for item in root.iter('item'):
                title = item.findtext('title', '').strip()
                date = item.findtext('pubDate', '')[:16]
                if title:
                    items.append(f"[Google News | {date}] {title}")
                if len(items) >= 3:
                    break
            return items
        except:
            return []

    async def fetch_finnhub_news(self, category: str = 'general') -> List[str]:
        if not self.finnhub_key:
            return []
        session = await self._get_session()
        try:
            params = {'category': category, 'token': self.finnhub_key}
            async with session.get(f"{FINNHUB_BASE}/news", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
            return [
                f"[{a.get('source','')} | Finnhub] {a.get('headline','')}: {a.get('summary','')[:100]}"
                for a in data[:5] if a.get('headline')
            ]
        except:
            return []

    # ── Injury report fetcher ──────────────────────────────────────────────────

    async def fetch_espn_injuries(self, sport: str = 'nba') -> List[str]:
        """Fetch injury reports from ESPN's unofficial API."""
        session = await self._get_session()
        sport_paths = {
            'nba': 'basketball/nba',
            'nhl': 'hockey/nhl',
            'mlb': 'baseball/mlb',
            'nfl': 'football/nfl',
        }
        path = sport_paths.get(sport, 'basketball/nba')
        url = f"{ESPN_BASE}/{path}/injuries"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
            items = []
            injuries = data.get('injuries', data.get('items', []))
            for team_data in injuries[:10]:
                team = team_data.get('team', {}).get('displayName', '')
                for inj in team_data.get('injuries', [])[:3]:
                    athlete = inj.get('athlete', {}).get('displayName', '')
                    status = inj.get('status', '')
                    detail = inj.get('details', {})
                    injury_type = detail.get('type', '') if isinstance(detail, dict) else ''
                    if athlete and status:
                        items.append(f"[ESPN Injuries] {sport.upper()}: {team} — {athlete} {status} {injury_type}")
            return items
        except Exception as e:
            log.debug(f"ESPN injury fetch error ({sport}): {e}")
            return []

    async def fetch_sportsbook_odds(self, sport_key: str) -> List[str]:
        """Fetch consensus sportsbook odds to compare with Kalshi pricing."""
        if not self.odds_api_key:
            return []
        session = await self._get_session()
        try:
            params = {
                'apiKey': self.odds_api_key,
                'regions': 'us',
                'markets': 'h2h',
                'oddsFormat': 'decimal',
                'dateFormat': 'iso',
            }
            url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
            items = []
            for game in data[:10]:
                home = game.get('home_team', '')
                away = game.get('away_team', '')
                bookmakers = game.get('bookmakers', [])
                if bookmakers:
                    # Average odds across bookmakers
                    home_odds = []
                    away_odds = []
                    for bm in bookmakers[:3]:
                        for market in bm.get('markets', []):
                            if market.get('key') == 'h2h':
                                for outcome in market.get('outcomes', []):
                                    if outcome['name'] == home:
                                        home_odds.append(outcome['price'])
                                    elif outcome['name'] == away:
                                        away_odds.append(outcome['price'])
                    if home_odds and away_odds:
                        avg_home = sum(home_odds) / len(home_odds)
                        avg_away = sum(away_odds) / len(away_odds)
                        # Convert decimal odds to implied probability
                        home_prob = round(1 / avg_home * 100, 1)
                        away_prob = round(1 / avg_away * 100, 1)
                        items.append(f"[Sportsbook Consensus] {away} @ {home}: {home} {home_prob}% | {away} {away_prob}%")
            return items
        except Exception as e:
            log.debug(f"Odds API error: {e}")
            return []

    # ── Context builders ───────────────────────────────────────────────────────

    async def build_live_context(self) -> str:
        """Build comprehensive intelligence from all sources concurrently."""
        log.info("Building live intelligence from all sources...")

        tasks = []
        # News sources
        for topic in NEWSAPI_TOPICS[:3]:
            tasks.append(self.fetch_newsapi(topic))
        for topic in GOOGLE_NEWS_TOPICS[:3]:
            tasks.append(self.fetch_google_news(topic))
        for name, url in RSS_FEEDS.items():
            tasks.append(self.fetch_rss(name, url))
        tasks.append(self.fetch_finnhub_news('general'))
        tasks.append(self.fetch_finnhub_news('crypto'))

        # Injury reports for active sports
        tasks.append(self.fetch_espn_injuries('nba'))
        tasks.append(self.fetch_espn_injuries('nhl'))
        tasks.append(self.fetch_espn_injuries('mlb'))

        # Sportsbook odds (if API key available)
        if self.odds_api_key:
            tasks.append(self.fetch_sportsbook_odds('basketball_nba'))
            tasks.append(self.fetch_sportsbook_odds('icehockey_nhl'))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)

        seen = set()
        unique_items = []
        for item in all_items:
            key = item[:60]
            if key not in seen:
                seen.add(key)
                unique_items.append(item)

        log.info(f"Intelligence gathered: {len(unique_items)} unique items")
        return "\n".join(unique_items[:60]) if unique_items else "No live intelligence available."

    # ── Market analyzers ───────────────────────────────────────────────────────

    async def analyze_macro_market(self, market: Dict, live_context: str) -> Optional[Dict]:
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)

        prompt = f"""You are a top quantitative prediction market analyst exploiting Kalshi's favourite-longshot bias.

PROVEN EDGE: Research on 300,000+ Kalshi contracts confirms:
- High-probability contracts (70-90% YES) are SYSTEMATICALLY UNDERPRICED → BUY YES
- Low-probability contracts (10-30% YES) are SYSTEMATICALLY OVERPRICED → BUY NO

MARKET: {question}
TICKER: {ticker} | CLOSES: {end_date[:16]} | LIQUIDITY: ${liquidity:.0f}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}

ECONOMIC CALENDAR:
{ECON_CALENDAR}

LIVE INTELLIGENCE:
{live_context[:2000]}

MACRO CONTEXT (April 2026):
- Fed held at 3.50-3.75%. Next FOMC April 28-29. Rate cut very unlikely.
- Supreme Court struck down IEEPA tariffs Feb 2026. Inflation ~2.5%.
- Jobs report April 4. CPI release April 10. GDP April 30.
- Markets pricing in recession risk due to tariff uncertainty.

Signal requirements: edge >= 5%, HIGH confidence, cite specific data.

JSON only:
{{"true_probability_yes": 0.85, "market_price_yes": {yes_price:.4f}, "edge": 0.08, "direction": "BUY_YES", "confidence": "HIGH", "reasoning": "Specific 2-sentence reasoning citing live data", "key_risk": "main risk", "signal": true, "conviction": "HIGH"}}
No edge: {{"signal": false, "direction": "SKIP", "reasoning": "brief"}}"""

        try:
            response = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=350,
                    messages=[{"role": "user", "content": prompt}]
                ),
                timeout=20
            )
            raw = response.content[0].text.strip().replace('```json', '').replace('```', '').strip()
            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start == -1 or end == 0:
                return None
            analysis = json.loads(raw[start:end])

            edge = abs(float(analysis.get('edge', 0) or 0))
            direction = analysis.get('direction', 'SKIP')
            signal = analysis.get('signal', False)
            confidence = analysis.get('confidence', 'LOW')
            conviction = analysis.get('conviction', 'MEDIUM')
            true_prob_raw = analysis.get('true_probability_yes')

            if signal and direction != 'SKIP' and edge >= 0.05 and confidence == 'HIGH' and true_prob_raw is not None:
                true_prob = float(true_prob_raw)
                return {
                    'type': 'ai_signal',
                    'market': market,
                    'direction': direction,
                    'true_probability': true_prob,
                    'market_price': yes_price,
                    'edge': edge,
                    'confidence': confidence,
                    'conviction': conviction,
                    'reasoning': analysis.get('reasoning', ''),
                    'key_risk': analysis.get('key_risk', ''),
                    'expected_value': edge * min(true_prob, 1 - true_prob),
                    'source': 'macro_engine',
                }
        except asyncio.TimeoutError:
            log.warning(f"Timeout: '{question[:50]}'")
        except Exception as e:
            log.warning(f"Macro analysis failed '{question[:50]}': {e}")
        return None

    async def analyze_sports_market(self, market: Dict, live_context: str) -> Optional[Dict]:
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)
        volume = market.get('volume', 0)

        # Determine favourite
        if yes_price >= 0.75:
            fav_side = 'YES'
            fav_price = yes_price
        elif yes_price <= 0.25:
            fav_side = 'NO'
            fav_price = 1 - yes_price
        else:
            return None

        prompt = f"""You are an expert sports prediction market analyst. Your edge: betting heavy favourites (75%+) which are systematically underpriced on Kalshi.

MARKET: {question}
TICKER: {ticker} | CLOSES: {end_date[:16]}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}
LIQUIDITY: ${liquidity:.0f} | VOLUME: {volume:.0f}
FAVOURITE: {fav_side} at {fav_price:.0%}

LIVE SPORTS INTELLIGENCE (injury reports, lineup news, sportsbook odds):
{live_context[:1500]}

ANALYSIS RULES:
1. Check live intelligence for ANY injury to key players on the favourite team
2. Check if sportsbook odds align with Kalshi pricing (mispricing = bigger edge)
3. If sportsbook shows favourite at higher probability than Kalshi → STRONG signal
4. Default to betting favourite UNLESS specific injury/disruption found
5. Rate conviction: HIGH (90%+ fav, no injuries, sportsbook agrees), MEDIUM (75-89%, no issues), LOW (any concerns)

CONVICTION-BASED SIZING SIGNAL:
- HIGH conviction → signal edge=0.07
- MEDIUM conviction → signal edge=0.05  
- LOW conviction → skip

JSON only:
{{"true_probability_yes": {yes_price + 0.05:.4f}, "market_price_yes": {yes_price:.4f}, "edge": 0.05, "direction": "BUY_{fav_side}", "confidence": "HIGH", "conviction": "MEDIUM", "reasoning": "Specific reasoning citing injury report or sportsbook data", "key_risk": "upset risk", "signal": true}}
Skip if injuries found: {{"signal": false, "direction": "SKIP", "reasoning": "specific injury found"}}"""

        try:
            response = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}]
                ),
                timeout=20
            )
            raw = response.content[0].text.strip().replace('```json', '').replace('```', '').strip()
            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start == -1 or end == 0:
                return None
            analysis = json.loads(raw[start:end])

            edge = abs(float(analysis.get('edge', 0) or 0))
            direction = analysis.get('direction', 'SKIP')
            signal = analysis.get('signal', False)
            confidence = analysis.get('confidence', 'LOW')
            conviction = analysis.get('conviction', 'MEDIUM')
            true_prob_raw = analysis.get('true_probability_yes')

            if signal and direction != 'SKIP' and edge >= 0.03 and confidence == 'HIGH' and true_prob_raw is not None:
                true_prob = float(true_prob_raw)
                return {
                    'type': 'ai_signal',
                    'market': market,
                    'direction': direction,
                    'true_probability': true_prob,
                    'market_price': yes_price,
                    'edge': edge,
                    'confidence': confidence,
                    'conviction': conviction,
                    'reasoning': analysis.get('reasoning', ''),
                    'key_risk': analysis.get('key_risk', ''),
                    'expected_value': edge * min(true_prob, 1 - true_prob),
                    'source': 'sports_engine',
                }
        except asyncio.TimeoutError:
            log.warning(f"Timeout: '{question[:50]}'")
        except Exception as e:
            log.warning(f"Sports analysis failed '{question[:50]}': {e}")
        return None

    # ── Main entry point ───────────────────────────────────────────────────────

    async def analyze_markets(self, markets: List[Dict]) -> List[Dict]:
        signals = []

        live_context = await self.build_live_context()
        self.live_context = live_context

        macro_markets = [m for m in markets if m.get('market_type') == 'macro']
        sports_markets = [m for m in markets if m.get('market_type') == 'sports']

        # Macro: liquid markets sorted by liquidity desc
        macro_candidates = [
            m for m in macro_markets
            if 0.08 <= m['yes_price'] <= 0.92
            and m.get('liquidity', 0) > 0
        ]
        macro_candidates.sort(key=lambda x: x.get('liquidity', 0), reverse=True)

        # Sports: 75%+ favourites, volume > 0, resolves within 20 days
        now = datetime.now(timezone.utc)
        sports_candidates = []
        for m in sports_markets:
            if not (m['yes_price'] >= 0.75 or m['yes_price'] <= 0.25):
                continue
            if not (m.get('volume', 0) > 0 or m.get('liquidity', 0) > 0):
                continue
            end = m.get('end_date', '')
            if end:
                try:
                    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                    if not (now <= end_dt <= now + timedelta(days=20)):
                        continue
                except:
                    pass
            sports_candidates.append(m)

        # Sort sports by favouritism (most extreme first)
        sports_candidates.sort(key=lambda x: abs(x['yes_price'] - 0.5), reverse=True)

        log.info(f"Candidates — Macro: {len(macro_candidates)} (liq>0), Sports: {len(sports_candidates)} (75%+ fav, vol>0)")

        # Analyze top 5 macro
        macro_signals = []
        for market in macro_candidates[:5]:
            log.info(f"  Macro: [{market['ticker']}] {market['question'][:55]} (liq=${market.get('liquidity',0):.0f})")
            try:
                signal = await asyncio.wait_for(self.analyze_macro_market(market, live_context), timeout=22)
                if signal:
                    macro_signals.append(signal)
                    log.info(f"  ✓ MACRO: {signal['direction']} edge={signal['edge']:.2%} conviction={signal.get('conviction','?')} | {signal['reasoning'][:70]}")
            except asyncio.TimeoutError:
                log.warning(f"  Hard timeout on macro {market['ticker']}")
            except Exception as e:
                log.warning(f"  Macro error: {e}")

        # Analyze top 5 sports
        sports_signals = []
        for market in sports_candidates[:5]:
            log.info(f"  Sports: [{market['ticker']}] {market['question'][:50]} yes={market['yes_price']:.0%} vol={market.get('volume',0):.0f}")
            try:
                signal = await asyncio.wait_for(self.analyze_sports_market(market, live_context), timeout=22)
                if signal:
                    sports_signals.append(signal)
                    log.info(f"  ✓ SPORTS: {signal['direction']} edge={signal['edge']:.2%} conviction={signal.get('conviction','?')} | {signal['reasoning'][:70]}")
            except asyncio.TimeoutError:
                log.warning(f"  Hard timeout on sports {market['ticker']}")
            except Exception as e:
                log.warning(f"  Sports error: {e}")

        signals = macro_signals + sports_signals
        log.info(f"Signals: {len(macro_signals)} macro + {len(sports_signals)} sports")
        return signals

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
