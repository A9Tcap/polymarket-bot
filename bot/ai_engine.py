"""
Expert AI Signal Engine — Elite Intelligence Edition v3

SPORTS: Elite analyst, injury-first, conviction-based sizing
MACRO: World's top economist consensus, economic reality filter
POSITION ADVISOR: Evaluates all open positions for hold/sell each cycle
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

NEWS_API_BASE  = "https://newsapi.org/v2"
FINNHUB_BASE   = "https://finnhub.io/api/v1"
ESPN_BASE      = "https://site.api.espn.com/apis/site/v2/sports"
ODDS_API_BASE  = "https://api.the-odds-api.com/v4"

RSS_FEEDS = {
    'Federal Reserve': 'https://www.federalreserve.gov/feeds/press_all.xml',
    'BLS (Jobs/CPI)':  'https://www.bls.gov/feed/bls_latest.rss',
    'Reuters Business':'https://feeds.reuters.com/reuters/businessNews',
    'AP Markets':      'https://rsshub.app/apnews/topics/financial-markets',
}

NEWSAPI_TOPICS = [
    'Federal Reserve FOMC interest rate 2026',
    'CPI inflation jobs report April 2026',
    'NBA NHL MLB injury report tonight 2026',
    'Trump tariffs economy recession 2026',
    'tennis ATP WTA injury withdrawal 2026',
]

GOOGLE_NEWS_TOPICS = [
    'NBA injury report out tonight April 2026',
    'Federal Reserve rate cut April 2026',
    'soccer injury Champions League tonight 2026',
    'tennis ATP WTA injury withdrawal 2026',
]

# ── Economist Framework ────────────────────────────────────────────────────────
ECONOMIST_FRAMEWORK = """
YOU ARE A SYNTHESIS OF THE WORLD'S TOP ECONOMISTS:
Ben Bernanke, Janet Yellen, Larry Summers, Nouriel Roubini,
Mohamed El-Erian, Paul Krugman, Raghuram Rajan.

CURRENT MACRO REALITY (April 2026):
- Fed funds rate: 3.50-3.75% (held steady Jan + Mar meetings)
- Core CPI: ~2.7% YoY | Headline CPI: ~3.3% (Iran war energy shock)
- Unemployment: ~4.4% | GDP growth: ~2.4%
- Fed dot plot: ONE cut in 2026, ONE in 2027
- Next FOMC: April 28-29 — NO CUT expected (89%+ probability hold)
- Powell term ends May 2026, Kevin Warsh nominated as new chair
- Market pricing: rates hold through most of 2026

ECONOMIC REALITY — HARD REJECT THESE SCENARIOS:
1. Fed cutting >1.50% in next 12 months → requires 2008-level crisis
2. Fed cutting >0.75% before end 2026 → consensus: at most 1 cut of 0.25%
3. Inflation dropping below 1.5% by end 2026 → structural floors exist
4. Unemployment spiking above 6% without prior recession signal

FED RATE MARKET GUIDE (rates currently at 3.50-3.75%):
"Above X% after April 2027 FOMC" — what does NO winning require?
- NO Above 0.25%: rates must DROP to ≤0.25% = needs 3.25%+ in cuts = CRISIS ONLY
- NO Above 0.50%: rates must DROP to ≤0.50% = needs 3.0%+ in cuts = CRISIS ONLY
- NO Above 0.75%: rates must DROP to ≤0.75% = needs 2.75%+ in cuts = CRISIS ONLY
- NO Above 2.25%: needs 1.25%+ in cuts = possible deep recession scenario
- NO Above 2.50%: needs 1.0%+ in cuts = possible if economy weakens
- NO Above 3.00%: needs only 0.50%+ cuts = plausible base case
- NO Above 3.25%: needs only 0.25%+ cuts = most likely scenario

TRADEABLE MACRO MARKETS: "Above 3.00%" and "Above 3.25%" have real edge.
DO NOT BET: "Above 0.25%", "Above 0.50%", "Above 0.75%" — outcomes require crisis.

COMMODITY MARKETS (high opportunity right now):
- Oil/WTI: Iran war driving volatility. Above/below price targets have real edge.
- Gold: Safe haven demand elevated. Direction depends on recession vs inflation balance.
- Agricultural (NEW — wheat, corn, soybeans, coffee): Early markets, likely mispriced.
  Iran war disrupting shipping routes through Hormuz affects global food commodity prices.
  Look for markets where Kalshi price diverges from futures market consensus.
- Copper/Lithium: China slowdown risk vs EV demand — genuine uncertainty, tradeable edge.

POLITICAL MARKETS (midterm season building):
- Fed Chair Warsh confirmation: Highly liquid, genuine uncertainty about Senate vote.
- Congressional approval markets: Primary season creating volatile short-term markets.
- Trump approval: Track vs 45% threshold markets — poll data gives real edge here.
- Debt ceiling/shutdown: Always has edge when deadline approaches.
- Apply same economic reality filter: only bet when you have specific data advantage.
"""

# ── Sports Analyst Framework ───────────────────────────────────────────────────
SPORTS_ANALYST_FRAMEWORK = """
YOU ARE AN ELITE SPORTS ANALYST — Vegas oddsmaker, ESPN injury analyst,
advanced stats expert combined.

CORE RULE: Heavy favourites (75%+) on Kalshi are SYSTEMATICALLY UNDERPRICED
due to favourite-longshot bias. Your job is to confirm the favourite is
legitimate and bet it confidently.

STEP 1 — INJURY CHECK (MANDATORY):
Search the live intelligence for the teams/players in this market.
If a KEY player (starter, star) is OUT or DOUBTFUL for the favourite → SKIP.
If no injury found → proceed to Step 2.

STEP 2 — VALIDATE THE FAVOURITE:
Does this probability make sense? Consider:
- Home/away (home wins ~60% NBA, ~55% soccer, ~57% NHL)
- Recent form (winning streak vs losing streak)
- Back-to-back games (fatigue)
- Matchup quality

STEP 3 — SIGNAL DECISION:
If favourite is healthy and probability is legitimate → SIGNAL.
Do NOT overthink. A healthy 90%+ favourite with no disruptions IS a signal.

CONVICTION SIZING:
- HIGH: 90%+ fav, healthy, good matchup → edge=0.07
- MEDIUM: 80-89% fav, no issues → edge=0.05
- LOW: 75-79% fav, minor concerns → edge=0.04
"""

# ── Position Advisor Framework ─────────────────────────────────────────────────
POSITION_ADVISOR_FRAMEWORK = """
YOU ARE A PORTFOLIO MANAGER evaluating an existing prediction market position.
Your job is to give a clear HOLD or SELL recommendation.

HOLD if:
- The original thesis is still intact
- Current price reflects temporary noise, not a fundamental change
- Holding to resolution gives better expected return than selling now
- Slippage/spread would eat most of the gain from selling

SELL if:
- The thesis has fundamentally changed (new information contradicts the bet)
- Position has captured 70%+ of maximum possible profit (lock in gains)
- A key event has occurred that makes losing much more likely
- Capital could be redeployed into higher-conviction opportunities

For Fed rate positions specifically:
- "Above 0.25/0.50/0.75% NO" — thesis is rates DON'T drop to near-zero.
  Hot CPI (3.3%) and Fed holding rates = thesis INTACT. HOLD.
- "Above 3.00/3.25% NO" — thesis is rates come down slightly.
  One cut expected in 2026 = thesis INTACT. HOLD.
- Any position showing 70%+ of max profit captured → SELL and redeploy.
"""


class AISignalEngine:
    def __init__(self):
        self.anthropic   = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'), timeout=20.0)
        self.news_api_key = os.getenv('NEWS_API_KEY')
        self.finnhub_key  = os.getenv('FINNHUB_API_KEY', '')
        self.odds_api_key = os.getenv('ODDS_API_KEY', '')
        self.session      = None
        self.live_context = ""

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self.session

    # ── Intelligence fetchers ──────────────────────────────────────────────────

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
                desc  = item.findtext('description', '').strip()[:100]
                date  = item.findtext('pubDate', '')[:16]
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
            url = f"https://news.google.com/rss/search?q={query.replace(' ','+')}&hl=en-US&gl=US&ceid=US:en"
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
            root = ET.fromstring(text)
            items = []
            for item in root.iter('item'):
                title = item.findtext('title', '').strip()
                date  = item.findtext('pubDate', '')[:16]
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
            async with session.get(f"{FINNHUB_BASE}/news",
                                   params={'category': category, 'token': self.finnhub_key}) as resp:
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
        paths = {'nba': 'basketball/nba', 'nhl': 'hockey/nhl', 'mlb': 'baseball/mlb'}
        url = f"{ESPN_BASE}/{paths.get(sport,'basketball/nba')}/injuries"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
            items = []
            for team_data in data.get('injuries', data.get('items', []))[:10]:
                team = team_data.get('team', {}).get('displayName', '')
                for inj in team_data.get('injuries', [])[:3]:
                    athlete = inj.get('athlete', {}).get('displayName', '')
                    status  = inj.get('status', '')
                    detail  = inj.get('details', {})
                    itype   = detail.get('type', '') if isinstance(detail, dict) else ''
                    if athlete and status:
                        items.append(f"[ESPN] {sport.upper()}: {team} — {athlete} {status} {itype}")
            return items
        except Exception as e:
            log.debug(f"ESPN error ({sport}): {e}")
            return []

    async def fetch_sportsbook_odds(self, sport_key: str) -> List[str]:
        if not self.odds_api_key:
            return []
        session = await self._get_session()
        try:
            params = {'apiKey': self.odds_api_key, 'regions': 'us',
                      'markets': 'h2h', 'oddsFormat': 'decimal'}
            async with session.get(f"{ODDS_API_BASE}/sports/{sport_key}/odds",
                                   params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
            items = []
            for game in data[:10]:
                home = game.get('home_team', '')
                away = game.get('away_team', '')
                bms  = game.get('bookmakers', [])
                if not bms:
                    continue
                ho, ao = [], []
                for bm in bms[:3]:
                    for mkt in bm.get('markets', []):
                        if mkt.get('key') == 'h2h':
                            for out in mkt.get('outcomes', []):
                                if out['name'] == home: ho.append(out['price'])
                                elif out['name'] == away: ao.append(out['price'])
                if ho and ao:
                    hp = round(1/(sum(ho)/len(ho))*100, 1)
                    ap = round(1/(sum(ao)/len(ao))*100, 1)
                    items.append(f"[Sportsbook] {away}@{home}: {home} {hp}% | {away} {ap}%")
            return items
        except Exception as e:
            log.debug(f"Odds API error: {e}")
            return []

    async def build_live_context(self) -> str:
        log.info("Building live intelligence from all sources...")
        tasks = []
        for topic in NEWSAPI_TOPICS:
            tasks.append(self.fetch_newsapi(topic))
        for topic in GOOGLE_NEWS_TOPICS:
            tasks.append(self.fetch_google_news(topic))
        for name, url in RSS_FEEDS.items():
            tasks.append(self.fetch_rss(name, url))
        tasks.append(self.fetch_finnhub_news('general'))
        tasks.append(self.fetch_espn_injuries('nba'))
        tasks.append(self.fetch_espn_injuries('nhl'))
        tasks.append(self.fetch_espn_injuries('mlb'))
        if self.odds_api_key:
            tasks.append(self.fetch_sportsbook_odds('basketball_nba'))
            tasks.append(self.fetch_sportsbook_odds('icehockey_nhl'))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_items = []
        for r in results:
            if isinstance(r, list):
                all_items.extend(r)

        seen, unique = set(), []
        for item in all_items:
            key = item[:60]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        log.info(f"Intelligence gathered: {len(unique)} unique items")
        return "\n".join(unique[:60]) if unique else "No live intelligence available."

    # ── Market analyzers ───────────────────────────────────────────────────────

    async def analyze_macro_market(self, market: Dict, live_context: str) -> Optional[Dict]:
        question  = market['question']
        yes_price = market['yes_price']
        ticker    = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)
        end_date  = market.get('end_date', 'unknown')

        prompt = f"""{ECONOMIST_FRAMEWORK}

MARKET: {question}
TICKER: {ticker} | CLOSES: {end_date[:16]} | LIQUIDITY: ${liquidity:.0f}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}

LIVE INTELLIGENCE:
{live_context[:1500]}

STEP 1 — ECONOMIC REALITY CHECK:
What must happen for YES to resolve true?
Does that pass the economic reality constraints above?
If NO → signal=false, reality_check=failed immediately.

STEP 2 — EDGE (only if reality check passed):
Is {yes_price:.2%} mispriced by 5%+? Cite specific data.

STEP 3 — SIGNAL:
Requirements: reality_check=passed + edge>=5% + HIGH confidence.

Respond in JSON only:
{{"true_probability_yes": 0.72, "market_price_yes": {yes_price:.4f}, "edge": 0.08, "direction": "BUY_YES", "confidence": "HIGH", "conviction": "HIGH", "reasoning": "2 sentence economic logic + live data", "key_risk": "main risk", "signal": true, "reality_check": "passed"}}
Failed reality: {{"signal": false, "direction": "SKIP", "reasoning": "Economic reality: reason", "reality_check": "failed"}}
No edge: {{"signal": false, "direction": "SKIP", "reasoning": "no edge", "reality_check": "passed"}}"""

        try:
            resp = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514", max_tokens=400,
                    messages=[{"role": "user", "content": prompt}]
                ), timeout=20
            )
            raw   = resp.content[0].text.strip().replace('```json','').replace('```','').strip()
            start = raw.find('{'); end = raw.rfind('}') + 1
            if start == -1 or end == 0: return None
            data  = json.loads(raw[start:end])

            if data.get('reality_check') == 'failed':
                log.info(f"  ✗ MACRO reality failed: {data.get('reasoning','')[:80]}")
                return None

            edge       = abs(float(data.get('edge', 0) or 0))
            direction  = data.get('direction', 'SKIP')
            signal     = data.get('signal', False)
            confidence = data.get('confidence', 'LOW')
            conviction = data.get('conviction', 'MEDIUM')
            true_prob  = data.get('true_probability_yes')

            if signal and direction != 'SKIP' and edge >= 0.05 and confidence == 'HIGH' and true_prob is not None:
                return {
                    'type': 'ai_signal', 'market': market,
                    'direction': direction, 'true_probability': float(true_prob),
                    'market_price': yes_price, 'edge': edge,
                    'confidence': confidence, 'conviction': conviction,
                    'reasoning': data.get('reasoning',''), 'key_risk': data.get('key_risk',''),
                    'expected_value': edge * min(float(true_prob), 1 - float(true_prob)),
                    'source': 'macro_engine',
                }
        except asyncio.TimeoutError:
            log.warning(f"Timeout macro: '{question[:50]}'")
        except Exception as e:
            log.warning(f"Macro failed '{question[:50]}': {e}")
        return None

    async def analyze_sports_market(self, market: Dict, live_context: str) -> Optional[Dict]:
        question  = market['question']
        yes_price = market['yes_price']
        ticker    = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)
        volume    = market.get('volume', 0)
        end_date  = market.get('end_date', 'unknown')

        if yes_price >= 0.75:
            fav_side, fav_price = 'YES', yes_price
        elif yes_price <= 0.25:
            fav_side, fav_price = 'NO', 1 - yes_price
        else:
            return None

        prompt = f"""{SPORTS_ANALYST_FRAMEWORK}

MARKET: {question}
TICKER: {ticker} | CLOSES: {end_date[:16]}
LIQUIDITY: ${liquidity:.0f} | VOLUME: {volume:.0f}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}
FAVOURITE: {fav_side} at {fav_price:.0%}

LIVE SPORTS INTELLIGENCE (injuries, lineups, sportsbook odds):
{live_context[:1500]}

STEP 1 — INJURY CHECK: Any key players OUT/DOUBTFUL for the favourite?
STEP 2 — VALIDATE: Does {fav_price:.0%} make sense for this matchup?
STEP 3 — SIGNAL: Healthy favourite + valid probability = SIGNAL.

IMPORTANT: A healthy {fav_price:.0%} favourite with no injury news IS a valid signal.
Do not overthink — if no disruptions found, signal=true with appropriate conviction.

Respond in JSON only:
{{"true_probability_yes": {yes_price + 0.04:.4f}, "market_price_yes": {yes_price:.4f}, "edge": 0.05, "direction": "BUY_{fav_side}", "confidence": "HIGH", "conviction": "MEDIUM", "reasoning": "Injury check result + matchup validation", "key_risk": "upset risk", "signal": true}}
Skip only if specific problem found: {{"signal": false, "direction": "SKIP", "reasoning": "specific injury or issue found"}}"""

        try:
            resp = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514", max_tokens=350,
                    messages=[{"role": "user", "content": prompt}]
                ), timeout=20
            )
            raw   = resp.content[0].text.strip().replace('```json','').replace('```','').strip()
            start = raw.find('{'); end = raw.rfind('}') + 1
            if start == -1 or end == 0: return None
            data  = json.loads(raw[start:end])

            edge       = abs(float(data.get('edge', 0) or 0))
            direction  = data.get('direction', 'SKIP')
            signal     = data.get('signal', False)
            confidence = data.get('confidence', 'LOW')
            conviction = data.get('conviction', 'MEDIUM')
            true_prob  = data.get('true_probability_yes')

            if signal and direction != 'SKIP' and edge >= 0.03 and confidence == 'HIGH' and true_prob is not None:
                return {
                    'type': 'ai_signal', 'market': market,
                    'direction': direction, 'true_probability': float(true_prob),
                    'market_price': yes_price, 'edge': edge,
                    'confidence': confidence, 'conviction': conviction,
                    'reasoning': data.get('reasoning',''), 'key_risk': data.get('key_risk',''),
                    'expected_value': edge * min(float(true_prob), 1 - float(true_prob)),
                    'source': 'sports_engine',
                }
        except asyncio.TimeoutError:
            log.warning(f"Timeout sports: '{question[:50]}'")
        except Exception as e:
            log.warning(f"Sports failed '{question[:50]}': {e}")
        return None

    # ── Position Advisor ───────────────────────────────────────────────────────

    async def advise_position(self, ticker: str, side: str, entry_price: float,
                               current_price: float, contracts: float,
                               cost_basis: float, market_type: str,
                               question: str, live_context: str) -> Dict:
        """
        Evaluate an existing position and recommend HOLD or SELL.
        Returns dict with action, reasoning, urgency.
        """
        # Calculate profit metrics
        current_value  = current_price * contracts
        profit_dollars = current_value - cost_basis
        max_profit     = (1.0 - entry_price) * contracts
        profit_pct     = (profit_dollars / max_profit * 100) if max_profit > 0 else 0
        pnl_pct        = (profit_dollars / cost_basis * 100) if cost_basis > 0 else 0

        prompt = f"""{POSITION_ADVISOR_FRAMEWORK}

OPEN POSITION:
Market: {question}
Ticker: {ticker}
Side: {side}
Entry price: {entry_price:.2%} per contract
Current price: {current_price:.2%} per contract
Contracts: {contracts:.0f}
Cost basis: ${cost_basis:.2f}
Current value: ${current_value:.2f}
Unrealized P&L: ${profit_dollars:+.2f} ({pnl_pct:+.1f}% of cost)
% of max profit captured: {profit_pct:.1f}%
Market type: {market_type}

LIVE INTELLIGENCE:
{live_context[:1000]}

Give a clear HOLD or SELL recommendation with reasoning.
Consider: thesis intact? profit captured? better use of capital?

JSON only:
{{"action": "HOLD", "urgency": "low", "reasoning": "2 sentence explanation", "profit_captured_pct": {profit_pct:.1f}}}
or
{{"action": "SELL", "urgency": "high", "reasoning": "2 sentence explanation", "profit_captured_pct": {profit_pct:.1f}}}"""

        try:
            resp = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514", max_tokens=200,
                    messages=[{"role": "user", "content": prompt}]
                ), timeout=15
            )
            raw   = resp.content[0].text.strip().replace('```json','').replace('```','').strip()
            start = raw.find('{'); end = raw.rfind('}') + 1
            if start == -1 or end == 0:
                return {'action': 'HOLD', 'urgency': 'low', 'reasoning': 'Could not analyze'}
            return json.loads(raw[start:end])
        except Exception as e:
            log.debug(f"Position advisor error: {e}")
            return {'action': 'HOLD', 'urgency': 'low', 'reasoning': 'Analysis failed'}

    async def advise_all_positions(self, positions: List[Dict], live_context: str) -> None:
        """
        Run position advisor on all open positions.
        Logs SELL recommendations prominently so they're easy to spot.
        """
        if not positions:
            return

        log.info(f"[POSITION_ADVISOR] Evaluating {len(positions)} open positions...")
        sell_recs = []

        for pos in positions:
            ticker       = pos.get('ticker', '')
            side         = pos.get('side', 'NO')
            entry_price  = pos.get('entry_price', 0.5)
            current_price = pos.get('current_price', 0.5)
            contracts    = pos.get('contracts', 0)
            cost_basis   = pos.get('cost_basis', 0)
            market_type  = pos.get('market_type', 'unknown')
            question     = pos.get('question', ticker)

            if cost_basis <= 0 or contracts <= 0:
                continue

            advice = await self.advise_position(
                ticker, side, entry_price, current_price,
                contracts, cost_basis, market_type, question, live_context
            )

            action   = advice.get('action', 'HOLD')
            urgency  = advice.get('urgency', 'low')
            reasoning = advice.get('reasoning', '')
            profit_pct = advice.get('profit_captured_pct', 0)

            if action == 'SELL':
                sell_recs.append((ticker, urgency, reasoning, profit_pct))
                log.warning(
                    f"[POSITION_ADVISOR] ⚡ SELL RECOMMENDED: {ticker} {side} "
                    f"({profit_pct:.0f}% profit captured) — {reasoning}"
                )
            else:
                log.info(
                    f"[POSITION_ADVISOR] ✓ HOLD: {ticker} {side} "
                    f"({profit_pct:.0f}% profit captured) — {reasoning[:60]}"
                )

        if sell_recs:
            log.warning(
                f"[POSITION_ADVISOR] === {len(sell_recs)} SELL RECOMMENDATION(S) THIS CYCLE ==="
            )
            for ticker, urgency, reasoning, profit_pct in sell_recs:
                log.warning(
                    f"[POSITION_ADVISOR]   → SELL {ticker} "
                    f"urgency={urgency} profit={profit_pct:.0f}% | {reasoning}"
                )
        else:
            log.info("[POSITION_ADVISOR] All positions: HOLD recommended this cycle")

    # ── Main entry point ───────────────────────────────────────────────────────

    async def analyze_markets(self, markets: List[Dict]) -> List[Dict]:
        signals = []

        live_context      = await self.build_live_context()
        self.live_context = live_context

        macro_markets  = [m for m in markets if m.get('market_type') == 'macro']
        sports_markets = [m for m in markets if m.get('market_type') == 'sports']

        # Macro: markets with any trading activity (liquidity OR volume)
        # Sort by liquidity first, then volume — catches newly launched commodity markets
        macro_candidates = [
            m for m in macro_markets
            if 0.05 <= m['yes_price'] <= 0.95
            and (m.get('liquidity', 0) > 0 or m.get('volume', 0) > 100)
        ]
        macro_candidates.sort(
            key=lambda x: (x.get('liquidity', 0) + x.get('volume', 0) * 0.1),
            reverse=True
        )

        # Sports: 75%+ favs, volume > 0, resolves within 20 days
        # Sort by VOLUME desc first (most liquid = best fills), then by favouritism
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

        # Sort: highest volume AND most extreme favourite
        sports_candidates.sort(
            key=lambda x: (x.get('volume', 0) * abs(x['yes_price'] - 0.5)),
            reverse=True
        )

        log.info(
            f"Candidates — Macro: {len(macro_candidates)} (liq>0), "
            f"Sports: {len(sports_candidates)} (75%+ fav, vol>0)"
        )

        # Analyze top 5 macro
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
                log.warning(f"  Timeout macro {market['ticker']}")
            except Exception as e:
                log.warning(f"  Macro error: {e}")

        # Analyze top 8 sports (increased from 5)
        sports_signals = []
        for market in sports_candidates[:8]:
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
                log.warning(f"  Timeout sports {market['ticker']}")
            except Exception as e:
                log.warning(f"  Sports error: {e}")

        signals = macro_signals + sports_signals
        log.info(f"Signals: {len(macro_signals)} macro + {len(sports_signals)} sports")
        return signals

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
