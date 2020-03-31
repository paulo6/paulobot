import datetime

from paulobot.common import GameState, TimeDelta

G_NOT_QUORATE_SPACES = "Game for {time} -- {players} +{spaces}"
G_NOT_QUORATE_OPEN = "Game for {time} -- {players} +any (until 'ready' issued)"
G_WAITING_FOR_TIME = "Game for {time} -- {players}. Starting in {future}"
G_WAITING_FOR_AREA = "Game for {time} -- {players}. Waiting until area is free -- queue position {place}/{length}"
G_WAITING_FOR_UNHOLD = "Game for {time} -- {players}. Waiting for unhold place by {holder}"
G_PLAYER_CHECK = "Game for {time} -- {players}. Waiting {timer} secs for idle players: {idlers}"
G_ROLL = "Game for {time} -- {players}. **ROLL**"
G_ROLL_MATCHUP = "Game for {time} -- {team1} vs {team2} **ROLL**\n" \
    "(quality {quality:.2f}, history {history}, win % {win1:.2f}-{win2:.2f}) "

PLAYER_IDLE = "{sport} game for {time} ready to roll, but you are idle. Say something in here or in room " \
              "'{room}' in the next {secs} secs or get dropped!"



def game_string(game, no_tags=False):
    time = str(game.gtime)
    time_index = game.time_index
    if time_index > 0:
        time += f" <{time_index + 1}>"
    now = datetime.datetime.now()
    if game.created_time.date() != now.date():
        time += ' (created {})'.format(str(game.created_time).split(".")[0])

    res = f"Game for {game.gtime} state is {game.state}"
    if game.state == GameState.NotQuorate:
        if game.sport.max_players == 0:
            res = G_NOT_QUORATE_OPEN.format(time=time,
                                            players=game.players)
        else:
            res = G_NOT_QUORATE_SPACES.format(time=time,
                                              players=game.players,
                                              spaces=game.spaces_left)

    elif game.state == GameState.WaitingForTime:
        res = G_WAITING_FOR_TIME.format(time=time,
                                        players=game.players,
                                        future=TimeDelta(game.gtime, now))

    elif game.state == GameState.WaitingForArea:
        res = G_WAITING_FOR_AREA.format(time=time,
                                        players=game.players,
                                        place=game.sport.area.queue_index(game) + 1,
                                        length=game.sport.area.queue_len)

    elif game.state == GameState.WaitingForHold:
        res = G_WAITING_FOR_UNHOLD.format(time=time,
                                          players=game.players,
                                          holder=game.held_by.username)

    elif game.state == GameState.PlayerCheck:
        res = G_PLAYER_CHECK.format(time=time,
                                    players=game.players,
                                    timer=game.idle_secs_left,
                                    idlers=game.not_ready_players)

    elif game.state == GameState.Rolling:
        res = G_ROLL.format(time=time,
                            players=game.players if no_tags else game.players.tagged)

    return res