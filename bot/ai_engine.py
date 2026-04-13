"""
Expert AI Signal Engine — Elite Intelligence Edition

SPORTS STRATEGY:
- Acts as a seasoned sports analyst with deep knowledge of:
  * Injury reports, lineup changes, rest days
  * Home/away performance, travel fatigue
  * Head-to-head records, recent form
  * Weather, venue factors
  * Coaching strategies and matchup advantages
- Only bets heavy favourites (75%+) with HIGH conviction
- Rejects bets when key players are injured or missing

MACRO STRATEGY:
- Acts as a consensus of the world's top economists including:
  * Ben Bernanke, Janet Yellen (Fed chairs, macro policy)
  * Larry Summers (secular stagnation, fiscal policy)
  * Nouriel Roubini (crisis prediction, tail risks)
  * Mohamed El-Erian (market dynamics, Fed communication)
  * Paul Krugman (Keynesian, inflation expectations)
  * Raghuram Rajan (financial stability, emerging markets)
- ECONOMIC REALITY FILTER: Rejects bets that require impossible
  economic outcomes (e.g. Fed cutting 3%+ in 12 months)
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
    'NHL MLB injury report tonight 2026',
    'Trump tariffs economy recession 2026',
]

GOOGLE_NEWS_TOPICS = [
    'NBA injury report out tonight April 2026',
    'NHL injury lineup tonight April 2026',
    'Federal Reserve rate cut April 2026',
    'soccer injury Champions League tonight 2026',
    'tennis ATP WTA injury withdrawal 2026',
]

ECONOMIST_FRAMEWORK = """
YOU ARE A SYNTHESIS OF THE WORLD'S TOP ECONOMISTS AND MARKET STRATEGISTS.

Your knowledge combines:
- Ben Bernanke & Janet Yellen: Deep understanding of Fed policy transmission,
  the dual mandate, and how monetary policy affects real economy outcomes
- Larry Summers: Secular stagnation theory, fiscal multipliers, the risk that
  rates stay higher for longer due to structural factors
- Nouriel Roubini: Crisis prediction, tail risks, how geopolitical shocks
  (Iran war, energy prices) feed into inflation and recession probability
- Mohamed El-Erian: Market-Fed communication dynamics, how expectations
  get anchored, the danger of the Fed being behind the curve
- Paul Krugman: Inflation expectations, demand-side dynamics, why core
  inflation matters more than headline for Fed decisions
- Raghuram Rajan: Financial stability risks from rapid rate changes,
  why the Fed moves slowly and predictably

CURRENT MACRO REALITY (April 2026):
- Fed funds rate: 3.50-3.75% (held steady at Jan and Mar meetings)
- Core CPI: ~2.7% YoY (above 2% target, sticky)
- Headline CPI: jumped to ~3.3% in March due to Iran war energy shock
- Jobs market: stable, unemployment ~4.4%
- Fed dot plot: projects ONE cut in 2026, ONE in 2027
- Next FOMC: April 28-29 (no cut expected — 89%+ probability of hold)
- Powell term ends May 2026, Kevin Warsh nominated as new chair
- Iran war creating oil/energy price uncertainty
- Supreme Court struck down IEEPA tariffs Feb 2026

ECONOMIC REALITY CONSTRAINTS — IMMEDIATELY REJECT ANY BET REQUIRING:
1. Fed cutting more than 1.50% in next 12 months (requires 2008-level crisis)
2. Fed cutting more than 0.75% before end of 2026 (consensus: at most 1 cut)
3. Fed RAISING rates above current level (no realistic scenario)
4. Inflation dropping below 1.5% by end 2026 (structural floors exist)
5. Unemployment spiking above 6% without prior recession signals

FED RATE MARKET GUIDE (current rate 3.50-3.75%):
For "Will fed funds rate be above X% after April 2027 meeting?":
- Above 0.25%, 0.50%, 0.75%: Requires 2.75-3.5% in cuts = near impossible
  → If YES priced at 15-25%, it is OVERPRICED. But NO bet means you need
    a 2008-level crisis. DO NOT BET EITHER SIDE — too extreme.
- Above 2.00%, 2.25%, 2.50%: Requires 1.25-1.75% in cuts = possible recession
  → Only bet if there is genuine edge and economic logic supports it
- Above 3.00%, 3.25%: Requires only 0.50-0.75% cuts = most likely scenario
  → These are the most tradeable Fed rate markets
- Above 3.50%: Rate holds flat — currently right at this level
  → Watch FOMC carefully
"""

SPORTS_ANALYST_FRAMEWORK = """
YOU ARE AN ELITE SPORTS ANALYST combining the expertise of:
- ESPN's top injury analysts and beat reporters
- Vegas oddsmakers with 20+ years setting lines
- Advanced stats analysts (PER, RAPTOR, xG, Elo ratings)
- Travel and fatigue specialists (back-to-backs, road trips)

SPORTS BETTING RULES:
1. INJURIES ARE EVERYTHING — Check injury reports first. Never bet a
   favourite with a key player (starter, star) listed as OUT or DOUBTFUL.

2. VALIDATE THE FAVOURITE — Does the probability make sense?
   Consider: home/away, recent form, back-to-back games, matchup quality.

3. HOME ADVANTAGE — Home teams win ~60% NBA, ~55% soccer, ~57% NHL.
   An away favourite at 85% is stronger than a home favourite at 85%.

4. CONVICTION LEVELS:
   HIGH: 90%+ fav, healthy roster, good matchup, sportsbooks agree → $30
   MEDIUM: 80-89% fav, no injury concerns, reasonable matchup → $22
   LOW: 75-79% fav, minor uncertainty but clear favourite → $15
   SKIP: Key injury found, poor matchup, or genuine upset risk
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

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self.session

    async def fetch_newsapi(self, query: str) -> List[str]:
        session = await self._get_session()
        try:
            params = {'q': query, 'sortBy': 'publishedAt', 'pageSize': 3,
                     'language': 'en', 'apiKey': self.news_api_key}
            async with session.get(f"{NEWS_API_BASE}/everything", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    f"[{a.get('source',{}).get('name','')} | {a.get('publishedAt','')[:10]}] "
                    f"{a['title']}: {(a.get('description') or '')[:120]}"
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

    async def fetch_espn_injuries(self, sport: str = 'nba') -> List[str]:
        session = await self._get_session()
        sport_paths = {
            'nba': 'basketball/nba',
            'nhl': 'hockey/nhl',
            'mlb': 'baseball/mlb',
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
                        items.append(
                            f"[ESPN Injuries] {sport.upper()}: {team} — "
                            f"{athlete} {status} {injury_type}"
                        )
            return items
        except Exception as e:
            log.debug(f"ESPN injury error ({sport}): {e}")
            return []

    async def fetch_sportsbook_odds(self, sport_key: str) -> List[str]:
        if not self.odds_api_key:
            return []
        session = await self._get_session()
        try:
            params = {'apiKey': self.odds_api_key, 'regions': 'us',
                     'markets': 'h2h', 'oddsFormat': 'decimal'}
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
                    home_odds, away_odds = [], []
                    for bm in bookmakers[:3]:
                        for market in bm.get('markets', []):
                            if market.get('key') == 'h2h':
                                for outcome in market.get('outcomes', []):
                                    if outcome['name'] == home:
                                        home_odds.append(outcome['price'])
                                    elif outcome['name'] == away:
                                        away_odds.append(outcome['price'])
                    if home_odds and away_odds:
                        home_prob = round(1 / (sum(home_odds)/len(home_odds)) * 100, 1)
                        away_prob = round(1 / (sum(away_odds)/len(away_odds)) * 100, 1)
                        items.append(
                            f"[Sportsbook] {away} @ {home}: "
                            f"{home} {home_prob}% | {away} {away_prob}%"
                        )
            return items
        except Exception as e:
            log.debug(f"Odds API error: {e}")
            return []

    async def build_live_context(self) -> str:
        log.info("Building live intelligence from all sources...")
        tasks = []
        for topic in NEWSAPI_TOPICS[:3]:
            tasks.append(self.fetch_newsapi(topic))
        for topic in GOOGLE_NEWS_TOPICS[:3]:
            tasks.append(self.fetch_google_news(topic))
        for name, url in RSS_FEEDS.items():
            tasks.append(self.fetch_rss(name, url))
        tasks.append(self.fetch_finnhub_news('general'))
        tasks.append(self.fetch_finnhub_news('crypto'))
        tasks.append(self.fetch_espn_injuries('nba'))
        tasks.append(self.fetch_espn_injuries('nhl'))
        tasks.append(self.fetch_espn_injuries('mlb'))
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

    async def analyze_macro_market(self, market: Dict, live_context: str) -> Optional[Dict]:
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)

        prompt = f"""{ECONOMIST_FRAMEWORK}

MARKET TO EVALUATE:
Question: {question}
Ticker: {ticker}
Closes: {end_date[:16]}
Liquidity: ${liquidity:.0f}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}

LIVE INTELLIGENCE:
{live_context[:1500]}

STEP 1 — ECONOMIC REALITY CHECK:
What economic conditions are required for YES to resolve?
Are those conditions realistic? Apply the constraints above.
If economically implausible → signal=false, reality_check=failed.

STEP 2 — EDGE ANALYSIS (only if reality check passed):
Is the current price of {yes_price:.2%} mis-priced by 5%+?
Cite specific live data or economic logic.

STEP 3 — SIGNAL:
Only signal if: reality check passed + edge >= 5% + HIGH confidence.

JSON only:
{{"true_probability_yes": 0.72, "market_price_yes": {yes_price:.4f}, "edge": 0.08, "direction": "BUY_YES", "confidence": "HIGH", "conviction": "HIGH", "reasoning": "Economic logic + live data in 2 sentences", "key_risk": "main risk", "signal": true, "reality_check": "passed"}}
Failed: {{"signal": false, "direction": "SKIP", "reasoning": "Economic reality: explanation", "reality_check": "failed"}}
No edge: {{"signal": false, "direction": "SKIP", "reasoning": "no edge"}}"""

        try:
            response = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=400,
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

            reality = analysis.get('reality_check', 'unknown')
            if reality == 'failed':
                log.info(f"  ✗ MACRO reality check failed: {analysis.get('reasoning', '')[:80]}")
                return None

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

        if yes_price >= 0.75:
            fav_side = 'YES'
            fav_price = yes_price
        elif yes_price <= 0.25:
            fav_side = 'NO'
            fav_price = 1 - yes_price
        else:
            return None

        prompt = f"""{SPORTS_ANALYST_FRAMEWORK}

MARKET TO EVALUATE:
Question: {question}
Ticker: {ticker}
Closes: {end_date[:16]}
Liquidity: ${liquidity:.0f} | Volume: {volume:.0f}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}
Favourite: {fav_side} at {fav_price:.0%}

LIVE SPORTS INTELLIGENCE:
{live_context[:1500]}

STEP 1 — INJURY CHECK: Scan for any players OUT/DOUBTFUL on the favourite team.
STEP 2 — VALIDATE: Does {fav_price:.0%} make sense for this matchup?
STEP 3 — CONVICTION: Rate HIGH/MEDIUM/LOW based on analysis above.

JSON only:
{{"true_probability_yes": {yes_price + 0.04:.4f}, "market_price_yes": {yes_price:.4f}, "edge": 0.05, "direction": "BUY_{fav_side}", "confidence": "HIGH", "conviction": "MEDIUM", "reasoning": "Team health, matchup analysis, sportsbook comparison", "key_risk": "specific risk", "signal": true}}
Skip: {{"signal": false, "direction": "SKIP", "reasoning": "specific reason"}}"""

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

    async def analyze_markets(self, markets: List[Dict]) -> List[Dict]:
        signals = []
        live_context = await self.build_live_context()
        self.live_context = live_context

        macro_markets = [m for m in markets if m.get('market_type') == 'macro']
        sports_markets = [m for m in markets if m.get('market_type') == 'sports']

        macro_candidates = [
            m for m in macro_markets
            if 0.08 <= m['yes_price'] <= 0.92
            and m.get('liquidity', 0) > 0
        ]
        macro_candidates.sort(key=lambda x: x.get('liquidity', 0), reverse=True)

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
        sports_candidates.sort(key=lambda x: abs(x['yes_price'] - 0.5), reverse=True)

        log.info(
            f"Candidates — Macro: {len(macro_candidates)} (liq>0), "
            f"Sports: {len(sports_candidates)} (75%+ fav, vol>0)"
        )

        macro_signals = []
        for market in macro_candidates[:5]:
            log.info(
                f"  Macro: [{market['ticker']}] {market['question'][:55]} "
                f"(liq=${market.get('liquidity',0):.0f})"
            )
            try:
                signal = await asyncio.wait_for(
                    self.analyze_macro_market(market, live_context), timeout=22
                )
                if signal:
                    macro_signals.append(signal)
                    log.info(
                        f"  ✓ MACRO: {signal['direction']} edge={signal['edge']:.2%} "
                        f"| {signal['reasoning'][:70]}"
                    )
            except asyncio.TimeoutError:
                log.warning(f"  Hard timeout on macro {market['ticker']}")
            except Exception as e:
                log.warning(f"  Macro error: {e}")

        sports_signals = []
        for market in sports_candidates[:5]:
            log.info(
                f"  Sports: [{market['ticker']}] {market['question'][:50]} "
                f"yes={market['yes_price']:.0%} vol={market.get('volume',0):.0f}"
            )
            try:
                signal = await asyncio.wait_for(
                    self.analyze_sports_market(market, live_context), timeout=22
                )
                if signal:
                    sports_signals.append(signal)
                    log.info(
                        f"  ✓ SPORTS: {signal['direction']} edge={signal['edge']:.2%} "
                        f"conviction={signal.get('conviction','?')} | {signal['reasoning'][:70]}"
                    )
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
