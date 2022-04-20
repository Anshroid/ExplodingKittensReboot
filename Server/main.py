import asyncio.tasks
import struct
import logging
from typing import Dict, Callable, Optional, List

from websockets import WebSocketServerProtocol

from game import Game
from player import Player
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger("websockets.server")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

public_key: Optional[bytes] = None
private_key: Optional[bytes] = None

players: List[Player] = []
games: List[Game] = []


async def kill_player(player: Player):
    await asyncio.sleep(5 * 60)
    players.remove(player)


# region Handlers
def h_nop(data, player) -> bytes:
    return data


def h_secret(data, websocket) -> Player:
    encrypted_secret, name_length = struct.unpack("!8B H", data[:10])
    name = struct.unpack(f"!{name_length}s", data[10:10 + name_length])[0]

    # Decrypt Secret Properly
    secret: bytes = encrypted_secret

    # Record the player
    players.append((new_player := Player(secret, name, websocket)))

    # Return the player to keep track of the decryption key and any actions
    return new_player


def h_rejoin(data, websocket) -> Optional[Player]:
    encrypted_secret, name_length = struct.unpack("!8B H", data[:10])
    name = struct.unpack(f"!{name_length}s", data[10:10 + name_length])[0]

    # Decrypt Secret Properly
    secret: bytes = encrypted_secret
    try:
        player = next(player for player in players if player.secret == secret)
    except StopIteration:
        return None

    player.death.cancel()
    player.websocket = websocket
    player.name = name
    return player


def h_newgame(data, player) -> bytes:
    games.sort(key=lambda game: game.game_id)
    settings, player_count = struct.unpack("!B H", data[:3])
    imploding, implodes = [True if setting == "1" else False for setting in bin(settings)[2:]]
    games.append((new_game := Game(games[-1].game_id, player, player_count, imploding, implodes)))
    player.set_game(new_game)
    return data[3:]


# endregion


# region Protocol
# Downstream Protocol
# 0x00 Empty
# 0x01 Pubkey (Handshake pt1) | 8B key
# 0x02 Ack (Handshake pt3) | B success
# 0x03 List Games | H num_games | n(H game_id | B settings | H players | H max_players | H name_length | (n)s name)

# Upstream Protocol
connection_handlers: Dict[int, Callable[[bytes, WebSocketServerProtocol], Optional[Player]]] = {
    0x01: h_secret,  # Secret (Handshake pt2) | 8B secret | H name_length | (n)s name
    0x02: h_rejoin,  # Reconnect (Handshake pt2) | 8B secret | H name_length | (n)s name
}

handlers: Dict[int, Callable[[bytes, Player], Optional[bytes]]] = {
    0x00: h_nop,  # Empty
    0x03: h_newgame,  # New Game Creation | B settings | H players
}


# endregion


async def handle(websocket: WebSocketServerProtocol, path):
    # region Perform Handshake
    # 1. Send Public Key
    websocket.send(struct.pack("!B 4B", 0x01, public_key))

    # 2. Wait for encrypted secret
    data = websocket.recv()
    while struct.unpack("!B", data[:1])[0] not in (0x01, 0x02):
        data = websocket.recv()

    # 3. Handle decryption of Secret and store it. Or, if it is a reconnection, find the player and return it
    player = connection_handlers.get(data[:1])(data[1:], websocket)
    if player is None:
        websocket.send(struct.pack("!B B", 0x02, 0b0))
        return
    websocket.send(struct.pack("!B B", 0x03, 0b1))
    # endregion

    # Serve Forever
    while True:
        try:
            data = websocket.recv()
            # Decrypt incoming data with secret
            data = data
            while len(data) > 0:
                data = handlers.get(data[:1])(data[1:], player)

            # Add game-irrelevant packets to the queue
            if player.current_game is None:
                # List Games Packet
                player.packet_queue += struct.pack("!B H " +
                                                   "".join([f"H B H H H {len(game.players[0].name)}s" for game in games
                                                            if not game.started]),

                                                   0x03,
                                                   len([game for game in games if not game.started]),
                                                   *sum([[game.game_id,
                                                          int(f"{1 if game.imploding else 0}" +
                                                              f"{1 if game.has_imploding else 0}", 2),
                                                          len(game.players),
                                                          game.player_limit,
                                                          len(game.players[0].name),
                                                          game.players[0].name] for game in games if not game.started],
                                                        []))

            websocket.send(player.packet_queue)
            player.packet_queue = b"\x00"
        except ConnectionClosed:
            if player.current_game is not None:
                player.current_game.remove_player(player)
            player.death = asyncio.tasks.create_task(kill_player(player))
