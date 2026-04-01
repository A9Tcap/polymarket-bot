"""
Expert AI Signal Engine — Maximum Intelligence Edition
Pulls from NewsAPI, Google News RSS, Federal Reserve RSS, BLS RSS, and Finnhub.
Analyzes top liquidity markets first for best edge.
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
    'Trump tariffs trade war 2026',
    'Bitcoin cryptocurrency 2026',
    'Iran US oil geopolitical 2026',
]

GOOGLE_NEWS_TOPICS = [
    'Federal Reserve interest rate 2026',
    'CPI inflation data April 2026',
    'Trump tariffs China announcement',
    'Bitcoin price prediction',
    'US recession economy 2026',
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
                        results.append(
                            f"[{a.get('source',{}).get('name','')} | {a.get('publishedAt','')[:10]}] "
                            f"{a['title']}: {(a.get('description') or '')[:120]}"
                        )
                return results
        except Exception as e:
            log.debug(f"NewsAPI error: {e}")
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
        except Exception as e:
            log.debug(f"RSS error for {name}: {e}")
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
        except Exception as e:
            log.debug(f"Google News error: {e}")
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

    async def analyze_single_market(self, market: Dict, live_context: str) -> Dict:
        question = market['question']
        yes_price = market['yes_price']
        end_date = market.get('end_date', 'unknown')
        ticker = market.get('ticker', '')
        liquidity = market.get('liquidity', 0)

        prompt = f"""You are the world's most sophisticated prediction market analyst with access to comprehensive real-time intelligence.

MARKET: {question}
TICKER: {ticker}
RESOLUTION DATE: {end_date}
YES PRICE: {yes_price:.2%} | NO PRICE: {1-yes_price:.2%}
LIQUIDITY: ${liquidity:,.0f}

LIVE INTELLIGENCE (NewsAPI + Google News + Federal Reserve + BLS + Reuters + Finnhub):
{live_context[:2000]}

STANDING MACRO CONTEXT (March 31, 2026):
- Fed held at 3.50-3.75% on March 18. Next FOMC: April 28-29, 2026.
- Inflation ~2.4-2.7% YoY, above 2% target. Tariffs + Iran war = upside risk.
- One rate cut expected all of 2026. Fed is patient and data-dependent.
- Supreme Court struck down Trump IEEPA tariffs in Feb 2026 as unconstitutional. Refunds being processed.
- Tariff impact still felt — consumer goods up ~2%, inflation sticky above 2% target.
- Trump may pursue new tariff legislation through Congress.
- Bitcoin elevated but volatile. Crypto markets risk-on.

YOUR TASK:
1. What exactly resolves this market YES?
2. What specific live intelligence items are relevant to this market?
3. What is your true probability estimate and why?
4. Is {yes_price:.2%} fair? What is your edge?

Only signal if:
- Edge >= 6% (abs difference between your probability and market price)
- HIGH confidence only
- You can cite specific live intelligence supporting your view
- Market has real significance (not a trivial or already-expired market)

Respond ONLY with valid JSON:
{{
  "true_probability_yes": 0.72,
  "market_price_yes": {yes_price:.4f},
  "edge": 0.09,
  "direction": "BUY_YES",
  "confidence": "HIGH",
  "reasoning": "2 sentences citing specific data from live intelligence",
  "key_risk": "Main risk to this view",
  "signal": true
}}

If no genuine edge: {{"signal": false, "direction": "SKIP", "reasoning": "brief explanation"}}"""

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

            edge = abs(float(analysis.get('edge', 0) or 0))
            direction = analysis.get('direction', 'SKIP')
            signal = analysis.get('signal', False)
            confidence = analysis.get('confidence', 'LOW')
            true_prob_raw = analysis.get('true_probability_yes')

            if signal and direction != 'SKIP' and edge >= 0.06 and confidence == 'HIGH' and true_prob_raw is not None:
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
                    'source': 'ai_engine',
                }

        except asyncio.TimeoutError:
            log.warning(f"Timed out analyzing '{question[:50]}'")
        except Exception as e:
            log.warning(f"Analysis failed for '{question[:50]}': {e}")

        return None

    async def analyze_markets(self, markets: List[Dict]) -> List[Dict]:
        signals = []

        # Build live context once per cycle
        live_context = await self.build_live_context()
        self.live_context = live_context

        # Sort by liquidity descending — analyze best markets first
        candidates = [m for m in markets if 0.08 <= m['yes_price'] <= 0.92]
        candidates.sort(key=lambda x: x.get('liquidity', 0), reverse=True)

        analyze_count = min(len(candidates), 5)
        log.info(f"Analyzing top {analyze_count} markets by liquidity...")

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
