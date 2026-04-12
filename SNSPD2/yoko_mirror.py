import argparse
import asyncio
import logging
import socket
import ipaddress
from typing import cast

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

EQUIPMENT_PORT = 7655
PROXY_PORT = 7655
RECONNECT_DELAY = 5


class EquipmentProxy:
    def __init__(self, equipment_host, listen_addr, listen_port, keepalive_interval=1.0):
        self.equipment_host = equipment_host
        self.listen_addr = listen_addr
        self.listen_port = listen_port
        self.keepalive_interval = keepalive_interval
        self.equipment_reader = None
        self.equipment_writer = None

    async def connect_equipment(self):
        """Establish connection with retry logic"""
        while True:
            try:
                self.equipment_reader, self.equipment_writer = (
                    await asyncio.open_connection(self.equipment_host, EQUIPMENT_PORT)
                )
                logger.info(
                    f"Connected to equipment at {self.equipment_host}:{EQUIPMENT_PORT}"
                )
                # Set TCP keepalive
                try:
                    sock = self.equipment_writer.get_extra_info("socket")
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    if KEEPIDLE := getattr(socket, "TCP_KEEPIDLE", None):
                        sock.setsockopt(
                            socket.IPPROTO_TCP,
                            KEEPIDLE,
                            int(self.keepalive_interval),
                        )
                except (AttributeError, OSError) as e:
                    logger.warning(f"Failed to set TCP keepalive: {e}")
                return
            except Exception as e:
                logger.error(
                    f"Failed to connect: {e}. Retrying in {RECONNECT_DELAY}s..."
                )
                await asyncio.sleep(RECONNECT_DELAY)

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        client_addr = writer.get_extra_info("peername")
        logger.info("Client connected from %s", client_addr)
        try:
            if not self.equipment_reader or not self.equipment_writer:
                await self.connect_equipment()
                self.equipment_reader = cast(
                    asyncio.StreamReader, self.equipment_reader
                )
                self.equipment_writer = cast(
                    asyncio.StreamWriter, self.equipment_writer
                )

            while True:
                data = await reader.read(1024)
                if not data:
                    break

                logger.debug(f"Client -> Equipment: {data}")
                self.equipment_writer.write(data)
                await self.equipment_writer.drain()

                response = await self.equipment_reader.read(1024)
                if not response:
                    logger.warning("Equipment disconnected")
                    await self.connect_equipment()
                    continue

                logger.debug(f"Equipment -> Client: {response}")
                writer.write(response)
                await writer.drain()
        except Exception as e:
            logger.error("Client handler error: %s", e)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, OSError) as e:
                logger.debug("Error during connection close: %s", e)
            logger.info("Connection closed for %s", client_addr)

    async def run(self):
        """Start the proxy server"""
        await self.connect_equipment()

        server = await asyncio.start_server(
            self.handle_client, self.listen_addr, self.listen_port
        )
        logger.info(f"Proxy listening on {self.listen_addr}:{self.listen_port}")

        async with server:
            await server.serve_forever()


def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description="Socket Mirror Proxy - Maintains persistent connection to equipment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single instrument on default address
  python equipment_proxy.py 192.168.1.100

  # Multiple instruments with different addresses
  python equipment_proxy.py 192.168.1.100 --listen 127.0.0.2
  python equipment_proxy.py 192.168.1.101 --listen 127.0.0.3
  python equipment_proxy.py 192.168.1.102 --listen 127.0.0.4
        """,
    )

    parser.add_argument(
        "equipment_host",
        help="IP address or hostname of the equipment",
    )

    parser.add_argument(
        "--listen",
        "-l",
        type=str,
        default="127.0.0.1",
        help="Listen address. Defaults to localhost, set to * to allow external connections",
    )

    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=PROXY_PORT,
        help="Listen port",
    )

    parser.add_argument(
        "--keepalive-interval",
        type=int,
        default=1,
        help="TCP keepalive interval in seconds. Default: 1",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level. Default: INFO",
    )

    args = parser.parse_args()

    # Validate address
    if args.listen != "*":
        _address = ipaddress.ip_address(args.listen)
    else:
        args.listen = None  # Bind to all interfaces

    return args


if __name__ == "__main__":
    args = parse_arguments()

    # Set logging level
    logging.getLogger().setLevel(args.log_level)

    logger.info(f"Starting socket proxy")
    logger.info(f"Equipment: {args.equipment_host}:{EQUIPMENT_PORT}")
    logger.info(f"Listen: {args.listen}:{args.port}")

    proxy = EquipmentProxy(args.equipment_host, args.listen, args.port, args.keepalive_interval)

    try:
        asyncio.run(proxy.run())
    except KeyboardInterrupt:
        logger.info("Proxy shutdown by user")
