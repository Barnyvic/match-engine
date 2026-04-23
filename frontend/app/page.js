"use client";

import { useEffect, useState, useTransition } from "react";

const BACKEND_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const FALLBACK_STATE = {
  competitions: [],
  teams: [],
  selectedCompetition: "EPL",
  homeTeam: "",
  awayTeam: "",
  matchup: null
};

function percent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatDate(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function resultTone(outcome) {
  if (outcome === "W") return "win";
  if (outcome === "D") return "draw";
  return "loss";
}

async function fetchBackend(path, options = {}) {
  const response = await fetch(`${BACKEND_API_BASE_URL}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.headers || {})
    },
    cache: "no-store"
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.message || `Request failed: ${response.status}`);
  }
  return payload;
}

export default function HomePage() {
  const [state, setState] = useState(FALLBACK_STATE);
  const [loadingSetup, setLoadingSetup] = useState(true);
  const [loadingMatchup, setLoadingMatchup] = useState(false);
  const [error, setError] = useState("");
  const [isRefreshing, startRefresh] = useTransition();

  async function loadSetup(competition, preferredHomeTeam = "", preferredAwayTeam = "") {
    setError("");
    const [competitionsPayload, teamsPayload] = await Promise.all([
      fetchBackend("/api/competitions"),
      fetchBackend(`/api/teams?competition=${encodeURIComponent(competition)}`)
    ]);
    const payload = {
      competitions: competitionsPayload.competitions,
      teams: teamsPayload.teams
    };

    const supportedCompetitions = payload.competitions || [];
    const teams = payload.teams || [];
    const homeTeam = teams.includes(preferredHomeTeam)
      ? preferredHomeTeam
      : teams.includes("Arsenal")
        ? "Arsenal"
        : teams[0] || "";
    const awayTeam = teams.includes(preferredAwayTeam)
      ? preferredAwayTeam
      : teams.includes("Man City")
        ? "Man City"
        : teams.find((team) => team !== homeTeam) || "";

    setState((current) => ({
      ...current,
      competitions: supportedCompetitions,
      teams,
      selectedCompetition: competition,
      homeTeam,
      awayTeam
    }));

    if (homeTeam && awayTeam) {
      await loadMatchup(competition, homeTeam, awayTeam);
    }
  }

  async function loadMatchup(competition, homeTeam, awayTeam) {
    setLoadingMatchup(true);
    setError("");
    try {
      const payload = await fetchBackend(
        `/api/matchup?competition=${encodeURIComponent(competition)}&home_team=${encodeURIComponent(homeTeam)}&away_team=${encodeURIComponent(awayTeam)}`
      );
      setState((current) => ({
        ...current,
        matchup: payload
      }));
    } catch (loadError) {
      setError(loadError.message || "Unable to generate prediction.");
    } finally {
      setLoadingMatchup(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      setLoadingSetup(true);
      try {
        if (!cancelled) {
          await loadSetup("EPL");
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || "Unable to load the app.");
        }
      } finally {
        if (!cancelled) {
          setLoadingSetup(false);
        }
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCompetitionChange(event) {
    const competition = event.target.value;
    setState((current) => ({
      ...current,
      selectedCompetition: competition,
      teams: [],
      homeTeam: "",
      awayTeam: "",
      matchup: null
    }));
    setLoadingSetup(true);
    try {
      await loadSetup(competition);
    } catch (loadError) {
      setError(loadError.message || "Unable to switch competition.");
    } finally {
      setLoadingSetup(false);
    }
  }

  function handleTeamChange(event) {
    const { name, value } = event.target;
    setState((current) => ({
      ...current,
      [name]: value
    }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (!state.homeTeam || !state.awayTeam) return;
    loadMatchup(state.selectedCompetition, state.homeTeam, state.awayTeam);
  }

  function handleRefresh() {
    startRefresh(async () => {
      try {
        setError("");
        await fetchBackend(
          `/api/refresh?competition=${encodeURIComponent(state.selectedCompetition)}`,
          {
            method: "POST"
          }
        );
        await loadSetup(state.selectedCompetition, state.homeTeam, state.awayTeam);
      } catch (refreshError) {
        setError(refreshError.message || "Unable to refresh competition snapshot.");
      }
    });
  }

  const supportedCompetitions = state.competitions.filter((competition) => competition.supported);
  const comingSoonCompetitions = state.competitions.filter((competition) => !competition.supported);
  const matchup = state.matchup;

  return (
    <main className="page-shell">
      <section className="hero-block">
        <div className="hero-copy">
          <p className="eyebrow">Football Prediction Intelligence</p>
          <h1>Search any club matchup.</h1>
          <p className="hero-text">
            Pick a competition, choose both teams, and get one clean prediction
            with probability bars, core stats, recent form, and Groq context.
          </p>
        </div>

        <form className="query-panel" onSubmit={handleSubmit}>
          <label className="field">
            <span>Competition</span>
            <select value={state.selectedCompetition} onChange={handleCompetitionChange}>
              {supportedCompetitions.map((competition) => (
                <option key={competition.key} value={competition.key}>
                  {competition.name}
                </option>
              ))}
            </select>
          </label>

          <div className="field-grid">
            <label className="field">
              <span>Home Team</span>
              <select
                name="homeTeam"
                value={state.homeTeam}
                onChange={handleTeamChange}
                disabled={loadingSetup}
              >
                <option value="">Select home team</option>
                {state.teams.map((team) => (
                  <option key={team} value={team}>
                    {team}
                  </option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Away Team</span>
              <select
                name="awayTeam"
                value={state.awayTeam}
                onChange={handleTeamChange}
                disabled={loadingSetup}
              >
                <option value="">Select away team</option>
                {state.teams.map((team) => (
                  <option key={team} value={team}>
                    {team}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="action-row">
            <button className="primary-button" type="submit" disabled={loadingSetup || loadingMatchup || !state.homeTeam || !state.awayTeam}>
              {loadingMatchup ? "Running prediction..." : "Generate Prediction"}
            </button>
            <button className="ghost-button" type="button" onClick={handleRefresh} disabled={isRefreshing || loadingSetup}>
              {isRefreshing ? "Refreshing..." : "Refresh Data"}
            </button>
          </div>

          {comingSoonCompetitions.length ? (
            <p className="helper-text">
              Coming soon: {comingSoonCompetitions.map((competition) => competition.name).join(", ")}.
            </p>
          ) : null}
        </form>
      </section>

      {error ? <section className="status-panel error">{error}</section> : null}

      <section className="result-layout">
        <section className="result-card hero-result">
          {matchup ? (
            <>
              <div className="result-topline">
                <div>
                  <p className="eyebrow">Prediction</p>
                  <h2>{matchup.summary.headline}</h2>
                </div>
                <div className="timestamp-chip">{formatDate(matchup.generated_at)}</div>
              </div>

              <div className="prediction-strip">
                <article className="spotlight-card">
                  <span>Expected Outcome</span>
                  <strong>{matchup.summary.predicted_outcome}</strong>
                  <small>{matchup.summary.confidence_tier} confidence</small>
                </article>
                <article className="spotlight-card">
                  <span>Competition</span>
                  <strong>{matchup.league}</strong>
                  <small>Club competition model</small>
                </article>
              </div>

              <div className="chart-card">
                {matchup.probability_chart.map((item) => (
                  <div className="probability-row" key={item.label}>
                    <div className="probability-label">
                      <span>{item.label}</span>
                      <strong>{percent(item.value)}</strong>
                    </div>
                    <div className="probability-track">
                      <div className="probability-fill" style={{ width: `${item.value * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              <div className="context-card">
                <p className="eyebrow">Groq Context</p>
                <p>{matchup.prediction.context.summary}</p>
              </div>
            </>
          ) : (
            <div className="empty-panel">
              <p className="eyebrow">Ready</p>
              <h2>Choose a matchup to see the prediction.</h2>
            </div>
          )}
        </section>

        <section className="side-column">
          <section className="result-card">
            <p className="eyebrow">Core Stats</p>
            <h3>Model Signals</h3>
            <div className="stat-grid">
              <article>
                <span>Elo Gap</span>
                <strong>{matchup ? matchup.stats.elo_gap : "--"}</strong>
              </article>
              <article>
                <span>Home Form</span>
                <strong>{matchup ? matchup.stats.home_form_points : "--"}</strong>
              </article>
              <article>
                <span>Away Form</span>
                <strong>{matchup ? matchup.stats.away_form_points : "--"}</strong>
              </article>
              <article>
                <span>Rest Days</span>
                <strong>
                  {matchup ? `${matchup.stats.home_rest_days} / ${matchup.stats.away_rest_days}` : "--"}
                </strong>
              </article>
            </div>
          </section>

          <section className="result-card">
            <p className="eyebrow">Recent Form</p>
            <h3>Last Five Matches</h3>
            <div className="form-columns">
              <div>
                <span className="team-label">{state.homeTeam || "Home team"}</span>
                <div className="form-list">
                  {matchup?.form?.home_team?.map((item) => (
                    <article className="form-item" key={`${item.date}-${item.opponent}`}>
                      <div>
                        <strong>{item.opponent}</strong>
                        <span>{item.date}</span>
                      </div>
                      <div className={`badge ${resultTone(item.outcome)}`}>{item.outcome}</div>
                    </article>
                  ))}
                </div>
              </div>
              <div>
                <span className="team-label">{state.awayTeam || "Away team"}</span>
                <div className="form-list">
                  {matchup?.form?.away_team?.map((item) => (
                    <article className="form-item" key={`${item.date}-${item.opponent}`}>
                      <div>
                        <strong>{item.opponent}</strong>
                        <span>{item.date}</span>
                      </div>
                      <div className={`badge ${resultTone(item.outcome)}`}>{item.outcome}</div>
                    </article>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="result-card">
            <p className="eyebrow">Head To Head</p>
            <h3>Recent Meetings</h3>
            <div className="h2h-list">
              {matchup?.head_to_head?.length ? (
                matchup.head_to_head.map((item) => (
                  <article className="h2h-item" key={`${item.date}-${item.home_team}-${item.away_team}`}>
                    <div>
                      <strong>{item.home_team} vs {item.away_team}</strong>
                      <span>{item.date}</span>
                    </div>
                    <div className="score-pill">{item.score}</div>
                  </article>
                ))
              ) : (
                <p className="helper-text">No recent meetings found in the current historical window.</p>
              )}
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}
