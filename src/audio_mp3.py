"""
SmartShell — DFPlayer Mini MP3 module for countdown audio.

Plays pre-recorded countdown during the cancellation window.
See docs/features/04_audio_mp3.md.
"""

from __future__ import annotations

from typing import Any

from src.config import MP3_BAUD, MP3_SERIAL_PORT, MP3_TX_GPIO


def _dfplayer_checksum(data: list[int]) -> int:
    """Compute DFPlayer Mini checksum: -Sum(bytes 1..6) as 16-bit."""
    s = sum(data[1:7]) & 0xFFFF
    return (0x10000 - s) & 0xFFFF


def _dfplayer_send_play(ser: Any, track: int) -> None:
    """Send DFPlayer Mini play command for track (1-based)."""
    high = (track >> 8) & 0xFF
    low = track & 0xFF
    data = [0xFF, 0x06, 0x03, 0x00, high, low]
    chk = _dfplayer_checksum([0x7E] + data)
    chk_h = (chk >> 8) & 0xFF
    chk_l = chk & 0xFF
    packet = bytes([0x7E] + data + [chk_h, chk_l, 0xEF])
    ser.write(packet)


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

    def open(self) -> None:
        """Open MP3 output transport (kernel serial or pigpio GPIO software UART TX)."""
        if self._dry_run:
            return
        if self._port:
            try:
                import serial

                self._ser = serial.Serial(self._port, MP3_BAUD, timeout=0.5)
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

    def close(self) -> None:
        """Close serial connection."""
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        if self._pi is not None:
            try:
                self._pi.stop()
            except Exception:
                pass
            self._pi = None

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
        if self._ser is not None:
            _dfplayer_send_play(self._ser, track_num)
        elif self._pi is not None:
            packet = _dfplayer_play_packet(track_num)
            self._send_soft_uart(packet)

    def stop(self) -> None:
        """Stop playback. (DFPlayer command 0x16.)"""
        if self._dry_run:
            return
        if self._ser is None and self._pi is None:
            self.open()
        packet = _dfplayer_stop_packet()
        if self._ser is not None:
            self._ser.write(packet)
        elif self._pi is not None:
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
            pass
        self._pi.wave_delete(wid)


def _dfplayer_play_packet(track: int) -> bytes:
    """Build DFPlayer play packet for a track."""
    high = (track >> 8) & 0xFF
    low = track & 0xFF
    data = [0xFF, 0x06, 0x03, 0x00, high, low]
    chk = _dfplayer_checksum([0x7E] + data)
    return bytes([0x7E] + data + [(chk >> 8) & 0xFF, chk & 0xFF, 0xEF])


def _dfplayer_stop_packet() -> bytes:
    """Build DFPlayer stop packet."""
    data = [0xFF, 0x06, 0x16, 0x00, 0, 0]
    chk = _dfplayer_checksum([0x7E] + data)
    return bytes([0x7E] + data + [(chk >> 8) & 0xFF, chk & 0xFF, 0xEF])
