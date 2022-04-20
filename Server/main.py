import asyncio.tasks
import struct
import logging

from websockets import WebSocketServerProtocol

from protocol import ProtocolHandler
from player import Player
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger("websockets.server")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

handler = ProtocolHandler()


async def kill_player(player: Player):
    await asyncio.sleep(5 * 60)
    handler.players.remove(player)


async def handle(websocket: WebSocketServerProtocol, path):
    # region Perform Handshake
    # 1. Send Public Key
    websocket.send(struct.pack("!B 4B", 0x01, handler.public_key))

    # 2. Wait for encrypted secret
    data = websocket.recv()
    while struct.unpack("!B", data[:1])[0] not in (0x01, 0x02):
        data = websocket.recv()

    # 3. Handle decryption of Secret and store it. Or, if it is a reconnection, find the player and return it
    player = handler.handle_connection_packet(data, websocket)
    if player is None:
        websocket.send(struct.pack("!B B", 0x02, 0b0))
        return
    websocket.send(struct.pack("!B B", 0x03, 0b1))
    # endregion

    # Serve Forever
    while True:
        try:
            data = websocket.recv()
            # TODO: Decrypt incoming data with secret
            data = data
            while len(data) > 0:
                data = handler.handle_packet(data, player)

            # Add game-irrelevant packets to the queue
            if player.current_game is None:
                # List Games Packet
                player.packet_queue += \
                    struct.pack("!B H " +
                                "".join([f"H B H H H {len(game.owner.name)}s" for game in handler.games
                                         if not game.started]),

                                0x03,
                                len([game for game in handler.games if not game.started]),
                                *sum([[game.game_id,
                                       int(f"{int(game.imploding)}{int(game.has_imploding)}", 2),
                                       len(game.players),
                                       game.player_limit,
                                       len(game.players[0].name),
                                       game.players[0].name] for game in handler.games if not game.started],
                                     []))

            websocket.send(player.packet_queue)
            player.packet_queue = b"\x00"
        except ConnectionClosed:
            if player.current_game is not None:
                player.current_game.remove_player(player)
            player.death = asyncio.tasks.create_task(kill_player(player))
