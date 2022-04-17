import struct
from typing import Dict, Callable, Optional

import websockets

public_key = None
private_key = None

saved_clients = []

packet_queue = b""


# region Handlers
def h_secret(data):
    encrypted_secret = struct.unpack("4B", data)
    # Decrypt Secret Properly
    secret = encrypted_secret
    saved_clients.append(secret)
    return secret
# endregion


# region Protocol
# Downstream Protocol
# 0x00 Pubkey (Handshake pt1) | B 4B


# Upstream Protocol
# 0x01 Secret is handled differently from the rest, so is not in the handlers list
# 0x01 Secret (Handshake pt2) | B 4B
handlers: Dict[int, Callable[[bytes], Optional[bytes]]] = {
}
# endregion


async def handle(websocket: websockets.WebSocketServerProtocol, path):
    # region Perform Handshake
    # 1. Send Public Key
    websocket.send(struct.pack("B 4B", 0x00, public_key))

    # 2. Wait for encrypted secret
    data = websocket.recv()
    while struct.unpack("B", data[:2]) != 0x01:
        data = websocket.recv()

    # 3. Handle decryption of Secret and store it
    secret = h_secret(data[2:])
    # endregion

    # Serve Forever
    while True:
        data = websocket.recv()
        # Decrypt incoming data with secret
        data = data
        while len(data) > 0:
            data = handlers[data[:2]](data[2:])
        websocket.send(packet_queue)
