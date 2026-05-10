"""
Audio I/O — microphone capture + overlapping sliding-window producer.

Opens the default system microphone via sounddevice, buffers samples into a
numpy circular ring buffer, and every HOP_SIZE_S seconds slices a
WINDOW_SAMPLES-length chunk and places it on an asyncio Queue.  Each chunk is
wrapped in a RawChunk dataclass so the orchestrator can fan it out to SED and
DOA without coupling those modules to sounddevice internals.

Performance notes:
- A numpy float32 ring buffer is used instead of a Python deque so that the
  audio callback copies raw C memory rather than boxing 16 000 Python floats.
- blocksize is fixed to hop_samples so the callback fires exactly once per hop,
  keeping the while-loop a straight single-pass with no branching.
- All asyncio queue operations are scheduled via call_soon_threadsafe from the
  sounddevice C thread; the event loop is never blocked.

Everything stays fully local — no network I/O of any kind.
"""
from __future__ import annotations

import asyncio
import time

import numpy as np
import sounddevice as sd

from contracts.config import HOP_SIZE_S, SAMPLE_RATE, WINDOW_SAMPLES, WINDOW_SIZE_S
from contracts.types import RawChunk

_BUF_SIZE = WINDOW_SAMPLES * 4   # 4 seconds of history (64 000 samples)


async def start() -> asyncio.Queue[RawChunk]:
    """
    Open the microphone and begin producing RawChunk objects.

    Returns an asyncio.Queue that will receive one RawChunk every HOP_SIZE_S.
    The caller must keep a reference to the queue and consume it; the producer
    runs as a background asyncio task.

    The queue is bounded at 32 items so that a slow consumer causes back-
    pressure rather than unbounded memory growth.
    """
    queue: asyncio.Queue[RawChunk] = asyncio.Queue(maxsize=32)
    loop = asyncio.get_running_loop()

    hop_samples = int(HOP_SIZE_S * SAMPLE_RATE)

    # Stereo numpy ring buffer — shape (BUF_SIZE, 2).
    # Storing stereo avoids a separate buffer for DOA while keeping SED on
    # channel-0 mono (extracted when the window is sliced out).
    _buf = np.zeros((_BUF_SIZE, 2), dtype=np.float32)
    _write_pos: list[int] = [0]
    _total_written: list[int] = [0]
    _window_id: list[int] = [0]

    def _sd_callback(
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        # indata shape: (frames, 2) — both channels, view into sounddevice's buffer.
        wp = _write_pos[0]
        end = wp + frames

        if end <= _BUF_SIZE:
            # Fast path: no wrap-around.
            _buf[wp:end] = indata
        else:
            # Wrap-around: split the write across the buffer boundary.
            split = _BUF_SIZE - wp
            _buf[wp:] = indata[:split]
            _buf[:frames - split] = indata[split:]

        _write_pos[0] = end % _BUF_SIZE
        _total_written[0] += frames

        # With blocksize == hop_samples this fires exactly once per callback.
        if _total_written[0] < WINDOW_SAMPLES:
            return   # Buffer not yet full enough for a complete window.

        # Extract the most recent WINDOW_SAMPLES from the ring buffer.
        wp = _write_pos[0]
        start_idx = (wp - WINDOW_SAMPLES) % _BUF_SIZE
        if start_idx + WINDOW_SAMPLES <= _BUF_SIZE:
            # Contiguous slice — single copy.
            stereo_window = _buf[start_idx:start_idx + WINDOW_SAMPLES].copy()
        else:
            # Wrap-around slice — two copies joined.
            tail_len = _BUF_SIZE - start_idx
            stereo_window = np.empty((WINDOW_SAMPLES, 2), dtype=np.float32)
            stereo_window[:tail_len] = _buf[start_idx:]
            stereo_window[tail_len:] = _buf[:WINDOW_SAMPLES - tail_len]

        raw = RawChunk(
            audio=stereo_window[:, 0],   # channel-0 mono for SED
            stereo_audio=stereo_window,  # both channels for DOA
            sample_rate=SAMPLE_RATE,
            timestamp=time.time() - WINDOW_SIZE_S,
            window_id=_window_id[0],
        )
        _window_id[0] += 1

        # Hand off to the asyncio event loop without blocking the audio thread.
        loop.call_soon_threadsafe(_put_latest, raw)

    def _put_latest(raw: RawChunk) -> None:
        """
        Put the newest chunk on the asyncio queue.

        This runs on the event-loop thread. If downstream inference falls
        behind, stale chunks are discarded so live mode stays live instead of
        replaying old audio later.
        """
        if queue.full():
            try:
                queue.get_nowait()
                queue.task_done()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(raw)
        except asyncio.QueueFull:
            pass

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=2,
        dtype="float32",
        blocksize=hop_samples,   # callback fires exactly once per hop
        callback=_sd_callback,
    )
    stream.start()

    # Keep the stream alive by storing it on the queue object itself.
    # The caller owns the queue; as long as it is referenced the stream lives.
    queue._sd_stream = stream  # type: ignore[attr-defined]

    return queue
