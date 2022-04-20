from typing import Dict, Callable, Optional, List

from websockets import WebSocketServerProtocol

from game import Game
from player import Player

import struct


# Downstream Protocol
# 0x00 NOP
# 0x01 Pubkey (Handshake pt1) | 8B key
# 0x02 Ack (Handshake pt3) | B success
# 0x03 List Games | H num_games | n(H game_id | B settings | H players | H max_players | H name_length | (n)s name)
# 0x04 Join Game | H game_id
# 0x05 Pregame Info | B settings | H max_players
# 0x06 Pregame Player Info | H num_players | n(H player_id | H name_length | (n)s name)
# 0x07 Ongoing Game Info | B settings | H name_length | (n)s owner | I start_time | H imploding_distance
# 0x08 Ongoing Game Player Info | H num_players | n(H player_id | H name_length | (n)s name)
# 0x09 Cards Info | H num_cards | n(B card_id)
# 0x0A Chat Message | H player_id | H message_length | (n)s message
# 0x0B Nope Opportunity | ? Temporary
# 0x0C Game Over | H winner_id
# 0x0D Kick | H player_id | ? Ban
# 0x0E Card Animation | H class | H subclass | H player_id
# 0x0F See the Future | H card1 | H card2 | H card3
# 0x10 Make Owner

# Upstream Protocol
# 0x00 NOP
# 0x01 Secret (Handshake pt2) | 8B secret | H name_length | (n)s name
# 0x02 Reconnect (Handshake pt2) | 8B secret | H name_length | (n)s name
# 0x03 New Game | B settings | H players
# 0x04 Join Game | H game_id
# 0x05 Leave Game
# 0x06 Shuffle Turn Order
# 0x07 Start Game
# 0x08 Play Card
# 0x09 Play Combo
# 0x0A Play Targeted Attack
# 0x0B Play Nope
# 0x0C Alter The Future
# 0x0D Return Favor
# 0x0E Draw Card
# 0x0F Die
# 0x10 Defuse
# 0x11 End Turn
# 0x12 Chat | H length | (n)s message
# 0x13 Kick | H player_id
# 0x14 Ban | H player_id


def h_nop(data, player) -> bytes:
    return data


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
            0x00: h_nop,
            0x03: self.h_newgame,
        }

    def handle_connection_packet(self, packet: bytes, websocket: WebSocketServerProtocol) -> Optional[Player]:
        return self.connection_handlers.get(packet[0])(packet[1:], websocket)
    
    def handle_packet(self, packet: bytes, player: Player) -> Optional[bytes]:
        return self.handlers.get(packet[0])(packet[1:], player)

    def h_secret(self, data, websocket) -> Player:
        encrypted_secret, name_length = struct.unpack("!8B H", data[:10])
        name = struct.unpack(f"!{name_length}s", data[10:10 + name_length])[0]

        # Decrypt Secret Properly
        secret: bytes = encrypted_secret

        # Record the player
        self.players.append((new_player := Player(secret, name, websocket)))

        # Return the player to keep track of the decryption key and any actions
        return new_player

    def h_rejoin(self, data, websocket) -> Optional[Player]:
        encrypted_secret, name_length = struct.unpack("!8B H", data[:10])
        name = struct.unpack(f"!{name_length}s", data[10:10 + name_length])[0]

        # Decrypt Secret Properly
        secret: bytes = encrypted_secret
        try:
            player = next(player for player in self.players if player.secret == secret)
        except StopIteration:
            return None

        player.death.cancel()
        player.websocket = websocket
        player.name = name
        return player

    def h_newgame(self, data, player) -> bytes:
        self.games.sort(key=lambda game: game.game_id)
        settings, player_count = struct.unpack("!B H", data[:3])
        imploding, implodes = [True if setting == "1" else False for setting in bin(settings)[2:]]
        self.games.append((new_game := Game(self.games[-1].game_id, player, player_count, imploding, implodes)))
        player.set_game(new_game)
        return data[3:]
