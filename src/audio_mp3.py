"""
SmartShell — DFPlayer Mini MP3 module for countdown audio.

Plays pre-recorded countdown during the cancellation window.
See docs/features/04_audio_mp3.md.
"""

from __future__ import annotations

import time
from typing import Any

from src.config import MP3_BAUD, MP3_RX_GPIO, MP3_SERIAL_PORT, MP3_TX_GPIO


def _dfplayer_checksum(data: list[int]) -> int:
    """Compute DFPlayer Mini checksum: -Sum(bytes 1..6) as 16-bit."""
    s = sum(data[1:7]) & 0xFFFF
    return (0x10000 - s) & 0xFFFF


def _dfplayer_packet(command: int, param: int = 0, feedback: int = 0) -> bytes:
    """Build a DFPlayer packet for command + 16-bit parameter."""
    high = (param >> 8) & 0xFF
    low = param & 0xFF
    data = [0xFF, 0x06, command & 0xFF, feedback & 0x01, high, low]
    chk = _dfplayer_checksum([0x7E] + data)
    return bytes([0x7E] + data + [(chk >> 8) & 0xFF, chk & 0xFF, 0xEF])


def _parse_dfplayer_frame(frame: bytes) -> dict[str, int] | None:
    """Parse a 10-byte DFPlayer frame."""
    if len(frame) != 10:
        return None
    if frame[0] != 0x7E or frame[9] != 0xEF:
        return None
    if frame[1] != 0xFF or frame[2] != 0x06:
        return None
    cmd = frame[3]
    feedback = frame[4]
    param_h = frame[5]
    param_l = frame[6]
    chk_h = frame[7]
    chk_l = frame[8]
    expected_chk = _dfplayer_checksum([0x7E, 0xFF, 0x06, cmd, feedback, param_h, param_l])
    got_chk = ((chk_h << 8) | chk_l) & 0xFFFF
    if expected_chk != got_chk:
        return None
    return {
        "command": cmd,
        "feedback": feedback,
        "param": ((param_h << 8) | param_l) & 0xFFFF,
    }


class AudioMP3:
    """
    DFPlayer Mini MP3 module interface.

    Plays tracks from SD card. Track 1 = countdown audio.
    """

    def __init__(self, port: str | None = None, dry_run: bool = False) -> None:
        """
        Initialize MP3 module.

        Args:
            port: Serial device path. Uses config default if None.
            dry_run: If True, play_track() is a no-op.
        """
        self._port = port if port is not None else MP3_SERIAL_PORT
        self._dry_run = dry_run
        self._ser: Any = None
        self._pi: Any = None
        self._bb_rx_open = False
        self._rx_buf = bytearray()

    def open(self) -> None:
        """Open MP3 transport (kernel serial or pigpio software UART)."""
        if self._dry_run:
            return
        if self._port:
            try:
                import serial

                self._ser = serial.Serial(self._port, MP3_BAUD, timeout=0.15)
            except (ImportError, OSError):
                self._ser = None
            return
        try:
            import pigpio
        except ImportError:
            self._pi = None
            return
        self._pi = pigpio.pi()
        if not getattr(self._pi, "connected", False):
            self._pi = None
            return
        # Optional RX line for DFPlayer feedback/queries.
        try:
            try:
                self._pi.bb_serial_read_close(MP3_RX_GPIO)
            except Exception:
                pass
            self._pi.bb_serial_read_open(MP3_RX_GPIO, MP3_BAUD, 8)
            self._bb_rx_open = True
        except Exception:
            self._bb_rx_open = False

    def close(self) -> None:
        """Close serial connection."""
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        if self._pi is not None:
            if self._bb_rx_open:
                try:
                    self._pi.bb_serial_read_close(MP3_RX_GPIO)
                except Exception:
                    pass
                self._bb_rx_open = False
            try:
                self._pi.stop()
            except Exception:
                pass
            self._pi = None
        self._rx_buf = bytearray()

    def play_track(self, track_num: int) -> None:
        """
        Play track by number (1-based).

        Args:
            track_num: Track index (1 = first file on SD).
        """
        if self._dry_run:
            return
        if self._ser is None and self._pi is None:
            self.open()
        self.send_command(0x03, param=max(1, int(track_num)), feedback=False)

    def stop(self) -> None:
        """Stop playback. (DFPlayer command 0x16.)"""
        if self._dry_run:
            return
        if self._ser is None and self._pi is None:
            self.open()
        self.send_command(0x16, param=0, feedback=False)

    def set_volume(self, volume: int) -> None:
        """Set playback volume to DFPlayer range 0..30."""
        if self._dry_run:
            return
        v = max(0, min(30, int(volume)))
        self.send_command(0x06, param=v, feedback=False)

    def query_volume(self, timeout_sec: float = 0.6) -> int | None:
        """Query current volume (requires RX feedback wiring)."""
        resp = self.send_command(0x43, param=0, feedback=True, expected_cmd=0x43, timeout_sec=timeout_sec)
        return None if resp is None else int(resp["param"])

    def query_status(self, timeout_sec: float = 0.6) -> int | None:
        """Query playback status code (requires RX feedback wiring)."""
        resp = self.send_command(0x42, param=0, feedback=True, expected_cmd=0x42, timeout_sec=timeout_sec)
        return None if resp is None else int(resp["param"])

    def query_tf_file_count(self, timeout_sec: float = 0.6) -> int | None:
        """Query total file count in TF card (requires RX feedback wiring)."""
        resp = self.send_command(0x48, param=0, feedback=True, expected_cmd=0x48, timeout_sec=timeout_sec)
        return None if resp is None else int(resp["param"])

    def send_command(
        self,
        command: int,
        param: int = 0,
        feedback: bool = False,
        expected_cmd: int | None = None,
        timeout_sec: float = 0.5,
    ) -> dict[str, int] | None:
        """Send a raw DFPlayer command; optionally wait for response."""
        if self._dry_run:
            return None
        if self._ser is None and self._pi is None:
            self.open()
        if self._ser is None and self._pi is None:
            return None
        packet = _dfplayer_packet(command=command, param=param, feedback=1 if feedback else 0)
        self._write_packet(packet)
        if not feedback:
            return None
        return self.read_response(expected_cmd=expected_cmd, timeout_sec=timeout_sec)

    def read_response(
        self,
        expected_cmd: int | None = None,
        timeout_sec: float = 0.5,
    ) -> dict[str, int] | None:
        """Read one DFPlayer response frame, if available."""
        if self._dry_run:
            return None
        deadline = time.monotonic() + max(0.05, float(timeout_sec))
        while time.monotonic() < deadline:
            self._pump_input()
            frame = self._pop_frame()
            while frame is not None:
                parsed = _parse_dfplayer_frame(frame)
                if parsed is not None and (expected_cmd is None or parsed["command"] == expected_cmd):
                    return parsed
                frame = self._pop_frame()
            time.sleep(0.01)
        return None

    def _write_packet(self, packet: bytes) -> None:
        """Write packet over kernel serial or pigpio TX wave serial."""
        if self._ser is not None:
            self._ser.write(packet)
            return
        if self._pi is not None:
            self._send_soft_uart(packet)

    def _send_soft_uart(self, packet: bytes) -> None:
        """Send bytes on MP3_TX_GPIO via pigpio wave serial."""
        if self._pi is None:
            return
        self._pi.wave_clear()
        self._pi.wave_add_serial(MP3_TX_GPIO, MP3_BAUD, packet)
        wid = self._pi.wave_create()
        if wid < 0:
            return
        self._pi.wave_send_once(wid)
        while self._pi.wave_tx_busy():
            time.sleep(0.001)
        self._pi.wave_delete(wid)
        # Give DFPlayer time to process and potentially answer.
        time.sleep(0.03)

    def _pump_input(self) -> None:
        """Read available RX bytes into local buffer."""
        if self._ser is not None:
            try:
                waiting = getattr(self._ser, "in_waiting", 0)
            except Exception:
                waiting = 0
            read_size = max(1, int(waiting)) if waiting else 1
            try:
                data = self._ser.read(read_size)
            except Exception:
                data = b""
            if data:
                self._rx_buf.extend(data)
            return
        if self._pi is not None and self._bb_rx_open:
            try:
                count, data = self._pi.bb_serial_read(MP3_RX_GPIO)
            except Exception:
                return
            if count > 0 and data:
                self._rx_buf.extend(data)

    def _pop_frame(self) -> bytes | None:
        """Pop next complete DFPlayer 10-byte frame from buffer."""
        if not self._rx_buf:
            return None
        try:
            start = self._rx_buf.index(0x7E)
        except ValueError:
            self._rx_buf.clear()
            return None
        if start > 0:
            del self._rx_buf[:start]
        if len(self._rx_buf) < 10:
            return None
        frame = bytes(self._rx_buf[:10])
        del self._rx_buf[:10]
        if frame[-1] != 0xEF:
            # Realign to next frame marker if this one is malformed.
            return self._pop_frame()
        return frame


def _dfplayer_play_packet(track: int) -> bytes:
    """Build DFPlayer play packet for a track."""
    return _dfplayer_packet(command=0x03, param=max(1, int(track)), feedback=0)


def _dfplayer_stop_packet() -> bytes:
    """Build DFPlayer stop packet."""
    return _dfplayer_packet(command=0x16, param=0, feedback=0)
