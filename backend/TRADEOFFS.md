# Match-Engine Tradeoffs

## What This Version Optimizes For

- Fast local iteration over perfect modeling sophistication.
- Strict chronological processing to avoid obvious look-ahead leakage.
- A modular pipeline so EPL can expand into more leagues with small configuration changes.

## Current Constraints

- The football-data.co.uk feed is convenient and free, but it does not provide the deepest event-level data.
- Logistic regression is intentionally simple and interpretable; stronger accuracy may require richer features or ensemble methods.
- The Groq layer is structured for real use, but quality depends heavily on the freshness and relevance of RSS snippets.
- Current ROI analysis uses closing-style book odds from the dataset and does not model staking strategies, liquidity, or slippage.

## Next Iterations

- Add multiple leagues and retrain with league-aware features.
- Cache LLM context summaries to avoid repeated calls for the same fixture.
- Introduce richer injury, lineup, and schedule congestion signals.
- Compare logistic regression against gradient boosting and calibration methods like isotonic regression.
