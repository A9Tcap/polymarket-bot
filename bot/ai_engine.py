"""
AI Signal Engine — uses Claude + NewsAPI to analyze markets and generate trade signals
"""

import logging
import os
import json
import aiohttp
from typing import List, Dict
from anthropic import AsyncAnthropic

log = logging.getLogger('ai_engine')

NEWS_API_BASE = "https://newsapi.org/v2"


class AISignalEngine:
    def __init__(self):
        self.anthropic = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.news_api_key = os.getenv('NEWS_API_KEY')
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_relevant_news(self, query: str) -> List[Dict]:
        """Fetch recent news articles relevant to a market question."""
        session = await self._get_session()
        try:
            # Extract key terms from question (first 100 chars)
            search_query = query[:100].split('?')[0]

            params = {
                'q': search_query,
                'sortBy': 'publishedAt',
                'pageSize': 5,
                'language': 'en',
                'apiKey': self.news_api_key,
            }
            async with session.get(f"{NEWS_API_BASE}/everything", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                articles = data.get('articles', [])
                return [
                    {
                        'title': a.get('title', ''),
                        'description': a.get('description', ''),
                        'published': a.get('publishedAt', ''),
                        'source': a.get('source', {}).get('name', ''),
                    }
                    for a in articles[:5]
                ]
        except Exception as e:
            log.warning(f"News fetch error: {e}")
            return []

    async def analyze_single_market(self, market: Dict) -> Dict:
        """Analyze a single market using news + Claude reasoning."""
        question = market['question']
        yes_price = market['yes_price']
        implied_prob = yes_price  # Price = implied probability on Polymarket

        # Fetch relevant news
        news = await self.get_relevant_news(question)
        news_text = "\n".join([
            f"- [{a['source']}] {a['title']}: {a['description']}"
            for a in news
        ]) or "No recent news found."

        prompt = f"""You are a sharp prediction market analyst. Analyze this market and determine if there's a profitable edge.

MARKET: {question}
CURRENT YES PRICE: {yes_price:.2%} (this is the market's implied probability of YES)
LIQUIDITY: ${market['liquidity']:,.0f}
CATEGORY: {market['category']}
END DATE: {market['end_date']}

RECENT NEWS:
{news_text}

Analyze this carefully:
1. What is your estimated TRUE probability of YES based on news and reasoning?
2. Is the market overpriced or underpriced?
3. What is the edge (your probability minus market price)?
4. What trade do you recommend: BUY_YES, BUY_NO, or SKIP?

Respond ONLY with a JSON object like this:
{{
  "true_probability": 0.72,
  "market_price": {yes_price},
  "edge": 0.07,
  "direction": "BUY_YES",
  "confidence": "HIGH",
  "reasoning": "Brief explanation of your analysis",
  "signal": true
}}

Only set signal=true if edge >= 0.04 and confidence is MEDIUM or HIGH.
If you would skip this market, set signal=false and direction=SKIP."""

        try:
            response = await self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            # Strip markdown if present
            raw = raw.replace('```json', '').replace('```', '').strip()
            analysis = json.loads(raw)

            if analysis.get('signal') and analysis.get('direction') != 'SKIP':
                return {
                    'type': 'ai_signal',
                    'market': market,
                    'direction': analysis['direction'],
                    'true_probability': analysis['true_probability'],
                    'market_price': yes_price,
                    'edge': analysis['edge'],
                    'confidence': analysis['confidence'],
                    'reasoning': analysis['reasoning'],
                    'expected_value': analysis['edge'] * analysis.get('true_probability', 0.5),
                    'source': 'ai_engine',
                }
        except Exception as e:
            log.warning(f"AI analysis failed for '{question[:50]}': {e}")

        return None

    async def analyze_markets(self, markets: List[Dict]) -> List[Dict]:
        """Analyze a batch of markets and return trade signals."""
        signals = []

        # Filter to markets in interesting probability range (avoid extremes)
        candidates = [
            m for m in markets
            if 0.10 <= m['yes_price'] <= 0.90
        ]

        log.info(f"Analyzing {len(candidates)} candidate markets with AI...")

        for market in candidates:
            signal = await self.analyze_single_market(market)
            if signal:
                signals.append(signal)
                log.info(
                    f"Signal: {signal['direction']} '{market['question'][:60]}...' "
                    f"edge={signal['edge']:.2%} conf={signal['confidence']}"
                )

        return signals

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
