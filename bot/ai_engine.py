"""
Expert AI Signal Engine — Maximum Intelligence Edition
Pulls from NewsAPI, Google News RSS, Federal Reserve RSS, BLS RSS, and Finnhub
for the most comprehensive real-time market intelligence available for free.
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

# RSS feeds for authoritative real-time data
RSS_FEEDS = {
    'Federal Reserve': 'https://www.federalreserve.gov/feeds/press_all.xml',
    'BLS (Jobs/CPI)': 'https://www.bls.gov/feed/bls_latest.rss',
    'Reuters Business': 'https://feeds.reuters.com/reuters/businessNews',
    'AP Economics': 'https://rsshub.app/apnews/topics/economy',
}

# Google News search topics
GOOGLE_NEWS_TOPICS = [
    'Federal Reserve interest rate 2026',
    'CPI inflation data April 2026',
    'Trump tariffs China announcement',
    'Bitcoin price prediction',
    'US recession economy 2026',
]

# NewsAPI topics
NEWSAPI_TOPICS = [
    'Federal Reserve FOMC April 2026',
    'CPI inflation release April 2026',
    'Trump tariffs trade war 2026',
    'Bitcoin cryptocurrency 2026',
    'Iran US oil geopolitical 2026',
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
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self.session

    async def fetch_newsapi(self, query: str) -> List[str]:
        """Fetch from NewsAPI."""
        session = await self._get_session()
        try:
            params = {
                'q': query,
                'sortBy': 'publishedAt',
                'pageSize': 3,
                'language': 'en',
                'apiKey': self.news_api_key,
            }
            async with session.get(f"{NEWS_API_BASE}/everything", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                results = []
                for a in data.get('articles', [])[:3]:
                    if a.get('title'):
                        results.append(f"[{a.get('source',{}).get('name','')} | {a.get('publishedAt','')[:10]}] {a['title']}: {(a.get('description') or '')[:120]}")
                return results
        except Exception as e:
            log.debug(f"NewsAPI error: {e}")
            return []

    async def fetch_rss(self, name: str, url: str) -> List[str]:
        """Fetch and parse an RSS feed."""
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
        except Exception as e:
            log.debug(f"RSS error for {name}: {e}")
            return []

    async def fetch_google_news(self, query: str) -> List[str]:
        """Fetch from Google News RSS."""
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
        except Exception as e:
            log.debug(f"Google News error: {e}")
            return []

    async def fetch_finnhub_news(self, category: str = 'general') -> List[str]:
        """Fetch from Finnhub financial news."""
        if not self.finnhub_key:
            return []
        session = await self._get_session()
        try:
            url = f"{FINNHUB_BASE}/news"
            params = {'category': category, 'token': self.finnhub_key}
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
            items = []
            for article in data[:5]:
                headline = article.get('headline', '')
                summary = article.get('summary', '')[:100]
                source = article.get('source', '')
                if headline:
                    items.append(f"[{source} | Finnhub] {headline}: {summary}")
            return items
        except Exception as e:
            log.debug(f"Finnhub error: {e}")
            return []

    async def build_live_context(self) -> str:
        """Build comprehensive intelligence briefing from all sources."""
        log.info("Building live intelligence from all sources...")
        all_items = []

        # Run all fetches concurrently
        tasks = []

        # NewsAPI
        for topic in NEWSAPI_TOPICS[:3]:
            tasks.append(('NewsAPI', self.fetch_newsapi(topic)))

        # Google News
        for topic in GOOGLE_NEWS_TOPICS[:3]:
            tasks.append(('Google', self.fetch_google_news(topic)))

        # RSS feeds
        for name, url in RSS_FEEDS.items():
            tasks.append((name, self.fetch_rss(name, url)))

        # Finnhub
        tasks.append(('Finnhub', self.fetch_finnhub_news('general')))
        tasks.append(('Finnhub Crypto', self.fetch_finnhub_news('crypto')))

        # Execute concurrently with timeout
        results = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True
        )

        source_counts = {}
        for i, result in enumerate(results):
            source = tasks[i][0]
            if isinstance(result, list) and result:
                all_items.extend(result)
                source_counts[source] = source_counts.get(source, 0) + len(result)

        log.info(f"Intelligence gathered: {len(all_items)} items from {source_counts}")

        if not all_items:
            return "No live intelligence available this cycle."

        # Deduplicate and format
        seen = set()
        unique_items = []
        for item in all_items:
            key = item[:50]
            if key not in seen:
                seen.add(key)
                unique_items.append(item)

        return "\n".join(unique_items[:40])  # Top 40 unique items

    async def analyze_single_market(self, market: Dict, live_context: str) -> Dict:
        """Deep expert analysis using comprehensive live intelligence."""
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')

        prompt = f"""You are the world's most sophisticated prediction market analyst with access to comprehensive real-time intelligence from multiple premium sources.

MARKET: {question}
TICKER: {ticker}
RESOLUTION DATE: {end_date}
YES PRICE: {yes_price:.2%} | NO PRICE: {1-yes_price:.2%}

LIVE INTELLIGENCE (from NewsAPI + Google News + Federal Reserve RSS + BLS RSS + Reuters + Finnhub):
{live_context[:2000]}

STANDING MACRO CONTEXT:
- Fed held at 3.50-3.75% on March 18. Next FOMC: April 28-29, 2026.
- Inflation ~2.4-2.7% YoY, above 2% target. Tariffs + Iran war = upside risk.
- One rate cut expected all of 2026. Fed is patient and data-dependent.
- Trump tariffs on China/EU creating significant trade uncertainty.
- Bitcoin elevated but volatile. Crypto markets risk-on.
- Today is March 31, 2026.

ANALYSIS REQUIREMENTS:
1. What exactly resolves this market YES?
2. What specific items from the live intelligence above are relevant?
3. Calculate your true probability estimate with reasoning
4. Is {yes_price:.2%} fair? If not, what's your edge?

Only signal if edge >= 6% AND you can cite specific live intelligence supporting your view.
SKIP if no genuine edge — most markets are efficiently priced.

Respond ONLY with valid JSON:
{{
  "true_probability_yes": 0.72,
  "market_price_yes": {yes_price:.4f},
  "edge": 0.09,
  "direction": "BUY_YES",
  "confidence": "HIGH",
  "reasoning": "2 sentences citing specific data from live intelligence",
  "key_risk": "Main risk",
  "signal": true
}}"""

        try:
            response = await asyncio.wait_for(
                self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=350,
                    messages=[{"role": "user", "content": prompt}]
                ),
                timeout=25
            )
            raw = response.content[0].text.strip()
            raw = raw.replace('```json', '').replace('```', '').strip()
            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start == -1 or end == 0:
                return None
            analysis = json.loads(raw[start:end])

            edge = abs(float(analysis.get("edge", 0) or 0))
            direction = analysis.get('direction', 'SKIP')
            signal = analysis.get('signal', False)
            confidence = analysis.get('confidence', 'LOW')

            if signal and direction != 'SKIP' and edge >= 0.06 and confidence == 'HIGH':
                true_prob_raw = analysis.get("true_probability_yes")
                true_prob = float(true_prob_raw) if true_prob_raw is not None else yes_price
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
                    'source': 'ai_engine',
                }

        except asyncio.TimeoutError:
            log.warning(f"Timed out analyzing '{question[:50]}'")
        except Exception as e:
            log.warning(f"Analysis failed for '{question[:50]}': {e}")

        return None

    async def analyze_markets(self, markets: List[Dict]) -> List[Dict]:
        """Analyze markets with maximum intelligence."""
        signals = []

        # Build comprehensive live context once per cycle
        live_context = await self.build_live_context()
        self.live_context = live_context

        candidates = [m for m in markets if 0.08 <= m['yes_price'] <= 0.92]
        analyze_count = min(len(candidates), 5)

        log.info(f"Analyzing {analyze_count} markets with live multi-source intelligence...")

        for market in candidates[:analyze_count]:
            signal = await self.analyze_single_market(market, live_context)
            if signal:
                signals.append(signal)
                log.info(
                    f"Signal: {signal['direction']} '{market['question'][:55]}' "
                    f"edge={signal['edge']:.2%} | {signal['reasoning'][:80]}"
                )

        return signals

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
