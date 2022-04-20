import struct
from asyncio import Task
from typing import Optional, List, TYPE_CHECKING

from websockets import WebSocketServerProtocol

if TYPE_CHECKING:
    from game import Game


class Player:
    def __init__(self, secret, name, websocket):
        self.secret: bytes = secret
        self.name: str = name
        self.current_game: Optional[Game] = None
        self.death: Optional[Task] = None
        self.cards: List[int] = []
        self.websocket: WebSocketServerProtocol = websocket
        self.packet_queue: bytes = b'\x00'

    def set_game(self, game) -> None:
        self.current_game: Game = game

    def send_error(self, error: str):
        self.packet_queue += struct.pack(f'!B H {len(error)}s', 0x11, len(error), error)
