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
        session = await self._get_session()
        try:
            search_query = query[:80].split('?')[0]
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
        question = market['question']
        yes_price = market['yes_price']

        news = await self.get_relevant_news(question)
        news_text = "\n".join([
            f"- [{a['source']}] {a['title']}: {a['description']}"
            for a in news
        ]) or "No recent news found."

        prompt = f"""You are a sharp prediction market analyst. Analyze this market carefully.

MARKET: {question}
CURRENT YES PRICE: {yes_price:.2%} (market's implied probability that YES wins)
CURRENT NO PRICE: {1-yes_price:.2%} (market's implied probability that NO wins)
CATEGORY: {market['category']}
END DATE: {market['end_date']}

RECENT NEWS:
{news_text}

Your job:
1. Estimate the TRUE probability of YES resolving based on all available info
2. Compare to the market price to find edge
3. Edge = abs(your_probability - market_price) — always a POSITIVE number
4. Recommend BUY_YES if you think YES is underpriced, BUY_NO if YES is overpriced, SKIP if no edge

Rules:
- Only recommend a trade if edge >= 0.04 (4%) and you have MEDIUM or HIGH confidence
- Edge must always be a positive number (0.04 to 0.50 range)
- Be realistic — most markets are fairly priced, SKIP is often correct

Respond ONLY with valid JSON, no markdown, no explanation outside the JSON:
{{
  "true_probability_yes": 0.65,
  "market_price_yes": {yes_price:.4f},
  "edge": 0.08,
  "direction": "BUY_YES",
  "confidence": "HIGH",
  "reasoning": "One sentence explanation",
  "signal": true
}}

Set signal=true only if edge >= 0.04 and direction is not SKIP."""

        try:
            response = await self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = raw.replace('```json', '').replace('```', '').strip()

            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start == -1 or end == 0:
                return None
            raw = raw[start:end]

            analysis = json.loads(raw)

            edge = abs(float(analysis.get('edge', 0)))
            direction = analysis.get('direction', 'SKIP')
            signal = analysis.get('signal', False)
            confidence = analysis.get('confidence', 'LOW')

            if signal and direction != 'SKIP' and edge >= 0.04 and confidence in ('MEDIUM', 'HIGH'):
                true_prob = float(analysis.get('true_probability_yes', yes_price))
                return {
                    'type': 'ai_signal',
                    'market': market,
                    'direction': direction,
                    'true_probability': true_prob,
                    'market_price': yes_price,
                    'edge': edge,
                    'confidence': confidence,
                    'reasoning': analysis.get('reasoning', ''),
                    'expected_value': edge * min(true_prob, 1 - true_prob),
                    'source': 'ai_engine',
                }

        except Exception as e:
            log.warning(f"AI analysis failed for '{question[:50]}': {e}")

        return None

    async def analyze_markets(self, markets: List[Dict]) -> List[Dict]:
        signals = []

        candidates = [
            m for m in markets
            if 0.08 <= m['yes_price'] <= 0.92
        ]

        log.info(f"Analyzing {len(candidates)} candidate markets with AI...")

        for market in candidates:
            signal = await self.analyze_single_market(market)
            if signal:
                signals.append(signal)
                log.info(
                    f"Signal: {signal['direction']} '{market['question'][:55]}' "
                    f"edge={signal['edge']:.2%} conf={signal['confidence']}"
                )

        return signals

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
