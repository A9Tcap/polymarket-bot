"""
Expert AI Signal Engine — Dual Strategy Edition
MACRO STRATEGY: Exploit favourite-longshot bias on economics/politics/crypto markets
SPORTS STRATEGY: Bet only on heavy favourites (75%+) for consistent daily returns
"""

import logging
import asyncio
import os
import json
import aiohttp
import xml.etree.ElementTree as ET
from typing import List, Dict
from anthropic import AsyncAnthropic

log = logging.getLogger('ai_engine')

NEWS_API_BASE = "https://newsapi.org/v2"
FINNHUB_BASE = "https://finnhub.io/api/v1"

RSS_FEEDS = {
    'Federal Reserve': 'https://www.federalreserve.gov/feeds/press_all.xml',
    'BLS (Jobs/CPI)': 'https://www.bls.gov/feed/bls_latest.rss',
    'Reuters Business': 'https://feeds.reuters.com/reuters/businessNews',
}

NEWSAPI_TOPICS = [
    'Federal Reserve FOMC April 2026',
    'CPI inflation release April 2026',
    'Trump tariffs trade policy 2026',
    'Bitcoin cryptocurrency market 2026',
    'NBA MLB NHL sports results today',
]

GOOGLE_NEWS_TOPICS = [
    'Federal Reserve interest rate April 2026',
    'CPI inflation data release 2026',
    'NBA game results injuries today 2026',
    'MLB baseball today 2026',
    'Bitcoin price today',
]


class AISignalEngine:
    def __init__(self):
        self.anthropic = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.news_api_key = os.getenv('NEWS_API_KEY')
        self.finnhub_key = os.getenv('FINNHUB_API_KEY', '')
        self.session = None
        self.live_context = ""

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self.session

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

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_items = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)

        seen = set()
        unique_items = []
        for item in all_items:
            key = item[:50]
            if key not in seen:
                seen.add(key)
                unique_items.append(item)

        log.info(f"Intelligence gathered: {len(unique_items)} unique items")
        return "\n".join(unique_items[:40]) if unique_items else "No live intelligence available."

    async def analyze_macro_market(self, market: Dict, live_context: str) -> Dict:
        """Analyze economics/politics/crypto market using favourite-longshot bias strategy."""
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)

        prompt = f"""You are a top prediction market analyst exploiting Kalshi's favourite-longshot bias.

PROVEN EDGE: Research on 300,000+ Kalshi contracts shows high-probability contracts (70-90%) are systematically underpriced. Buy YES at 70-90% to exploit this. Buy NO when YES is 10-30% to fade overpriced longshots.

MARKET: {question}
TICKER: {ticker} | RESOLUTION: {end_date} | LIQUIDITY: ${liquidity:,.0f}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}

LIVE INTELLIGENCE:
{live_context[:1500]}

MACRO CONTEXT (April 2026):
- Fed held at 3.50-3.75%. Next FOMC April 28-29. Rate cut very unlikely.
- Supreme Court struck down IEEPA tariffs Feb 2026. Inflation still ~2.5%.
- Jobs report April 4. CPI release ~April 10.
- Bitcoin ~$75-77k range.

Analyze and respond with JSON only:
{{"true_probability_yes": 0.85, "market_price_yes": {yes_price:.4f}, "edge": 0.08, "direction": "BUY_YES", "confidence": "HIGH", "reasoning": "2 sentences with specific data", "key_risk": "main risk", "signal": true}}

Only signal if edge >= 5%, confidence HIGH, specific live data supports view. Otherwise: {{"signal": false, "direction": "SKIP", "reasoning": "no edge"}}"""

        try:
            response = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}]
                ),
                timeout=25
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

    async def analyze_sports_market(self, market: Dict, live_context: str) -> Dict:
        """
        Sports strategy: Only bet heavy favourites (75%+).
        Use live news to confirm no injuries, suspensions, or surprises.
        """
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)

        # Only analyze if one side is a heavy favourite
        if yes_price < 0.72 and (1 - yes_price) < 0.72:
            return None  # No clear favourite, skip

        prompt = f"""You are a sports prediction market analyst. Your strategy: BET ONLY ON HEAVY FAVOURITES (75%+).

Research proves heavy favourites on Kalshi are systematically underpriced — they win MORE often than their price implies.

MARKET: {question}
TICKER: {ticker} | RESOLUTION: {end_date} | LIQUIDITY: ${liquidity:,.0f}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}

LIVE SPORTS INTELLIGENCE:
{live_context[:1000]}

YOUR TASK:
1. Who is the heavy favourite here?
2. Does live intelligence show any injuries, roster changes, or surprises that would affect the favourite?
3. Is the favourite at 75%+ YES or NO price? That is your bet direction.
4. Only signal if you can CONFIRM the favourite is still strong with no major disruptions.

Signal requirements:
- Favourite must be priced 75% or higher
- No major injuries or disruptions to favourite from live news
- Market has liquidity > 0
- Game resolves today or tomorrow

Respond with JSON only:
{{"true_probability_yes": 0.82, "market_price_yes": {yes_price:.4f}, "edge": 0.05, "direction": "BUY_YES", "confidence": "HIGH", "reasoning": "Team X is 75% favourite, no injury news found, playing at home", "key_risk": "upset risk", "signal": true}}

If not a clear high-confidence favourite bet: {{"signal": false, "direction": "SKIP", "reasoning": "brief"}}"""

        try:
            response = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}]
                ),
                timeout=25
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
            true_prob_raw = analysis.get('true_probability_yes')

            if signal and direction != 'SKIP' and edge >= 0.04 and confidence == 'HIGH' and true_prob_raw is not None:
                true_prob = float(true_prob_raw)
                return {
                    'type': 'ai_signal',
                    'market': market,
                    'direction': direction,
                    'true_probability': true_prob,
                    'market_price': yes_price,
                    'edge': edge,
                    'confidence': confidence,
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

        # Build live context once
        live_context = await self.build_live_context()
        self.live_context = live_context

        # Split markets by type
        macro_markets = [m for m in markets if m.get('market_type') == 'macro']
        sports_markets = [m for m in markets if m.get('market_type') == 'sports']

        # Sort macro by liquidity
        macro_candidates = [m for m in macro_markets if 0.08 <= m["yes_price"] <= 0.92 and m.get("liquidity", 0) > 0]
        macro_candidates.sort(key=lambda x: x.get('liquidity', 0), reverse=True)

        # Sort sports by how extreme the favourite is (furthest from 0.5)
        sports_candidates = [
            m for m in sports_markets
            if m.get('liquidity', 0) > 0 and (m['yes_price'] >= 0.72 or m['yes_price'] <= 0.28)
        ]
        sports_candidates.sort(key=lambda x: abs(x['yes_price'] - 0.5), reverse=True)

        log.info(f"Sports candidates (75%+ fav): {len(sports_candidates)}, Macro candidates (liq>0): {len(macro_candidates)}")
        for m in sports_candidates[:3]:
            log.info(f"  Top sports: {m["ticker"]} yes={m["yes_price"]:.0%} liq={m.get("liquidity",0)}")
        log.info(f"Analyzing up to 5 macro + up to 5 sports markets...")

        # Analyze top 5 macro markets
        macro_signals = []
        for market in macro_candidates[:5]:
            log.info(f"  Macro: [{market['ticker']}] {market['question'][:55]} (liq={market.get('liquidity',0):.0f})")
            signal = await self.analyze_macro_market(market, live_context)
            if signal:
                macro_signals.append(signal)
                log.info(f"  ✓ MACRO Signal: {signal['direction']} edge={signal['edge']:.2%} | {signal['reasoning'][:70]}")

        # Analyze top 5 sports markets (heavy favourites only)
        sports_signals = []
        for market in sports_candidates[:5]:
            log.info(f"  Sports: [{market['ticker']}] {market['question'][:55]} (liq={market.get('liquidity',0):.0f}, yes={market['yes_price']:.0%})")
            signal = await self.analyze_sports_market(market, live_context)
            if signal:
                sports_signals.append(signal)
                log.info(f"  ✓ SPORTS Signal: {signal['direction']} edge={signal['edge']:.2%} | {signal['reasoning'][:70]}")

        signals = macro_signals + sports_signals
        log.info(f"Total signals: {len(macro_signals)} macro + {len(sports_signals)} sports")
        return signals

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
