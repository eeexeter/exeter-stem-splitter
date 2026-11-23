import ctypes
from ctypes import wintypes
from threading import RLock, Thread
from time import monotonic, sleep
import wave


class WaveFormat(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("format_tag", wintypes.WORD),
        ("channels", wintypes.WORD),
        ("sample_rate", wintypes.DWORD),
        ("bytes_per_second", wintypes.DWORD),
        ("block_align", wintypes.WORD),
        ("bits_per_sample", wintypes.WORD),
        ("extra_size", wintypes.WORD),
    ]


class WaveHeader(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("length", wintypes.DWORD),
        ("bytes_recorded", wintypes.DWORD),
        ("user", ctypes.c_size_t),
        ("flags", wintypes.DWORD),
        ("loops", wintypes.DWORD),
        ("next", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


class MultimediaTime(ctypes.Structure):
    _fields_ = [("kind", wintypes.UINT), ("value", wintypes.DWORD), ("reserved", wintypes.DWORD)]


winmm = ctypes.WinDLL("winmm")
wave_format_pointer = ctypes.POINTER(WaveFormat)
wave_header_pointer = ctypes.POINTER(WaveHeader)
winmm.waveOutOpen.argtypes = (
    ctypes.POINTER(wintypes.HANDLE), wintypes.UINT, wave_format_pointer,
    ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD,
)
winmm.waveOutOpen.restype = wintypes.UINT
winmm.waveOutGetErrorTextW.argtypes = (wintypes.UINT, wintypes.LPWSTR, wintypes.UINT)
winmm.waveOutGetErrorTextW.restype = wintypes.UINT
winmm.waveOutGetPosition.argtypes = (wintypes.HANDLE, ctypes.POINTER(MultimediaTime), wintypes.UINT)
winmm.waveOutGetPosition.restype = wintypes.UINT
for operation in (winmm.waveOutPrepareHeader, winmm.waveOutWrite, winmm.waveOutUnprepareHeader):
    operation.argtypes = (wintypes.HANDLE, wave_header_pointer, wintypes.UINT)
    operation.restype = wintypes.UINT
for operation in (winmm.waveOutPause, winmm.waveOutRestart, winmm.waveOutReset, winmm.waveOutClose):
    operation.argtypes = (wintypes.HANDLE,)
    operation.restype = wintypes.UINT

WAVE_MAPPER = 0xFFFFFFFF
BUFFER_DONE = 1
BUFFER_COUNT = 4
WAVE_BAD_FORMAT = 32
TIME_MS = 1
TIME_SAMPLES = 2
TIME_BYTES = 4


def check(error):
    if error:
        message = ctypes.create_unicode_buffer(256)
        winmm.waveOutGetErrorTextW(error, message, len(message))
        raise OSError(message.value or f"Windows audio error {error}.")


class StemPlayer:
    def __init__(self):
        self.lock = RLock()
        self.stream_thread = None
        self.stream_error = None
        self.source = None
        self.state = "idle"
        self.reader = None
        self.handle = None
        self.buffers = []
        self.eof = False
        self.use_pcm16 = False
        self.start_frame = 0
        self.frame_bytes = 0
        self.position_frame = 0
        self.clock_frame = 0
        self.clock_started = 0.0

    @property
    def duration(self):
        return self.reader.getnframes() / self.reader.getframerate() if self.source is not None else 0

    def play(self, source):
        with self.lock:
            if source == self.source:
                self.poll()
                if self.state == "ended":
                    self.set_frame(0, paused=False)
                elif self.state == "paused":
                    check(winmm.waveOutRestart(self.handle))
                    self.start_clock()
                    self.state = "playing"
                    self.start_stream()
                else:
                    check(winmm.waveOutPause(self.handle))
                    self.position()
                    self.state = "paused"
                return

            position = self.position() if self.state != "ended" else 0
            self.stop()
            try:
                self.reader = wave.open(str(source), "rb")
                channels = self.reader.getnchannels()
                rate = self.reader.getframerate()
                bits = self.reader.getsampwidth() * 8
                alignment = channels * (bits // 8)
                audio_format = WaveFormat(1, channels, rate, rate * alignment, alignment, bits, 0)
                handle = wintypes.HANDLE()
                error = winmm.waveOutOpen(ctypes.byref(handle), WAVE_MAPPER, ctypes.byref(audio_format), 0, 0, 0)
                if error == WAVE_BAD_FORMAT and bits == 24:
                    alignment = channels * 2
                    audio_format = WaveFormat(1, channels, rate, rate * alignment, alignment, 16, 0)
                    error = winmm.waveOutOpen(ctypes.byref(handle), WAVE_MAPPER, ctypes.byref(audio_format), 0, 0, 0)
                    self.use_pcm16 = not error
                check(error)
                self.handle = handle
                self.frame_bytes = alignment
                self.source = source
                frame = round(position * rate)
                self.set_frame(frame if frame < self.reader.getnframes() else 0, paused=False)
            except (OSError, wave.Error, EOFError) as exc:
                self.stop()
                raise OSError(str(exc) or "Couldn't read the WAV file.") from exc

    def fill_buffers(self):
        frame_count = max(1, self.reader.getframerate() // 8)
        while not self.eof and len(self.buffers) < BUFFER_COUNT:
            samples = self.reader.readframes(frame_count)
            if not samples:
                self.eof = True
                break
            if self.use_pcm16:
                pcm16 = bytearray(len(samples) // 3 * 2)
                pcm16[::2] = samples[1::3]
                pcm16[1::2] = samples[2::3]
                samples = bytes(pcm16)
            data = ctypes.create_string_buffer(samples, len(samples))
            header = WaveHeader(ctypes.addressof(data), len(data))
            size = ctypes.sizeof(header)
            check(winmm.waveOutPrepareHeader(self.handle, ctypes.byref(header), size))
            # Retain both objects until Windows finishes reading the buffer.
            self.buffers.append((header, data))
            check(winmm.waveOutWrite(self.handle, ctypes.byref(header), size))

    def start_stream(self):
        if self.stream_thread is None:
            self.stream_thread = Thread(target=self.stream_audio, daemon=True)
            self.stream_thread.start()

    def stream_audio(self):
        # A native Windows drag can block Tk's timers until the file is dropped.
        while True:
            with self.lock:
                if self.state != "playing":
                    self.stream_thread = None
                    return
                try:
                    while self.buffers and self.buffers[0][0].flags & BUFFER_DONE:
                        self.release_buffer()
                    self.fill_buffers()
                except (OSError, wave.Error, EOFError) as exc:
                    self.stream_error = OSError(str(exc) or "Couldn't continue playing the WAV file.")
                    self.stream_thread = None
                    return
                if self.eof and not self.buffers:
                    self.state = "ended"
                    self.stream_thread = None
                    return
            sleep(0.025)

    def poll(self):
        with self.lock:
            if self.stream_error:
                error, self.stream_error = self.stream_error, None
                raise error

    def position(self):
        with self.lock:
            if self.source is None:
                return 0
            if self.state == "ended":
                return self.duration
            rate = self.reader.getframerate()
            if self.state == "paused":
                return self.position_frame / rate
            time = MultimediaTime(TIME_SAMPLES)
            check(winmm.waveOutGetPosition(self.handle, ctypes.byref(time), ctypes.sizeof(time)))
            if time.kind == TIME_SAMPLES:
                frame = self.start_frame + time.value
            elif time.kind == TIME_BYTES:
                frame = self.start_frame + time.value // self.frame_bytes
            elif time.kind == TIME_MS:
                frame = self.start_frame + time.value * rate // 1000
            else:
                # Some drivers report another format. Count the completed buffers instead.
                queued_frames = sum(header.length // self.frame_bytes for header, _ in self.buffers)
                frame = self.reader.tell() - queued_frames
            # Discard backwards readings and ones ahead of what could have played since a reset.
            reachable = self.clock_frame + int((monotonic() - self.clock_started) * rate)
            self.position_frame = max(self.position_frame, min(frame, reachable, self.reader.tell()))
            return self.position_frame / rate

    def seek(self, seconds):
        with self.lock:
            if self.source is not None:
                frame = min(self.reader.getnframes(), max(0, round(seconds * self.reader.getframerate())))
                self.set_frame(frame, paused=self.state != "playing")
                return frame / self.reader.getframerate()

    def start_clock(self):
        self.clock_frame = self.position_frame
        self.clock_started = monotonic()

    def set_frame(self, frame, *, paused):
        self.reset_output()
        self.reader.setpos(frame)
        self.start_frame = frame
        self.position_frame = frame
        self.eof = frame == self.reader.getnframes()
        if self.eof:
            self.state = "ended"
            return
        if paused:
            check(winmm.waveOutPause(self.handle))
        else:
            check(winmm.waveOutRestart(self.handle))
            self.start_clock()
        self.state = "paused" if paused else "playing"
        self.fill_buffers()
        if not paused:
            self.start_stream()

    def release_buffer(self):
        header, _ = self.buffers[0]
        check(winmm.waveOutUnprepareHeader(self.handle, ctypes.byref(header), ctypes.sizeof(header)))
        self.buffers.pop(0)

    def reset_output(self):
        check(winmm.waveOutReset(self.handle))
        while self.buffers:
            self.release_buffer()

    def stop(self):
        with self.lock:
            self.source = None
            self.state = "idle"
            self.stream_error = None
            if self.handle:
                self.reset_output()
                check(winmm.waveOutClose(self.handle))
                self.handle = None
            if self.reader:
                self.reader.close()
                self.reader = None
            self.eof = False
            self.use_pcm16 = False
            self.start_frame = 0
