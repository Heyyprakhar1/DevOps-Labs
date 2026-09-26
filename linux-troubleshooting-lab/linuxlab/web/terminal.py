import os
import pty
import fcntl
import termios
import struct
import asyncio
import subprocess
import logging
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from linuxlab.config import CONTAINER_NAME
from linuxlab.lab.controller import LabController
from linuxlab.state.manager import StateManager
from linuxlab.db import db

logger = logging.getLogger("linuxlab.terminal")

class TerminalSession:
    """Manages an interactive PTY session attached to the Linux Lab Docker container."""

    def __init__(self, websocket: WebSocket, container_name: str = CONTAINER_NAME, user_id: Optional[str] = None):
        self.websocket = websocket
        self.container_name = container_name
        self.user_id = user_id
        self.master_fd: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.controller = LabController(container_name)
        self.current_cmd_buffer = ""
        self._closing = False

    async def run(self):
        # Ensure container is running
        try:
            self.controller.ensure_running()
        except Exception as e:
            await self.websocket.send_text(f"\r\n\x1b[31mError starting lab container: {e}\x1b[0m\r\n")
            await self.websocket.close()
            return

        # Open pseudo-terminal
        self.master_fd, slave_fd = pty.openpty()

        # Set non-blocking on master_fd
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Set default terminal size: 80 cols, 24 rows
        self.set_terminal_size(24, 80)

        # Spawn interactive docker exec process attached to slave PTY
        cmd = [
            "docker", "exec", "-it",
            "-u", "devops",
            "-e", "TERM=xterm-256color",
            "-e", "COLORTERM=truecolor",
            self.container_name,
            "/bin/bash", "--login"
        ]

        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
                close_fds=True
            )
        finally:
            try:
                os.close(slave_fd)
            except Exception:
                pass

        # Tasks for reading from PTY and WebSocket
        reader_task = asyncio.create_task(self._pty_to_ws())
        writer_task = asyncio.create_task(self._ws_to_pty())

        try:
            done, pending = await asyncio.wait(
                [reader_task, writer_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
        except Exception as e:
            logger.debug(f"Terminal session finished: {e}")
        finally:
            self.cleanup()

    def set_terminal_size(self, rows: int, cols: int):
        """Update window size of the slave PTY."""
        if self.master_fd is not None:
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except Exception as e:
                logger.debug(f"Failed to set window size: {e}")

    async def _pty_to_ws(self):
        """Read data from container master_fd and send to WebSocket."""
        loop = asyncio.get_running_loop()
        try:
            while not self._closing and self.master_fd is not None:
                fut = loop.create_future()

                def on_readable():
                    if not fut.done():
                        fut.set_result(True)

                loop.add_reader(self.master_fd, on_readable)
                try:
                    await fut
                finally:
                    if self.master_fd is not None:
                        try:
                            loop.remove_reader(self.master_fd)
                        except Exception:
                            pass

                try:
                    data = os.read(self.master_fd, 4096)
                    if not data:
                        break
                    await self.websocket.send_bytes(data)
                except BlockingIOError:
                    continue
                except OSError:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"PTY reader exited: {e}")

    async def _ws_to_pty(self):
        """Read messages from WebSocket and write to container master_fd."""
        try:
            while not self._closing and self.master_fd is not None:
                message = await self.websocket.receive()
                msg_type = message.get("type")
                if msg_type == "websocket.disconnect":
                    break

                raw = None
                if message.get("bytes"):
                    raw = message["bytes"]
                elif message.get("text"):
                    text = message["text"]
                    if text.startswith("{") and "resize" in text:
                        try:
                            import json
                            payload = json.loads(text)
                            if payload.get("type") == "resize":
                                rows = int(payload.get("rows", 24))
                                cols = int(payload.get("cols", 80))
                                self.set_terminal_size(rows, cols)
                                continue
                        except Exception:
                            pass
                    raw = text.encode("utf-8", errors="replace")

                if raw and self.master_fd is not None:
                    self._parse_and_record_input(raw)
                    os.write(self.master_fd, raw)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception as e:
            logger.debug(f"WS writer exited: {e}")

    def _parse_and_record_input(self, raw: bytes):
        """Track complete command lines entered by the learner in session history."""
        for b in raw:
            char = chr(b) if b < 128 else ""
            if char in ("\r", "\n"):
                cmd = self.current_cmd_buffer.strip()
                if cmd:
                    if self.user_id:
                        db.record_command_to_session(self.user_id, cmd)
                    else:
                        StateManager.record_command(cmd)
                self.current_cmd_buffer = ""
            elif char in ("\x7f", "\x08"):
                self.current_cmd_buffer = self.current_cmd_buffer[:-1]
            elif char.isprintable():
                self.current_cmd_buffer += char

    def cleanup(self):
        """Close master fd and terminate child process."""
        self._closing = True
        if self.master_fd is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.remove_reader(self.master_fd)
            except Exception:
                pass
            try:
                os.close(self.master_fd)
            except Exception:
                pass
            self.master_fd = None

        if self.proc is not None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
