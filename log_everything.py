import sqlite3
from events import Event
from messages import SayText2
from collections import defaultdict
import json
from datetime import datetime
from filters.players import PlayerIter
from pprint import pprint

class LogEverythingPlugin(object):
    def __init__(self, connection):
        self.connection = connection
        self.users = {}
        self.teams = defaultdict(list)
        self._round_id = None

    def add_player(self, user_id, steam_id, name):
        self.users[user_id] = {
            'steam_id': steam_id,
            'name': name
        }

        cursor = self.connection.cursor()
        cursor.execute("""
            insert or replace into players (steam_id, name) values (?,  ?)
            """, (steam_id, name))

    def remove_player(self, event):
        user_id = event['userid']
        del self.users[user_id]

        for team in self.teams.values():
            try:
                team.remove(user_id)
            except ValueError:
                pass

    def set_player_team(self, user_id, new_team_id, old_team_id=None):
        if old_team_id in self.teams:
            team = self.teams[old_team_id]
            try:
                team.remove(user_id)
            except ValueError:
                pass

        self.teams[new_team_id].append(user_id)

    def start_round(self):
        cursor = self.connection.cursor()
        cursor.execute("""
            insert into rounds (starttime) values (?)""",
                       (datetime.now(),))
        self._round_id = cursor.lastrowid

    def end_round(self, winner_team_id):
        def team_to_json(team):
            return json.dumps([self.users[user_id]['steam_id'] for user_id in team])

        cursor = self.connection.cursor()

        # If it's a draw, winner_team_id will be something weird
        if winner_team_id in self.teams and self._round_id:
            win_team = self.teams[winner_team_id]
            lose_team = [team for (team_number, team) in self.teams.items() \
                if team_number != winner_team_id][0]
            cursor.execute("""
                update rounds set endtime=?, win_team=?, lose_team=? where id=?""",
                           (datetime.now(), team_to_json(win_team), team_to_json(lose_team),
                            self._round_id))
            self.connection.commit()

            self._round_id = None

    def add_event(self, event_type, data, subject=None, indirect=None):
        if self._round_id:
            cursor = self.connection.cursor()
            cursor.execute("""
                insert into events (round_id, time, type, data, subject_id, indirect_id)
                """, (self._round_id, datetime.now(), event_type, json.dumps(data),
                      self.users[subject] if subject else None,
                      self.users[indirect] if indirect else None))
            self.connection.commit()

def ensure_up_to_date(connection):
    cursor = connection.cursor()
    cursor.execute("""
        create table if not exists rounds (
            id integer primary key autoincrement,
            starttime datetime,
            endtime datetime null,
            win_team text null,
            lose_team text null)
        """)
    cursor.execute("""
        create table if not exists players (
            steam_id varchar(16) primary key,
            name varchar(32))
        """)
    cursor.execute("""
        create table if not exists `events` (
            id integer primary key autoincrement,
            round_id integer references rounds,
            time datetime,
            type varchar(16),
            data text,
            subject_id varchar(16) null references players,
            indirect_id varchar(16) null references players)
        """)

PLUGIN = None

@Event('player_connect')
@Event('player_connect_client')
def on_player_connect(event):
    global PLUGIN
    user_id = event['userid']
    steam_id = event['networkid']
    name = event['name']
    PLUGIN.add_player(user_id, steam_id, name)

@Event('player_disconnect')
def on_player_disconnect(event):
    global PLUGIN
    PLUGIN.remove_player(event['userid'])

@Event('player_team')
def on_player_team(event):
    global PLUGIN
    if not event['disconnect']:
        user_id = event['userid']
        new_team = event['team']
        old_team = event['oldteam']

        PLUGIN.set_player_team(user_id, new_team, old_team)

@Event('round_start')
def on_round_start(_):
    global PLUGIN
    PLUGIN.start_round()

@Event('round_end')
def on_round_end(event):
    global PLUGIN
    PLUGIN.end_round(event['winner'])

@Event('player_hurt')
def on_event(event):
    global PLUGIN
    subject_id = event['userid'] if 'userid' in event else None
    indirect_id = event['attacker'] if 'attacker' in event else None
    PLUGIN.add_event('player_hurt', event.variables.as_dict(), subject_id, indirect_id)

def load():
    global PLUGIN
    connection = sqlite3.connect('log-everything.sqlite3')
    ensure_up_to_date(connection)
    PLUGIN = LogEverythingPlugin(connection)

    for player in list(PlayerIter('all')):
        user_id = player.userid
        PLUGIN.add_player(user_id, player.steamid, player.name)
        PLUGIN.set_player_team(user_id, player.team)


    SayText2('Log Everything plugin loaded.').send()

def unload():
    global PLUGIN
    PLUGIN = None
    SayText2('Log Everything plugin unloaded').send()
