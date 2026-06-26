"""
build_training_set.py
=====================
Turn raw badminton match results + weekly BWF ranking snapshots into a
model-ready training CSV, with PRE-MATCH ranking points attached via a
point-in-time join (no leakage).

One row per match. Each row: features known BEFORE the match + the label.

It does the three things that are easy to get wrong:
  1. POINT-IN-TIME JOIN  - attaches each player's ranking points as they stood
     in the most recent weekly snapshot STRICTLY BEFORE the match date. Using
     today's ranking, or a snapshot from during/after the tournament, leaks the
     future into your features.
  2. NAME MATCHING        - match data and ranking data spell/order names
     differently ("AXELSEN Viktor" vs "Viktor Axelsen"). Token-sorted, accent-
     stripped normalization + an override map.
  3. ORIENTATION          - the raw data always lists a "team_one"/"team_two".
     If you train on that, the model just learns "team_one wins ~50%". We emit
     each match in a player-order-independent frame (player_a = the higher-
     ranked of the two) and the label is "did player_a win", so the signal is
     real.

INPUTS (you download these — see DATA_SOURCES.md):
  --matches   path to a match CSV in the juanliong14/Kaggle schema (ms.csv).
  --rankings  a FOLDER of weekly ranking CSVs (e.g. SanderP99 out/ dumps).

OUTPUT:
  --out       training_set.csv

Configure the column names / filename-date parsing in the CONFIG block to match
whichever ranking source you downloaded; the two sources differ slightly.
"""

import argparse
import csv
import glob
import os
import re
import sys
import unicodedata
from bisect import bisect_left
from datetime import datetime, date

# ---------------------------------------------------------------------------
# CONFIG  — adjust to match the files you downloaded
# ---------------------------------------------------------------------------
# Match CSV columns. The pipeline AUTO-DETECTS which of two layouts you have:
#   (A) MANUAL  (what you hand-enter): has `winner` and `loser` NAME columns.
#   (B) SCRAPED (juanliong schema): has team_one_players/team_two_players and a
#       numeric `winner` (1/2/0).
M_DATE        = "date"
M_ROUND       = "round"
M_TOURNAMENT  = "tournament"
M_TIER        = "tier"                # manual format; falls back to "tournament_type"
M_TIER_FALLBACK = "tournament_type"   # scraped format
# manual layout:
M_WINNER_NAME = "winner"
M_LOSER_NAME  = "loser"
# scraped layout:
M_WINNER_FLAG = "winner"             # 1 -> team_one, 2 -> team_two, 0 -> retired
M_P1          = "team_one_players"
M_P2          = "team_two_players"
M_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d")  # tried in order

# Ranking files: SanderP99/Badminton-Data layout is out/<YYYY-MM-DD>/MS_<YYYY-MM-DD>
#   - one subfolder per snapshot date, five discipline files inside,
#   - men's singles = the file starting "MS_", and files have NO .csv extension.
# RANKING_GLOB is matched recursively under the folder you pass to --rankings.
RANKING_GLOB = "**/MS_*"           # men's singles, any subfolder, any/no extension
RANKING_DATE_MODE = "date"         # date is in the filename, not an ISO week
RANKING_DATE_RE    = re.compile(r"(\d{4}-\d{2}-\d{2})")
RANKING_ISOWEEK_RE = re.compile(r"(\d{4})w(\d{1,2})", re.I)  # only used if mode="isoweek"

# Column names inside each ranking file. Leave as None to AUTO-DETECT from the
# header (name column ~ /player|name/, points column ~ /point/). Set explicitly
# if auto-detect guesses wrong — the script prints what it picked.
R_NAME_COL    = None
R_POINTS_COL  = None

# Manual name fixes for pairs token-sort normalization can't reconcile
# (nicknames, transliteration differences). normalized_match_name -> normalized_ranking_name
NAME_OVERRIDES = {
    # "prannoy h s": "h s prannoy",   # example; add as you discover misses
}

# Exclude the event you're predicting so it never leaks into training:
EXCLUDE_TOURNAMENTS = {"olympic games", "olympics"}  # matched case-insensitively, substring


# ---------------------------------------------------------------------------
# NAME NORMALIZATION
# ---------------------------------------------------------------------------
def normalize_name(raw):
    """Lowercase, strip accents/punctuation, sort tokens. Makes name ORDER and
    accents irrelevant: 'AXELSEN Viktor' and 'Viktor Axelsen' collapse to the
    same key 'axelsen viktor'."""
    if raw is None:
        return ""
    s = unicodedata.normalize("NFKD", raw)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z\s]", " ", s)          # drop digits/punctuation
    tokens = [t for t in s.split() if t]
    tokens.sort()
    key = " ".join(tokens)
    return NAME_OVERRIDES.get(key, key)


# ---------------------------------------------------------------------------
# RANKING INDEX  (folder of weekly CSVs -> point-in-time lookup)
# ---------------------------------------------------------------------------
def _isoweek_to_date(year, week):
    # Monday of that ISO week
    return date.fromisocalendar(int(year), int(week), 1)

def _detect_columns(fieldnames):
    """Pick the name and points columns from a header row."""
    name_col = R_NAME_COL
    pts_col = R_POINTS_COL
    if name_col is None:
        for c in fieldnames:
            if re.search(r"player|name", c, re.I):
                name_col = c; break
    if pts_col is None:
        for c in fieldnames:
            if re.search(r"point", c, re.I):
                pts_col = c; break
    if name_col is None or pts_col is None:
        sys.exit(f"Couldn't auto-detect columns from header {fieldnames}. "
                 f"Set R_NAME_COL / R_POINTS_COL in CONFIG.")
    return name_col, pts_col


def _open_table(path):
    """Read one ranking file (CSV, any/no extension, comma or ; or tab)."""
    with open(path, newline="", encoding="utf-8") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        return reader.fieldnames, list(reader)


def load_ranking_index(folder):
    """Return (sorted_dates, snapshots) where snapshots[d] = {norm_name: points}."""
    pattern = os.path.join(folder, RANKING_GLOB)
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        sys.exit(f"No ranking files matching '{RANKING_GLOB}' under {folder}")

    snapshots = {}
    name_col = pts_col = None
    for path in files:
        fname = os.path.basename(path)
        if RANKING_DATE_MODE == "isoweek":
            m = RANKING_ISOWEEK_RE.search(fname)
            snap_date = _isoweek_to_date(m.group(1), m.group(2)) if m else None
        else:
            m = RANKING_DATE_RE.search(fname)
            snap_date = datetime.strptime(m.group(1), "%Y-%m-%d").date() if m else None
        if snap_date is None:
            continue

        fieldnames, rows = _open_table(path)
        if name_col is None:
            name_col, pts_col = _detect_columns(fieldnames)
            print(f"Ranking columns detected -> name: '{name_col}'  points: '{pts_col}'")

        table = {}
        for row in rows:
            name, pts = row.get(name_col), row.get(pts_col)
            if not name or pts in (None, ""):
                continue
            try:
                table[normalize_name(name)] = float(str(pts).replace(",", ""))
            except ValueError:
                continue
        if table:
            snapshots[snap_date] = table

    sorted_dates = sorted(snapshots)
    if not sorted_dates:
        sys.exit("Parsed 0 ranking snapshots — check RANKING_GLOB / date regex / columns.")
    print(f"Loaded {len(sorted_dates)} ranking snapshots "
          f"({sorted_dates[0]} … {sorted_dates[-1]})")
    return sorted_dates, snapshots


def points_before(sorted_dates, snapshots, match_date, norm_name):
    """Most recent snapshot STRICTLY BEFORE match_date. Returns points or None."""
    i = bisect_left(sorted_dates, match_date)   # first index >= match_date
    j = i - 1                                   # strictly before
    while j >= 0:
        pts = snapshots[sorted_dates[j]].get(norm_name)
        if pts is not None:
            return pts
        j -= 1                                  # player absent that week -> look further back
    return None


# ---------------------------------------------------------------------------
# MATCH PARSING
# ---------------------------------------------------------------------------
def parse_date(s):
    for fmt in M_DATE_FORMATS:
        try:
            return datetime.strptime(s.strip()[:10], fmt).date()
        except (ValueError, AttributeError):
            continue
    return None

TIER_RANK = {  # ordinal for tournament prestige; tune as you like
    "super 1000": 7, "super 750": 6, "super 500": 5, "super 300": 4,
    "super 100": 3, "world tour finals": 7, "world championships": 7,
    "olympic games": 7, "super series": 5, "grand prix": 3,
    "continental": 6, "continental championships": 6,  # e.g. Badminton Asia Ch.
}
def tier_ord(tier):
    return TIER_RANK.get((tier or "").strip().lower(), 0)


# ---------------------------------------------------------------------------
# BUILD
# ---------------------------------------------------------------------------
def build(matches_path, rankings_folder, out_path):
    sorted_dates, snapshots = load_ranking_index(rankings_folder)

    rows_out = []
    n_total = n_kept = n_drop_date = n_drop_name = n_drop_rank = n_drop_retire = 0

    with open(matches_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        manual = M_LOSER_NAME in fieldnames          # presence of `loser` -> manual layout
        tier_col = M_TIER if M_TIER in fieldnames else M_TIER_FALLBACK
        print(f"Match file format: {'MANUAL (winner/loser names)' if manual else 'SCRAPED (team_one/two)'}")

        for row in reader:
            n_total += 1
            tour = (row.get(M_TOURNAMENT) or "")
            if any(x in tour.lower() for x in EXCLUDE_TOURNAMENTS):
                continue

            md = parse_date(row.get(M_DATE, ""))
            if md is None:
                n_drop_date += 1; continue

            # --- extract the two players + who won, per layout ---
            if manual:
                w_raw = (row.get(M_WINNER_NAME) or "").strip()
                l_raw = (row.get(M_LOSER_NAME) or "").strip()
                if not w_raw or not l_raw:
                    n_drop_name += 1; continue
                p1_raw, p2_raw, winner_raw = w_raw, l_raw, w_raw
            else:
                flag = (row.get(M_WINNER_FLAG) or "").strip()
                if flag not in ("1", "2"):            # 0 = retired/walkover
                    n_drop_retire += 1; continue
                p1_raw, p2_raw = row.get(M_P1, ""), row.get(M_P2, "")
                if not p1_raw or not p2_raw:
                    n_drop_name += 1; continue
                winner_raw = p1_raw if flag == "1" else p2_raw

            p1, p2 = normalize_name(p1_raw), normalize_name(p2_raw)

            pts1 = points_before(sorted_dates, snapshots, md, p1)
            pts2 = points_before(sorted_dates, snapshots, md, p2)
            if pts1 is None or pts2 is None:
                n_drop_rank += 1; continue

            # ORIENTATION: player_a := higher-ranked of the two (tie -> p1)
            if pts1 >= pts2:
                a_raw, a_pts, b_raw, b_pts = p1_raw, pts1, p2_raw, pts2
            else:
                a_raw, a_pts, b_raw, b_pts = p2_raw, pts2, p1_raw, pts1
            a_wins = 1 if normalize_name(winner_raw) == normalize_name(a_raw) else 0

            rows_out.append({
                "date": md.isoformat(),
                "tournament": tour,
                "tier": row.get(tier_col, ""),
                "tier_ord": tier_ord(row.get(tier_col, "")),
                "round": row.get(M_ROUND, ""),
                "player_a": a_raw,
                "player_b": b_raw,
                "a_points": a_pts,
                "b_points": b_pts,
                "points_diff": a_pts - b_pts,           # >= 0 by construction
                "points_ratio": a_pts / b_pts if b_pts else "",
                "log_points_diff": (a_pts and b_pts) and
                                   (__import__("math").log(a_pts) - __import__("math").log(b_pts)) or 0.0,
                "a_wins": a_wins,                        # <-- LABEL
            })
            n_kept += 1

    if not rows_out:
        sys.exit("No rows produced. Most likely a name-matching or date-range "
                 "mismatch between matches and rankings. Check the diagnostics above.")

    rows_out.sort(key=lambda r: r["date"])
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader(); w.writerows(rows_out)

    base_rate = sum(r["a_wins"] for r in rows_out) / len(rows_out)
    print(f"\nMatches read:            {n_total}")
    print(f"  dropped (bad date):    {n_drop_date}")
    print(f"  dropped (retired/WO):  {n_drop_retire}")
    print(f"  dropped (no name):     {n_drop_name}")
    print(f"  dropped (no ranking):  {n_drop_rank}   <- watch this; high = name/date mismatch")
    print(f"Training rows written:   {n_kept}  ->  {out_path}")
    print(f"Higher-ranked win rate:  {base_rate:.3f}  (your baseline to beat)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", required=True, help="match CSV (juanliong/Kaggle schema)")
    ap.add_argument("--rankings", required=True, help="FOLDER of weekly ranking CSVs")
    ap.add_argument("--out", default="training_set.csv")
    a = ap.parse_args()
    build(a.matches, a.rankings, a.out)


if __name__ == "__main__":
    main()
