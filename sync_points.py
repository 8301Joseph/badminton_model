"""
sync_points.py
==============
Fill a hand-entered match sheet with PRE-COMPETITION ranking points from the
cloned SanderP99/Badminton-Data repo, compute point_diff, and re-orient each row
so player_a = the higher-ranked player going in (leakage-free label).

INPUT  (your schema):
    match_date,event,round,player_a,player_b,a_points,b_points,point_diff,winner
      - winner = 1 if YOUR player_a won, 0 if YOUR player_b won
      - a_points/b_points/point_diff left blank — this script fills them.

OUTPUT (same columns, filled + re-oriented):
      - player_a = higher-ranked going in; a_points >= b_points; point_diff >= 0
      - winner   = 1 if the higher-ranked player won (favorite), 0 if upset

Run:
    python sync_points.py \
        --matches training_matches.csv \
        --rankings Badminton-Data/out/ \
        --out training_matches_synced.csv

Rows whose players can't be found in the rankings are written to
<out>.unmatched.csv with the offending names, so you can fix spelling / add to
NAME_OVERRIDES and re-run.
"""

import argparse, csv, glob, os, re, sys, unicodedata
from bisect import bisect_left
from datetime import datetime, date

# ---- ranking file layout (SanderP99 out/<date>/MS_<date>) -------------------
RANKING_GLOB = "**/MS_*"
RANKING_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
R_NAME_COL = None      # auto-detect (/player|name|id/)
R_POINTS_COL = None    # auto-detect (/point/)

# normalized_name_in_your_sheet -> normalized_name_in_rankings
NAME_OVERRIDES = {
    "li shifeng":         "feng li shi",       # ranked as "LI Shi Feng" (3 tokens)
    "johannessen magnus": "johannesen magnus",  # ranked as "JOHANNESEN Magnus" (1 s)
}

# ---- name normalization (order/accent/case independent) ---------------------
def norm(raw):
    if not raw: return ""
    s = unicodedata.normalize("NFKD", raw)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z\s]", " ", s)
    toks = sorted(t for t in s.split() if t)
    key = " ".join(toks)
    return NAME_OVERRIDES.get(key, key)

# ---- load weekly ranking snapshots -----------------------------------------
def detect_cols(fieldnames):
    nc, pc = R_NAME_COL, R_POINTS_COL
    if nc is None:
        # prefer exact 'name' match first, then fallback
        nc = next((c for c in fieldnames if c.strip().lower() == "name"), None)
        if nc is None:
            nc = next((c for c in fieldnames if re.search(r"\bname\b", c, re.I)), None)
        if nc is None:
            nc = next((c for c in fieldnames if re.search(r"player(?!_id)", c, re.I)), None)
    if pc is None:
        pc = next((c for c in fieldnames if re.search(r"\bpoints\b", c, re.I)), None)
        if pc is None:
            pc = next((c for c in fieldnames if re.search(r"point", c, re.I)), None)
    if not nc or not pc:
        sys.exit(f"Can't find name/points columns in {fieldnames}; set R_NAME_COL/R_POINTS_COL.")
    return nc, pc

def load_rankings(folder):
    files = sorted(glob.glob(os.path.join(folder, RANKING_GLOB), recursive=True))
    if not files:
        sys.exit(f"No MS_* ranking files under {folder} — point --rankings at the repo's out/ folder.")
    snaps, nc, pc = {}, None, None
    for path in files:
        m = RANKING_DATE_RE.search(os.path.basename(path))
        if not m: continue
        d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        with open(path, newline="", encoding="utf-8") as f:
            sample = f.read(2048); f.seek(0)
            try: dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error: dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            if nc is None:
                nc, pc = detect_cols(reader.fieldnames)
                print(f"Ranking columns -> name:'{nc}' points:'{pc}'")
            tbl = {}
            for r in reader:
                nm, p = r.get(nc), r.get(pc)
                if nm and p not in (None, ""):
                    try: tbl[norm(nm)] = float(str(p).replace(",", ""))
                    except ValueError: pass
            if tbl:
                snaps[d] = tbl
                if len(snaps) == 1:
                    sample = list(tbl.keys())[:6]
                    print(f"Sample normalized names from rankings: {sample}")
    dates = sorted(snaps)
    if not dates: sys.exit("Parsed 0 snapshots — check the date regex / folder.")
    print(f"Loaded {len(dates)} snapshots ({dates[0]} … {dates[-1]})")
    return dates, snaps

def points_before(dates, snaps, match_date, name):
    """Most recent snapshot strictly before match_date."""
    j = bisect_left(dates, match_date) - 1
    while j >= 0:
        v = snaps[dates[j]].get(name)
        if v is not None: return v
        j -= 1
    return None

def parse_date(s):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try: return datetime.strptime(s.strip()[:10], fmt).date()
        except (ValueError, AttributeError): pass
    return None

# ---- main -------------------------------------------------------------------
def load_tournament_dates(path="data/tournaments_2024.csv"):
    """Return {tournament_name: date} from tournaments_2024.csv."""
    dates = {}
    for p in [path, "tournaments_2024.csv"]:
        if not os.path.exists(p): continue
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("tournament") or "").strip()
                d = parse_date(row.get("start_date",""))
                if name and d:
                    dates[name] = d
        if dates:
            print(f"Loaded {len(dates)} tournament dates from {p}")
            return dates
    sys.exit("Could not find tournaments_2024.csv. Put it in data/ or the same folder as this script.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", required=True)
    ap.add_argument("--rankings", required=True, help="the repo's out/ folder")
    ap.add_argument("--tournaments", default=None, help="path to tournaments_2024.csv (auto-detected if not set)")
    ap.add_argument("--out", default="training_matches_synced.csv")
    a = ap.parse_args()

    dates, snaps = load_rankings(a.rankings)
    tour_dates = load_tournament_dates(a.tournaments or "data/tournaments_2024.csv")

    out_cols = ["match_date","event","round","player_a","player_b",
                "a_points","b_points","point_diff","winner"]
    kept, unmatched = [], []
    in_winner_vals = []

    with open(a.matches, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            event = (row.get("event") or "").strip()

            # get date: from match_date column if present, else from tournament lookup
            md = parse_date(row.get("match_date",""))
            if md is None:
                md = tour_dates.get(event)
            if md is None:
                unmatched.append({**row, "_problem": f"no date for event: '{event}'"}); continue

            pa, pb = (row.get("player_a") or "").strip(), (row.get("player_b") or "").strip()
            wbit = (row.get("winner") or "").strip()
            if not (pa and pb and wbit in ("0","1")):
                unmatched.append({**row, "_problem": "missing player name or winner-bit"}); continue
            in_winner_vals.append(wbit)

            winner_name = pa if wbit == "1" else pb
            pa_pts = points_before(dates, snaps, md, norm(pa))
            pb_pts = points_before(dates, snaps, md, norm(pb))
            if pa_pts is None or pb_pts is None:
                miss = []
                if pa_pts is None: miss.append(pa)
                if pb_pts is None: miss.append(pb)
                unmatched.append({**row, "_problem": "no ranking for: " + " | ".join(miss)}); continue

            # re-orient: higher-ranked becomes player_a (outcome-independent)
            if pa_pts >= pb_pts:
                A, Ap, B, Bp = pa, pa_pts, pb, pb_pts
            else:
                A, Ap, B, Bp = pb, pb_pts, pa, pa_pts
            winner = 1 if norm(winner_name) == norm(A) else 0

            kept.append({
                "match_date": md.isoformat(), "event": event,
                "round": row.get("round",""), "player_a": A, "player_b": B,
                "a_points": Ap, "b_points": Bp, "point_diff": Ap - Bp,
                "winner": winner,
            })

    kept.sort(key=lambda r: r["match_date"])
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_cols); w.writeheader(); w.writerows(kept)

    if unmatched:
        upath = a.out + ".unmatched.csv"
        cols = list(unmatched[0].keys())
        with open(upath, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(unmatched)

    # diagnostics
    print(f"\nSynced rows:   {len(kept)}  ->  {a.out}")
    print(f"Unmatched:     {len(unmatched)}" + (f"  ->  {a.out}.unmatched.csv (fix & re-run)" if unmatched else ""))
    if kept:
        fav = sum(r["winner"] for r in kept) / len(kept)
        print(f"Favorite win rate (your baseline to beat): {fav:.3f}")
    if in_winner_vals:
        ones = in_winner_vals.count("1") / len(in_winner_vals)
        if ones > 0.85 or ones < 0.15:
            print(f"\n⚠  Your input `winner` was {ones:.0%} ones — looks like you typed the "
                  f"winner as player_a most of the time. That's fine: this script re-oriented "
                  f"by rank, so the OUTPUT label is leakage-free. Just confirm the favorite "
                  f"win rate above looks plausible (~0.6–0.8 for badminton), not ~1.0.")

if __name__ == "__main__":
    main()
