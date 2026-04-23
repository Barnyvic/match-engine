from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import Any

import requests
from groq import Groq

from app.config import get_runtime_setting


RSS_QUERIES = [
    "https://news.google.com/rss/search?q={query}",
    "https://news.google.com/rss/search?q={query}+football",
]


def parse_rss_items(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items: list[dict[str, str]] = []
    for item in root.findall(".//item")[:5]:
        items.append(
            {
                "title": item.findtext("title", default="").strip(),
                "link": item.findtext("link", default="").strip(),
                "pub_date": item.findtext("pubDate", default="").strip(),
                "description": item.findtext("description", default="").strip(),
            }
        )
    return items


@lru_cache(maxsize=256)
def fetch_team_news(team_name: str) -> list[dict[str, str]]:
    articles: list[dict[str, str]] = []
    for template in RSS_QUERIES:
        query = requests.utils.quote(team_name)
        try:
            response = requests.get(template.format(query=query), timeout=15, headers={"User-Agent": "match-engine/1.0"})
            if response.ok:
                articles.extend(parse_rss_items(response.text))
        except (requests.RequestException, ET.ParseError):
            continue
        if len(articles) >= 5:
            break
    return articles[:5]


def fallback_context(home_team: str, away_team: str, home_news: list[dict[str, str]], away_news: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "context_score": 0,
        "summary": f"No Groq key configured, so contextual adjustment is neutral for {home_team} vs {away_team}.",
        "home_team_news_count": len(home_news),
        "away_team_news_count": len(away_news),
        "confidence": "low",
        "drivers": ["Fallback neutral context used because GROQ_API_KEY is missing."],
    }


def groq_context_adjustment(home_team: str, away_team: str) -> dict[str, Any]:
    home_news = fetch_team_news(home_team)
    away_news = fetch_team_news(away_team)
    groq_api_key = get_runtime_setting("GROQ_API_KEY")
    if not groq_api_key or groq_api_key == "your_groq_key_here":
        return fallback_context(home_team, away_team, home_news, away_news)

    try:
        client = Groq(api_key=groq_api_key)
        prompt = {
            "fixture": {"home_team": home_team, "away_team": away_team},
            "home_news": home_news,
            "away_news": away_news,
            "task": (
                "Return compact JSON with keys context_score, confidence, summary, drivers. "
                "context_score must be an integer from -3 to 3 where positive helps the home team and negative helps the away team."
            ),
        }
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            messages=[
                {
                    "role": "system",
                    "content": "You are a football betting context analyst. Use only the supplied news snippets and return valid JSON.",
                },
                {"role": "user", "content": json.dumps(prompt)},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        parsed["home_team_news_count"] = len(home_news)
        parsed["away_team_news_count"] = len(away_news)
        parsed.setdefault("context_score", 0)
        parsed.setdefault("confidence", "low")
        parsed.setdefault("summary", f"Neutral contextual output for {home_team} vs {away_team}.")
        parsed.setdefault("drivers", [])
        return parsed
    except Exception:
        return fallback_context(home_team, away_team, home_news, away_news)
