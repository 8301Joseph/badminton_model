import csv 

class Player:
    def __init__(self, name: str, bwf_points: float, seed_9july: int, group_is_bye: str):
        self.name = name
        self.bwf_points = bwf_points
        self.seed_9july = seed_9july
        self.group_is_bye = group_is_bye

class Group:
    def __init__(self, letter: str, player1: Player, player2: Player, player3: Player, player4: Player):
        self.letter = letter
        self.player1 = player1
        self.player2 = player2
        self.player3 = player3
        self.player4 = player4

def load_players(path):
    players = []
    groups = []
    groupMembers = []
    with open(path, newline = "", encoding = "utf-8") as f:
        for row in csv.DictReader(f):
            name = row["player_name"]
            bwf_points = float(row["bwf_points"])
            seed_9july = int(row["seed_9july"]) if row["seed_9july"] else None
            group_is_bye = row["group_is_bye"] == "1" #what does this mean
            newPlayer = Player(name, bwf_points, seed_9july, group_is_bye) 
            players.append(newPlayer)
            if row["group"] == 'A':
                groupMembers.append(newPlayer)
            elif row["group"] != prevRowGroup:
                if len(groupMembers) == 4:
                    newGroup = Group(prevRowGroup, groupMembers[0], groupMembers[1], groupMembers[2], groupMembers[3])
                else:
                    newGroup = Group(prevRowGroup, groupMembers[0], groupMembers[1], groupMembers[2], "N/A")
                groupMembers.clear()
                groups.append(newGroup)
                groupMembers.append(newPlayer)
            elif row["group"] == prevRowGroup:
                groupMembers.append(newPlayer)
            prevRowGroup = row["group"]
    #account for the last group when iteration ends
    if len(groupMembers) == 4:
        newGroup = Group(prevRowGroup, groupMembers[0], groupMembers[1], groupMembers[2], groupMembers[3])
    else:
        newGroup = Group(prevRowGroup, groupMembers[0], groupMembers[1], groupMembers[2], "N/A")
    groups.append(newGroup)
    return players, groups
        



players,groups = load_players("data/players.csv")
#for player in players:
    print(player.name)
    print(player.bwf_points)
    print(player.seed_9july)
    print(player.group_is_bye)