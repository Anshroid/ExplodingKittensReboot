import random
from typing import Dict, Callable, Optional, List

from websockets import WebSocketServerProtocol

from game import Game
from player import Player
from cards import *

import struct


# Downstream Protocol
# 0x00 NOP
# 0x01 Pubkey (Handshake pt1) | 8B key
# 0x02 Ack (Handshake pt3) | B success
# 0x03 List Games | H num_games | n(H game_id | B settings | H players | H max_players | H name_length | (n)s name)
# 0x04 Join Game | H game_id
# 0x05 Pregame Info | B settings | H max_players
# 0x06 Pregame Player Info | H num_players | n(H player_id | H name_length | (n)s name)
# 0x07 Start Game
# 0x08 Ongoing Game Info | B settings | H name_length | (n)s owner | I start_time | H imploding_distance
# 0x09 Ongoing Game Player Info | H num_players | n(H player_id | H name_length | (n)s name)
# 0x0A Cards Info | H num_cards | n(B card_id)
# 0x0B Chat Message | H player_id | H message_length | (n)s message
# 0x0C Request Favor
# 0x0
# 0x0D Nope Opportunity | ? Temporary
# 0x0E Noped
# 0x0F Game Over | H winner_id
# 0x10 Kick | H player_id | ? Ban
# 0x11 Card Animation | H class | H subclass | H player_id
# 0x12 See the Future | ? alter | H card1 | H card2 | H card3
# 0x13 Make Owner
# 0x14 Error | H error_length | (n)s error_message

# Upstream Protocol
# 0x00 NOP
# 0x01 Secret (Handshake pt2) | 8B secret | H name_length | (n)s name
# 0x02 Reconnect (Handshake pt2) | 8B secret | H name_length | (n)s name
# 0x03 New Game | B settings | H players
# 0x04 Join Game | H game_id
# 0x05 Leave Game
# 0x06 Shuffle Turn Order
# 0x07 Start Game
# 0x08 Play Card | B card_id
# 0x09 Play Combo | H combo_length | n(H card_id)
# 0x0A Play Targeted Card | H card_id | H player_id
# 0x0B Play Nope
# 0x0C Alter The Future
# 0x0D Return Favor
# 0x0D Combo 2 Animation
# 0x0E Draw Card
# 0x0F Die
# 0x10 Defuse
# 0x11 End Turn
# 0x12 Chat | H length | (n)s message
# 0x13 Kick | H player_id
# 0x14 Ban | H player_id


class ProtocolHandler:
    def __init__(self):
        self.public_key: Optional[bytes] = None
        self.private_key: Optional[bytes] = None

        self.players: List[Player] = []
        self.games: List[Game] = []

        self.connection_handlers: Dict[int, Callable[[bytes, WebSocketServerProtocol], Optional[Player]]] = {
            0x01: self.h_secret,
            0x02: self.h_rejoin,
        }

        self.handlers: Dict[int, Callable[[bytes, Player], Optional[bytes]]] = {
            0x00: lambda data, player: data,
            0x03: self.h_newgame,
        }

    def handle_connection_packet(self, packet: bytes, websocket: WebSocketServerProtocol) -> Optional[Player]:
        return self.connection_handlers.get(packet[0])(packet[1:], websocket)
    
    def handle_packet(self, packet: bytes, player: Player) -> Optional[bytes]:
        return self.handlers.get(packet[0])(packet[1:], player)

    def h_secret(self, data: bytes, websocket: WebSocketServerProtocol) -> Player:
        encrypted_secret, name_length = struct.unpack("!8B H", data[:10])
        name = struct.unpack(f"!{name_length}s", data[10:10 + name_length])[0]

        # TODO: Decrypt Secret Properly
        secret: bytes = encrypted_secret

        # Record the player
        self.players.append((new_player := Player(secret, name, websocket)))

        # Return the player to keep track of the decryption key and any actions
        return new_player

    def h_rejoin(self, data: bytes, websocket: WebSocketServerProtocol) -> Optional[Player]:
        encrypted_secret, name_length = struct.unpack("!8B H", data[:10])
        name = struct.unpack(f"!{name_length}s", data[10:10 + name_length])[0]

        # TODO: Decrypt Secret Properly
        secret: bytes = encrypted_secret
        try:
            player = next(player for player in self.players if player.secret == secret)
        except StopIteration:
            return None

        player.death.cancel()
        player.websocket = websocket
        player.name = name
        return player

    def h_newgame(self, data: bytes, player: Player) -> bytes:
        self.games.sort(key=lambda game: game.game_id)
        settings, player_count = struct.unpack("!B H", data[:3])
        imploding, implodes = [bool(setting) for setting in bin(settings)[2:]]
        self.games.append((new_game := Game(self.games[-1].game_id, player, player_count, imploding, implodes)))
        player.set_game(new_game)
        return data[3:]

    def h_joingame(self, data: bytes, player: Player) -> bytes:
        game_id = struct.unpack("!H", data[:2])[0]
        try:
            game = next(game for game in self.games if game.game_id == game_id)
            if len(game.players) == game.player_limit:
                player.send_error("Game is full")
                return data[2:]

            if player in game.banned_players:
                player.send_error("You are banned from this game")
                return data[2:]

            game.players.append(player)
            player.set_game(game)

        except StopIteration:
            player.send_error("Game cannot be found or has already started")
        return data[2:]

    @staticmethod
    def h_leavegame(data: bytes, player: Player) -> bytes:
        player.current_game.players.remove(player)
        player.current_game = None
        return data

    @staticmethod
    def h_shuffleorder(data: bytes, player: Player) -> bytes:
        random.shuffle(player.current_game.players)
        return data

    @staticmethod
    def h_startgame(data: bytes, player: Player) -> bytes:
        player.current_game.started = True
        player.current_game.setup_deck()
        for p in player.current_game.players:
            p.packet_queue += b"\x07"
        return data

    # TODO: Implement card animations
    @staticmethod
    def h_playcard(data: bytes, player: Player) -> bytes:
        card_id = struct.unpack("!H", data[:2])[0]
        player.cards.remove(card_id)
        # For each possible card, perform the appropriate action
        if card_id == ATTACK:
            player.current_game.turn_count += 2 if player.current_game.turn_count > 1 else 1
        elif card_id == SHUFFLE:
            random.shuffle(player.current_game.deck)
        elif card_id == SKIP:
            pass
        elif card_id == REVERSE:
            player.current_game.turn_direction *= -1
        elif card_id == DRAWFROMBOTTOM:
            player.cards.append(player.current_game.deck.pop())
            player.cards.sort()
        elif card_id in (SEETHEFUTURE, ALTERTHEFUTURE):
            player.packet_queue += struct.pack("!B ? 3H", 0x12, bool(card_id - 0x0C), *player.current_game.deck[:3])
            return data[2:]
        player.current_game.advance_turn()
        return data[2:]

    @staticmethod
    def h_playcombo(data: bytes, player: Player) -> bytes:
        combo_length = struct.unpack("!H", data[:2])[0]
        combo = struct.unpack(f"!{combo_length}H", data[2:2 + 2 * combo_length])
        if combo_length == 2:
            if combo[0] == combo[1]:
                # TODO: Finish this
                pass

