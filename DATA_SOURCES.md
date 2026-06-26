# Data sources for the training set

The pipeline (`build_training_set.py`) needs two inputs you download:
a **match-results CSV** and a **folder of weekly ranking snapshots**. Here's
where each lives, what it covers, and the one real gap.

---

## 1. Ranking snapshots (the point-in-time half)

**`SanderP99/Badminton-Data`** — https://github.com/SanderP99/Badminton-Data
- Weekly BWF world-ranking dumps for all five disciplines in `out/`,
  auto-updated via GitHub Actions. Also ships a tournaments file.
- MIT license. This is your primary ranking source — weekly granularity is
  exactly what the pre-match join needs.
- Clone it, point `--rankings` at the folder of men's-singles weekly CSVs.

**`raywan/bwf-data`** — https://github.com/raywan/bwf-data  (backup)
- Weekly CSVs named `bwf_<discipline>_<year>w<week>.csv` — the filename already
  encodes ISO year+week, which is why the pipeline's default
  `RANKING_DATE_MODE = "isoweek"` parses it out of the box.

**`andyphua/bwf-historical-badminton-world-ranking`** (Kaggle) — men's-singles
historical ranking, another fallback.

> Set `R_NAME_COL` / `R_POINTS_COL` in the CONFIG block to match the actual
> header names in whichever source you pick (they differ slightly), and set
> `RANKING_DATE_MODE` to `isoweek` or `date` depending on the filenames.

---

## 2. Match outcomes (the results half)

**`juanliong14/badminton_data_analysis`** — https://github.com/juanliong14/badminton_data_analysis
(mirror: Kaggle `sanderp/badminton-bwf-world-tour`)
- One row per match: `date`, `round`, `tournament_type`, both players,
  nationalities, scores, and a `winner` flag (1/2, 0 = retired). ~15k matches.
- `ms.csv` is men's singles — that's your `--matches` input.
- **Coverage: April 2018 → early 2021 only.** CC0 license.

### ⚠️ The gap you must close yourself
The ready-made match data **stops in 2021**. For a model predicting the **2024**
Olympics, your most valuable training window — **2022 through July 2024** — is
not in any public dump I could find. You have two options:

1. **Scrape it.** The BWF results site / tournamentsoftware.com carries every
   World Tour match. `SanderP99/Badminton-Data/src/scraping` and the original
   juanliong scraper both target the BWF site and are a starting point — extend
   the date range to 2022–2024. Respect each site's terms of use and rate-limit.
2. **Train on 2018–2021 only** as a first pass to validate the whole pipeline
   end-to-end, then backfill the recent window before trusting predictions.
   (Form drifts a lot over 3 years, so don't ship a 2024 model trained only on
   pre-2021 data — use it to debug, not to predict.)

Whatever you scrape, land it in the **same column schema as `ms.csv`** and the
pipeline ingests it unchanged.

---

## 3. Run it

```bash
# after downloading both sources:
python build_training_set.py \
    --matches ms.csv \
    --rankings ./bwf_ranking_weeks/ \
    --out training_set.csv
```

Watch the **"dropped (no ranking)"** count in the output. A high number means
names aren't matching between the two sources, or your ranking weeks don't span
your match dates — add fixes to `NAME_OVERRIDES` and check the snapshot date
range printed at the top.

---

## 4. Output schema (`training_set.csv`)

One row per match, sorted by date. `player_a` is always the **higher-ranked**
of the two going in, so the label isn't trivially predictable from column order.

| column | meaning |
|---|---|
| `date`, `tournament`, `tier`, `tier_ord`, `round` | context |
| `player_a`, `player_b` | a = higher pre-match points |
| `a_points`, `b_points` | pre-match BWF points (strictly before match date) |
| `points_diff` | a − b (≥ 0 by construction) |
| `points_ratio`, `log_points_diff` | scale-free strength gap features |
| `a_wins` | **label**: 1 if the higher-ranked player won |

The printed **"higher-ranked win rate"** is your baseline: a model using ranking
points must beat just always-pick-the-higher-ranked-player to be worth anything.

---

## Modeling cautions (where naive training sets go wrong)
- **Temporal split, not random.** Validate on a time-held-out slice (e.g. train
  ≤2023, test 2024) so you measure genuine forecasting, not interpolation.
- **Ranking points are a lagging, coarse signal.** They're a fine baseline
  feature, but the gains come from form, head-to-head, and recent results — all
  buildable from the same match table.
- **The Olympics is your test set.** It's excluded from training by default
  (`EXCLUDE_TOURNAMENTS`); keep it that way.
- **Feeding this into the simulator:** once trained, your model becomes the
  `p_win(a, b)` function in `simulate.py`.
