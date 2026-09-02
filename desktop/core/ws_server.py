"""
Self-contained Pure Python Asyncio WebSocket Server & Protocol (RFC 6455).
Zero external dependencies, robust support for multi-megabyte frames, text & binary payloads.
"""

import asyncio
import base64
import hashlib
import struct
from typing import Callable, Optional, Dict, Any, List

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

class WebSocketClientConnection:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_address: tuple):
        self.reader = reader
        self.writer = writer
        self.remote_address = remote_address
        self.closed = False
        self._lock = asyncio.Lock()

    async def send(self, data: str | bytes):
        if self.closed:
            return

        async with self._lock:
            try:
                if isinstance(data, str):
                    payload = data.encode('utf-8')
                    header = bytearray([0x81])  # FIN + Text Opcode
                else:
                    payload = data
                    header = bytearray([0x82])  # FIN + Binary Opcode

                length = len(payload)
                if length <= 125:
                    header.append(length)
                elif length <= 65535:
                    header.append(126)
                    header.extend(struct.pack('>H', length))
                else:
                    header.append(127)
                    header.extend(struct.pack('>Q', length))

                self.writer.write(header + payload)
                await self.writer.drain()
            except Exception as e:
                self.closed = True
                raise e

    async def close(self):
        if not self.closed:
            self.closed = True
            try:
                # Send Close Frame (0x88)
                header = bytes([0x88, 0x00])
                self.writer.write(header)
                await self.writer.drain()
            except Exception:
                pass
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass

    def __aiter__(self):
        return self

    async def __anext__(self) -> str | bytes:
        if self.closed:
            raise StopAsyncIteration

        frame = await self._read_frame()
        if frame is None:
            self.closed = True
            raise StopAsyncIteration
        return frame

    async def _read_frame(self) -> Optional[str | bytes]:
        try:
            head = await self.reader.readexactly(2)
            if not head or len(head) < 2:
                return None

            b1, b2 = head[0], head[1]
            fin = (b1 & 0x80) != 0
            opcode = b1 & 0x0F
            is_masked = (b2 & 0x80) != 0
            payload_len = b2 & 0x7F

            if payload_len == 126:
                ext_len = await self.reader.readexactly(2)
                payload_len = struct.unpack('>H', ext_len)[0]
            elif payload_len == 127:
                ext_len = await self.reader.readexactly(8)
                payload_len = struct.unpack('>Q', ext_len)[0]

            mask_key = b""
            if is_masked:
                mask_key = await self.reader.readexactly(4)

            payload = await self.reader.readexactly(payload_len)

            if is_masked and mask_key:
                unmasked = bytearray(payload_len)
                for i in range(payload_len):
                    unmasked[i] = payload[i] ^ mask_key[i % 4]
                payload = bytes(unmasked)

            # Close frame
            if opcode == 0x8:
                await self.close()
                return None

            # Ping frame -> reply with Pong
            if opcode == 0x9:
                pong_header = bytes([0x8A, len(payload)])
                self.writer.write(pong_header + payload)
                await self.writer.drain()
                return await self._read_frame()

            # Pong frame
            if opcode == 0xA:
                return await self._read_frame()

            # Text frame
            if opcode == 0x1:
                return payload.decode('utf-8', errors='replace')

            # Binary frame
            if opcode == 0x2:
                return payload

            return None
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            return None
        except Exception as e:
            return None


class PureWebSocketServer:
    def __init__(self, handler: Callable[[WebSocketClientConnection], Any], host: str = "0.0.0.0", port: int = 42100):
        self.handler = handler
        self.host = host
        self.port = port
        self._server: Optional[asyncio.Server] = None

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
            reuse_address=True
        )

    async def close(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        remote_address = writer.get_extra_info('peername')
        try:
            # 1. Read HTTP Handshake Request
            headers = {}
            line = await reader.readline()
            if not line:
                writer.close()
                return

            req_line = line.decode('utf-8', errors='ignore').strip()
            while True:
                line = await reader.readline()
                if not line or line in (b'\r\n', b'\n', b''):
                    break
                header_line = line.decode('utf-8', errors='ignore').strip()
                if ':' in header_line:
                    k, v = header_line.split(':', 1)
                    headers[k.strip().lower()] = v.strip()

            key = headers.get('sec-websocket-key')
            if not key:
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await writer.drain()
                writer.close()
                return

            # Compute Accept Key
            accept_raw = hashlib.sha1((key + WS_GUID).encode('utf-8')).digest()
            accept_str = base64.b64encode(accept_raw).decode('ascii')

            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_str}\r\n\r\n"
            )
            writer.write(response.encode('ascii'))
            await writer.drain()

            ws_conn = WebSocketClientConnection(reader, writer, remote_address)
            await self.handler(ws_conn)
        except Exception as e:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


async def serve_ws(handler, host="0.0.0.0", port=42100):
    server = PureWebSocketServer(handler, host, port)
    await server.start()
    return server

