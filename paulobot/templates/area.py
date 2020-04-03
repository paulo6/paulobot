from paulobot.templates.commands import INDENT
from paulobot.game import State as GameState

AREA_STATUS = """**Area: {area}** _(sports: {sports})_
{status}
"""

NULL_AREA_STATUS = """**Sports:** _{sports}_
{status}
"""

def area_string(area, is_direct=False):
    open_games = []
    future_games = []
    held_games = []
    unknown_games = []
    rolling_games = area.rolling_games
    text = ""
    for game in (g for s in area.sports
                   for g in s.games):
        if game.has_space:
            open_games.append(game)
        elif game.state is GameState.WaitingForTime:
            future_games.append(game)
        elif game.state is GameState.WaitingForHold:
            held_games.append(game)
        elif (game not in area.rolling_games and
              game not in area.game_queue):
            unknown_games.append(game)

    # Wrapper to select correct game pretty fn, bearing in mind
    # Game.pretty_for_direct adds its own sport tag
    def game_str(g):
        if is_direct:
            return g.pretty_for_direct
        return f"{g.sport.tag} {g.pretty}"

    for title, games in (("Waiting for sign-ups", open_games),
                         ("Held", held_games),
                         ("Scheduled", future_games),
                         ("Rolling", rolling_games),
                         ("Other", unknown_games)):
        if not games:
            continue
        text += f"{title}:  \n"
        for g in games:
            text += f"{INDENT}{game_str(g)}  \n"

    if area.game_queue:
        text += "\nBusy queue:  \n"
        for idx, g in enumerate(area.game_queue):
            text += f"{INDENT}{idx} {game_str(g)}  \n"

    if area.is_null:
        if not text:
            text = "No games"
        return NULL_AREA_STATUS.format(sports=", ".join(s.name for s in area.sports),
                                       status=text)

    if not text:
        text = "Area is free"
    return AREA_STATUS.format(area=area.name,
                              sports=", ".join(s.name for s in area.sports),
                              status=text)