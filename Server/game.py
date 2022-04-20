import random
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from player import Player

from cards import *


class Game:
    def __init__(self, game_id, start_player, num_players, imploding, implodes):
        self.game_id: int = game_id

        self.owner: Player = start_player
        self.players: List[Player] = [start_player]
        self.spectators: List[Player] = []
        self.player_limit: int = num_players

        self.imploding: bool = imploding
        self.has_imploding: bool = implodes

        self.deck: List[int] = []
        self.discard_pile: List[int] = []

        self.turn: int = 0
        self.implosion_distance: int = 0

        self.started: bool = False

    def setup_deck(self):
        # Emulate multiple decks if the game is big enough
        if len(self.players) == 1:
            return False
        game_size = 1 if len(self.players) < 7 else (
            2 if len(self.players) < 13 else (3 if len(self.players) < 19 else 0))
        if game_size == 0:
            return False

        # Based on official game rules card counts
        self.deck = [TACOCAT] * (4 * game_size) + \
                    [BEARDCAT] * (4 * game_size) + \
                    [RAINBOWCAT] * (4 * game_size) + \
                    [POTATOCAT] * (4 * game_size) + \
                    [CATTERMELON] * (4 * game_size) + \
                    [ATTACK] * (4 * game_size) + \
                    [FAVOR] * (4 * game_size) + \
                    [NOPE] * (5 * game_size) + \
                    [SHUFFLE] * (4 * game_size) + \
                    [SKIP] * (4 * game_size) + \
                    [SEETHEFUTURE] * (5 * game_size) + \
                    \
                    [IMPLODING] if self.has_imploding else [] + \
                    \
                    [REVERSE] * ((4 * game_size) if self.imploding else 0) + \
                    [DRAWFROMBOTTOM] * ((4 * game_size) if self.imploding else 0) + \
                    [FERALCAT] * ((4 * game_size) if self.imploding else 0) + \
                    [ALTERTHEFUTURE] * ((4 * game_size) if self.imploding else 0) + \
                    [TARGETTEDATTACK] * ((3 * game_size) if self.imploding else 0)

        random.shuffle(self.deck)  # Shuffle the deck

        for player in self.players:
            for i in range(4):
                player.cards.append(self.deck.pop())  # Give the player the top 4 cards
            player.cards.append(1)  # Give a defuse to each player

        self.deck += [0 for player in self.players[1:]]  # One Exploding Kitten for each player EXCEPT the winner
        self.deck += [1 for i in range((6 * game_size) - len(self.players))]
        # 6 defuses in a game-size, one has already been given out to each player

        random.shuffle(self.deck)

        self.implosion_distance = (self.deck.index(13) + 1) if self.has_imploding else None
        return True

    def remove_player(self, player):
        if self.started:
            self.discard_pile += player.cards
            self.players.remove(player)

