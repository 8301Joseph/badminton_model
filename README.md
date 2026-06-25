# Paris 2024 Olympic Men's Singles — Tournament Simulator

Monte Carlo simulation of the full event: 13 round-robin groups → knockout
(R16 → QF → SF → Final + bronze), with the three quarter-final byes (groups
A, E, P) built in.

## Files
- `players.csv` — all 41 players: group, bye flag, seed (9 July), Race-to-Paris
  ranking + BWF points, qualification route.
- `simulate.py` — the engine. It ships with **no** prediction logic; it won't
  run until you implement the matchup model.

## Implement YOUR model
The engine is just plumbing — you supply the prediction. Open `simulate.py` and
implement `p_win(a, b)` inside `make_p_win`: return P(a beats b) for one match,
a float in [0, 1]. You get every column of players.csv via `players[a][...]`.
Until you do, the simulator raises `NotImplementedError` by design.

Everything downstream — groups, byes, bracket, R16→QF→SF→Final, and the
aggregation into per-player stage probabilities — is already wired and waits on
your `p_win`. Output is written to a CSV of your choosing (`--out`).

## Three strength signals already in the data
Treat these as distinct features, not interchangeable:
- `bwf_points` / `paris_ranking` — 52-week form as of 30 Apr 2024 (qualifying).
- `seed_9july` — closest to draw-day strength; it set the bracket. Note it
  diverges from the ranking: Axelsen was ranking #1 but seed #2; Lakshya Sen was
  ranking #13 but UNSEEDED (and reached the semis).
- `qualification_route` — rough proxy for how deep a pull a player was.

## Things to refine (flagged honestly)
1. **Group tie-breaks** are currently random among players level on match wins.
   The real rule is game difference, then point difference. If your model emits
   set scores, implement that for sharper group-winner probabilities.
2. **R16 opponent pairings** (which of D/H/J/K/N each strong group meets) are a
   best-effort reconstruction. The confirmed structure — 3 byes, and the two
   semifinal halves (P & L vs C & G) — is correct; verify the five `R16` lines
   against the official BWF draw and edit if needed. It's pure data, one line each.
3. **Best-of-3 detail**: `p_win` already represents a whole match. If you'd
   rather model game-by-game, expand `play_match`.

## Validation idea
Because the sim resolves every stage, you can check calibration at each one:
did your predicted group winners hit? R16 survivors? QF? That's far more
diagnostic than only grading the final. Compare `sim_results.csv` against the
actual finishes (Axelsen gold, Vitidsarn silver, Lee Zii Jia bronze, Sen 4th).
