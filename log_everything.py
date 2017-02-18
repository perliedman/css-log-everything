import sqlite3
from events import Event
from messages import SayText2
from collections import defaultdict
import json
from datetime import datetime


class LogEverythingPlugin(object):
    def __init__(self, connection):
        self.connection = connection
        self.users = {}
        self.teams = defaultdict(list)
        self._round_start = None

    def on_player_connect(self, event):
        user_id = event['userid']
        self.users[user_id] = {
            'steam_id': event['networkid'],
            'name': event['name']
        }

    def on_player_disconnect(self, event):
        user_id = event['userid']
        del self.users[user_id]

    def on_player_team(self, event):
        user_id = event['userid']
        old_team_id = event['oldteam']
        if old_team_id in self.teams:
            team = self.teams[old_team_id]
            team.remove(user_id)

        if not event['disconnect']:
            new_team_id = event['team']
            self.teams[new_team_id] = user_id

    def on_round_start(self, _):
        self._round_start = datetime.now()

    def on_round_end(self, event):
        def team_to_json(team):
            return json.dumps([team])

        cursor = self.connection.cursor()

        winner = event['winner']
        win_team = self.teams[winner]
        lose_team = [team for (team_number, team) in self.teams.items() if team_number != winner][0]
        cursor.execute("""
            insert into rounds (round_start, round_end, win_team, lose_team) values (?, ?, ?, ?)""",
                       (self._round_start, datetime.now(),
                        team_to_json(win_team), team_to_json(lose_team)))

if __name__ == '__main__':
    PLUGIN = None

    @Event('player_connect')
    @Event('player_connect_client')
    def on_player_connect(event):
        global PLUGIN
        PLUGIN.on_player_connect(event)

    @Event('player_disconnect')
    def on_player_disconnect(event):
        global PLUGIN
        PLUGIN.on_player_disconnect(event)

    @Event('player_team')
    def on_player_team(event):
        global PLUGIN
        PLUGIN.on_player_team(event)

    @Event('round_start')
    def on_round_start(_):
        global PLUGIN
        PLUGIN.on_round_start(_)

    @Event('round_end')
    def on_round_end(event):
        global PLUGIN
        PLUGIN.on_round_end(event)

    def load():
        connection = sqlite3.connect('log-everything.sqlite3')
        PLUGIN = LogEverythingPlugin(connection)
        SayText2('Log Everything plugin loaded.').send()

    def unload():
        PLUGIN = None
        SayText2('Log Everything plugin unloaded').send()
