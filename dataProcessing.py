import csv
from collections import defaultdict

class Player:
    def __init__(self, name, bwf_points, seed_9july, group_is_bye):
        self.name = name
        self.bwf_points = bwf_points
        self.seed_9july = seed_9july
        self.group_is_bye = group_is_bye

class Group:
    def __init__(self, letter, players):
        self.letter = letter
        self.players = players  # list, length up to 4

def load_players(path):
    players = []
    groups_by_letter = defaultdict(list)

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            seed = int(row["seed_9july"]) if row["seed_9july"] else None
            player = Player(
                name=row["player_name"],
                bwf_points=float(row["bwf_points"]),
                seed_9july=seed,
                group_is_bye=(row["group_is_bye"] == "1"),
            )
            players.append(player)
            groups_by_letter[row["group"]].append(player)

    groups = [Group(letter, members) for letter, members in groups_by_letter.items()]
    return players, groups

players, groups = load_players("data/players.csv")