"""
Expert AI Signal Engine — Dual Strategy Edition
MACRO: Exploit favourite-longshot bias on economics/politics/crypto
SPORTS: Bet only heavy favourites (75%+) for consistent daily returns

Uses correct Kalshi field names:
- volume_fp -> parsed as 'volume'
- liquidity_dollars -> parsed as 'liquidity'  
- close_time -> parsed as 'end_date'
"""

import logging
import asyncio
import os
import json
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
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
    'NBA MLB NHL games today results',
    'Bitcoin cryptocurrency market 2026',
]

GOOGLE_NEWS_TOPICS = [
    'Federal Reserve interest rate April 2026',
    'NBA game tonight injury report 2026',
    'MLB baseball today starting pitcher 2026',
    'Bitcoin price today April 2026',
    'US jobs report nonfarm payrolls 2026',
]


class AISignalEngine:
    def __init__(self):
        self.anthropic = AsyncAnthropic(
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            timeout=20.0
        )
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

    def resolves_soon(self, market: Dict, hours: int = 36) -> bool:
        """Check if market resolves within given hours."""
        end = market.get('end_date', '')
        if not end:
            return True
        try:
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            return now <= end_dt <= now + timedelta(hours=hours)
        except:
            return True

    async def analyze_macro_market(self, market: Dict, live_context: str) -> Dict:
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)
        volume = market.get('volume', 0)

        prompt = f"""You are a top prediction market analyst exploiting Kalshi's favourite-longshot bias.

PROVEN EDGE: Research on 300,000+ Kalshi contracts shows:
- High-probability contracts (70-90% YES) are systematically UNDERPRICED → BUY YES
- Low-probability contracts (10-30% YES) are systematically OVERPRICED → BUY NO

MARKET: {question}
TICKER: {ticker} | CLOSES: {end_date[:16]} | LIQUIDITY: ${liquidity:.0f} | VOLUME: {volume:.0f}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}

LIVE INTELLIGENCE:
{live_context[:1500]}

MACRO CONTEXT (April 2026):
- Fed held at 3.50-3.75%. Next FOMC April 28-29. Rate cut very unlikely.
- Supreme Court struck down IEEPA tariffs Feb 2026. Inflation still ~2.5%.
- Jobs report April 4. CPI release ~April 10.
- Bitcoin ~$75-77k range.

Signal requirements: edge >= 5%, HIGH confidence, cite specific live data.

JSON only: {{"true_probability_yes": 0.85, "market_price_yes": {yes_price:.4f}, "edge": 0.08, "direction": "BUY_YES", "confidence": "HIGH", "reasoning": "2 sentences with specific data", "key_risk": "main risk", "signal": true}}
No edge: {{"signal": false, "direction": "SKIP", "reasoning": "brief"}}"""

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
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)
        volume = market.get('volume', 0)

        # Determine favourite side and price
        if yes_price >= 0.75:
            fav_side = 'YES'
            fav_price = yes_price
        elif yes_price <= 0.25:
            fav_side = 'NO'
            fav_price = 1 - yes_price
        else:
            return None  # No clear favourite

        prompt = f"""You are a sports prediction market analyst. Strategy: BET ONLY HEAVY FAVOURITES (75%+).

Research proves heavy favourites on Kalshi win MORE often than their price implies (favourite-longshot bias).

MARKET: {question}
TICKER: {ticker} | CLOSES: {end_date[:16]}
YES: {yes_price:.2%} | NO: {1-yes_price:.2%}
LIQUIDITY: ${liquidity:.0f} | VOLUME: {volume:.0f}
FAVOURITE: {fav_side} at {fav_price:.0%}

LIVE SPORTS INTELLIGENCE:
{live_context[:1000]}

YOUR TASK:
1. Identify the heavy favourite team/player
2. Check live intelligence for injury news, roster changes, or surprises
3. Confirm no major disruptions to the favourite
4. Only signal BUY_{fav_side} — do not recommend the underdog

DECISION RULES:
- Favourite is already confirmed at {fav_price:.0%} ✓
- DEFAULT TO SIGNAL unless you find SPECIFIC bad news (key injury, suspension, weather cancellation)
- No news = good news = BUY the favourite
- Volume confirms real market activity ✓

JSON only (always signal unless specific bad news found):
{{"true_probability_yes": {yes_price:.4f}, "market_price_yes": {yes_price:.4f}, "edge": 0.05, "direction": "BUY_{fav_side}", "confidence": "HIGH", "reasoning": "Heavy favourite at {fav_price:.0%}, no disruptions found in live intelligence", "key_risk": "standard upset risk", "signal": true}}
Only skip if SPECIFIC injury/cancellation news: {{"signal": false, "direction": "SKIP", "reasoning": "specific reason"}}"""

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

        # Split by type
        macro_markets = [m for m in markets if m.get('market_type') == 'macro']
        sports_markets = [m for m in markets if m.get('market_type') == 'sports']

        # MACRO: sort by liquidity desc, skip zero-liquidity
        macro_candidates = [
            m for m in macro_markets
            if 0.08 <= m['yes_price'] <= 0.92
            and m.get('liquidity', 0) > 0
        ]
        macro_candidates.sort(key=lambda x: x.get('liquidity', 0), reverse=True)

        # SPORTS: heavy favourites (75%+), resolving within 36h, with volume
        now = datetime.now(timezone.utc)
        sports_candidates = []
        for m in sports_markets:
            # Must be a clear favourite (75%+)
            if not (m['yes_price'] >= 0.75 or m['yes_price'] <= 0.25):
                continue
            # Must have some trading activity
            if not (m.get('volume', 0) > 0 or m.get('liquidity', 0) > 0):
                continue
            # Must resolve within 20 days (covers series/playoff markets)
            end = m.get('end_date', '')
            if end:
                try:
                    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                    if not (now <= end_dt <= now + timedelta(days=20)):
                        continue
                except:
                    pass
            sports_candidates.append(m)

        # Sort sports by how extreme the favourite is
        sports_candidates.sort(key=lambda x: abs(x['yes_price'] - 0.5), reverse=True)

        # Deduplicate — keep only the favourite side of each game
        # (e.g. HOU at 94% and MIL at 6% are the same bet — just keep HOU)
        seen_events = set()
        deduped = []
        for m in sports_candidates:
            # Extract event key from ticker (e.g. KXNBAGAME-26APR01MILHOU)
            parts = m['ticker'].rsplit('-', 1)
            event_key = parts[0] if len(parts) > 1 else m['ticker']
            if event_key not in seen_events:
                seen_events.add(event_key)
                deduped.append(m)
        sports_candidates = deduped

        log.info(f"Candidates — Macro: {len(macro_candidates)} (liq>0), Sports: {len(sports_candidates)} (75%+ fav, 36h, vol>0)")

        # Analyze top 5 macro — with hard per-market timeout
        macro_signals = []
        for market in macro_candidates[:5]:
            log.info(f"  Macro: [{market['ticker']}] {market['question'][:50]} (liq=${market.get('liquidity',0):.0f})")
            try:
                signal = await asyncio.wait_for(
                    self.analyze_macro_market(market, live_context),
                    timeout=20
                )
                if signal:
                    macro_signals.append(signal)
                    log.info(f"  ✓ MACRO: {signal['direction']} edge={signal['edge']:.2%} | {signal['reasoning'][:70]}")
            except asyncio.TimeoutError:
                log.warning(f"  Hard timeout on macro market {market['ticker']}, skipping")
            except Exception as e:
                log.warning(f"  Error analyzing macro market: {e}")

        # Analyze top 5 sports — with hard per-market timeout
        sports_signals = []
        for market in sports_candidates[:5]:
            log.info(f"  Sports: [{market['ticker']}] {market['question'][:50]} yes={market['yes_price']:.0%} vol={market.get('volume',0):.0f}")
            try:
                signal = await asyncio.wait_for(
                    self.analyze_sports_market(market, live_context),
                    timeout=20
                )
                if signal:
                    sports_signals.append(signal)
                    log.info(f"  ✓ SPORTS: {signal['direction']} edge={signal['edge']:.2%} | {signal['reasoning'][:70]}")
            except asyncio.TimeoutError:
                log.warning(f"  Hard timeout on sports market {market['ticker']}, skipping")
            except Exception as e:
                log.warning(f"  Error analyzing sports market: {e}")

        signals = macro_signals + sports_signals
        log.info(f"Signals: {len(macro_signals)} macro + {len(sports_signals)} sports")
        return signals

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
