from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import requests

from app.config import get_runtime_setting
from app.pipeline.llm_layer import fallback_context, fetch_team_news, groq_context_adjustment


class ContextProvider(Protocol):
    def get_context_adjustment(self, home_team: str, away_team: str) -> dict[str, Any]:
        ...


@dataclass
class GroqNewsContextProvider:
    def get_context_adjustment(self, home_team: str, away_team: str) -> dict[str, Any]:
        return groq_context_adjustment(home_team, away_team)


@dataclass
class McpContextProvider:
    server_url: str | None = (get_runtime_setting("MCP_SERVER_URL") or "").strip() or None
    tool_name: str = (get_runtime_setting("MCP_TOOL_NAME", "findEventsAndMarketsByCompetition") or "findEventsAndMarketsByCompetition").strip()
    timeout_seconds: int = int(get_runtime_setting("MCP_TIMEOUT_SECONDS", "15") or "15")

    def _map_prob_gap_to_context_score(self, home_prob: float, away_prob: float) -> int:
        gap = home_prob - away_prob
        if gap >= 0.25:
            return 3
        if gap >= 0.15:
            return 2
        if gap >= 0.06:
            return 1
        if gap <= -0.25:
            return -3
        if gap <= -0.15:
            return -2
        if gap <= -0.06:
            return -1
        return 0

    def _extract_match_odds_probs(self, tool_result: dict[str, Any]) -> dict[str, float] | None:
        structured = tool_result.get("structuredContent")
        if not isinstance(structured, list):
            return None
        for event in structured:
            markets = event.get("markets", {})
            match_odds = markets.get("soccer.match_odds", {})
            submarkets = match_odds.get("submarkets", {})
            full_time = submarkets.get("period=ft", {})
            selections = full_time.get("selections", [])
            prices: dict[str, float] = {}
            for selection in selections:
                outcome = str(selection.get("Outcome", "")).strip().lower()
                price = selection.get("Price")
                if outcome in {"home", "draw", "away"} and isinstance(price, (int, float)) and price > 1:
                    prices[outcome] = float(price)
            if {"home", "draw", "away"}.issubset(prices.keys()):
                inv_home = 1.0 / prices["home"]
                inv_draw = 1.0 / prices["draw"]
                inv_away = 1.0 / prices["away"]
                total = inv_home + inv_draw + inv_away
                if total > 0:
                    return {
                        "home": inv_home / total,
                        "draw": inv_draw / total,
                        "away": inv_away / total,
                    }
        return None

    def _call_mcp_tool(self, competition_name: str) -> dict[str, Any] | None:
        if not self.server_url:
            return None
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": self.tool_name,
                "arguments": {
                    "competitionName": competition_name,
                    "limit": 10,
                },
            },
        }
        response = requests.post(
            self.server_url,
            json=payload,
            timeout=self.timeout_seconds,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
        result = body.get("result")
        if isinstance(result, dict):
            return result
        return None

    def get_context_adjustment(self, home_team: str, away_team: str) -> dict[str, Any]:
        home_news = fetch_team_news(home_team)
        away_news = fetch_team_news(away_team)
        context = fallback_context(home_team, away_team, home_news, away_news)
        try:
            result = self._call_mcp_tool("Premier League")
            probs = self._extract_match_odds_probs(result or {})
            if probs:
                context_score = self._map_prob_gap_to_context_score(probs["home"], probs["away"])
                context["context_score"] = context_score
                context["confidence"] = "medium"
                context["summary"] = (
                    f"MCP odds context suggests home={probs['home']:.1%}, draw={probs['draw']:.1%}, away={probs['away']:.1%} "
                    f"for recent {home_team}/{away_team}-like market conditions."
                )
                context["drivers"] = [
                    f"MCP tool `{self.tool_name}` from `{self.server_url}`",
                    "Context score derived from normalized match-odds probability gap (home vs away).",
                ]
                return context
            context["summary"] = (
                "MCP provider responded, but no parseable soccer match-odds market was found; using neutral context."
            )
            context["drivers"] = [f"MCP call succeeded but tool output was incompatible: `{self.tool_name}`."]
            return context
        except Exception:
            context["summary"] = (
                "MCP context provider is selected but unavailable or not configured; using neutral context fallback."
            )
            context["drivers"] = [
                "Set MCP_SERVER_URL to your MCP JSON-RPC endpoint or switch CONTEXT_PROVIDER=groq."
            ]
        return context


def build_context_provider() -> ContextProvider:
    provider_name = (get_runtime_setting("CONTEXT_PROVIDER", "groq") or "groq").strip().lower()
    if provider_name == "mcp":
        return McpContextProvider()
    return GroqNewsContextProvider()


_PROVIDER: ContextProvider = build_context_provider()


def get_context_adjustment(home_team: str, away_team: str) -> dict[str, Any]:
    return _PROVIDER.get_context_adjustment(home_team, away_team)
