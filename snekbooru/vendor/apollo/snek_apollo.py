import ctypes
import os
import sys
import time

# C Struct Definitions

class SnekMediaInfo(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("duration_ms", ctypes.c_uint64),
        ("has_audio", ctypes.c_bool),
    ]

class SnekVideoFrame(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("data", ctypes.POINTER(ctypes.c_uint32)),
        ("data_len", ctypes.c_size_t),
        ("timestamp_ms", ctypes.c_uint64),
    ]

PLAYER_STATE_IDLE = 0
PLAYER_STATE_PLAYING = 1
PLAYER_STATE_PAUSED = 2
PLAYER_STATE_STOPPED = 3
PLAYER_STATE_END_OF_STREAM = 4
PLAYER_STATE_ERROR = 5

class SnekApolloPlayer:
    """
    Python wrapper for the SNEK_Apollo Rust multimedia framework.
    """
    def __init__(self, dll_path=None):
        if dll_path is None:
            # Default to checking the target/release directory
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dll_name = "snek_apollo.dll" if sys.platform == "win32" else "libsnek_apollo.so"
            dll_path = os.path.join(base_dir, dll_name)
            if not os.path.exists(dll_path):
                dll_path = os.path.join(base_dir, "target", "release", dll_name)
            
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"Could not find SNEK_Apollo shared library at {dll_path}")
            
        self.lib = ctypes.CDLL(dll_path)
        
        # Setup argument and return types for FFI functions
        self.lib.snek_create.argtypes = []
        self.lib.snek_create.restype = ctypes.c_void_p
        
        self.lib.snek_destroy.argtypes = [ctypes.c_void_p]
        self.lib.snek_destroy.restype = None
        
        self.lib.snek_open.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(SnekMediaInfo), ctypes.c_void_p]
        self.lib.snek_open.restype = ctypes.c_bool
        
        self.lib.snek_play.argtypes = [ctypes.c_void_p]
        self.lib.snek_play.restype = None
        
        self.lib.snek_pause.argtypes = [ctypes.c_void_p]
        self.lib.snek_pause.restype = None
        
        self.lib.snek_stop.argtypes = [ctypes.c_void_p]
        self.lib.snek_stop.restype = None
        
        self.lib.snek_seek.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        self.lib.snek_seek.restype = None

        self.lib.snek_seek_hls.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        self.lib.snek_seek_hls.restype = ctypes.c_bool
        
        self.lib.snek_set_volume.argtypes = [ctypes.c_void_p, ctypes.c_float]
        self.lib.snek_set_volume.restype = None
        
        self.lib.snek_set_mute.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self.lib.snek_set_mute.restype = None
        
        self.lib.snek_position_ms.argtypes = [ctypes.c_void_p]
        self.lib.snek_position_ms.restype = ctypes.c_uint64
        
        self.lib.snek_state.argtypes = [ctypes.c_void_p]
        self.lib.snek_state.restype = ctypes.c_uint8
        
        self.lib.snek_next_frame.argtypes = [ctypes.c_void_p, ctypes.POINTER(SnekVideoFrame)]
        self.lib.snek_next_frame.restype = ctypes.c_bool

        self.lib.snek_get_download_progress.argtypes = [ctypes.c_void_p]
        self.lib.snek_get_download_progress.restype = ctypes.c_float

        self.lib.snek_terminate.argtypes = []
        self.lib.snek_terminate.restype = None

        self.lib.snek_cleanup.argtypes = []
        self.lib.snek_cleanup.restype = None

        # Create the underlying Rust Player instance
        self.ptr = self.lib.snek_create()
        if not self.ptr:
            raise RuntimeError("Failed to create SNEK_Apollo Player")

    def __del__(self):
        if hasattr(self, 'ptr') and self.ptr:
            self.lib.snek_cleanup()
            self.lib.snek_destroy(self.ptr)
            self.ptr = None

    def terminate(self):
        """Instantly kill the backend process (useful if it hangs)"""
        self.lib.snek_cleanup()
        self.lib.snek_terminate()
        
    def cleanup(self):
        """Delete temporary files from disk"""
        self.lib.snek_cleanup()

    def open(self, url: str, hwnd: int = 0) -> dict:
        """
        Open a media stream. Blocks until the stream is ready to play.
        If hwnd is provided, the rust backend will use D3D11/Direct2D hardware rendering to draw the video directly.
        Returns a dict with media info: width, height, duration_ms, has_audio
        """
        info = SnekMediaInfo()
        success = self.lib.snek_open(self.ptr, url.encode('utf-8'), ctypes.byref(info), ctypes.c_void_p(hwnd))
        if not success:
            raise RuntimeError(f"Failed to open media URL: {url}")
            
        return {
            "width": info.width,
            "height": info.height,
            "duration_ms": info.duration_ms,
            "has_audio": info.has_audio
        }

    def play(self):
        self.lib.snek_play(self.ptr)

    def pause(self):
        self.lib.snek_pause(self.ptr)

    def stop(self):
        self.lib.snek_stop(self.ptr)

    def seek(self, ms: int):
        self.lib.snek_seek(self.ptr, ms)

    def seek_hls(self, ms: int) -> bool:
        return bool(self.lib.snek_seek_hls(self.ptr, ms))

    def set_volume(self, volume: float):
        """Set volume between 0.0 and 1.0"""
        self.lib.snek_set_volume(self.ptr, volume)

    def set_mute(self, mute: bool):
        self.lib.snek_set_mute(self.ptr, mute)

    def get_position_ms(self) -> int:
        return self.lib.snek_position_ms(self.ptr)

    def get_download_progress(self) -> float:
        return self.lib.snek_get_download_progress(self.ptr)

    def get_state(self) -> int:
        return self.lib.snek_state(self.ptr)

    def next_frame(self):
        """
        Returns a tuple of (width, height, raw_bytes, timestamp_ms) or None if no frame is ready.
        The raw_bytes can be directly converted into a NumPy array or used in PyQt/Tkinter.
        """
        frame = SnekVideoFrame()
        if self.lib.snek_next_frame(self.ptr, ctypes.byref(frame)):
            # For 0x00RRGGBB, this is 4 bytes per pixel.
            ArrayType = ctypes.c_uint32 * frame.data_len
            buf = ArrayType.from_address(ctypes.addressof(frame.data.contents))
            return (frame.width, frame.height, bytes(buf), frame.timestamp_ms)
        return None

# --- Example Usage ---
if __name__ == "__main__":
    print("Initializing SNEK_Apollo FFI wrapper...")
    try:
        player = SnekApolloPlayer()
    except FileNotFoundError as e:
        print(e)
        print("Make sure you run `cargo build --release` first!")
        sys.exit(1)
        
    url = "https://stream-akamai.castr.com/5b9352dbda7b8c769937e459/live_2361c920455111ea85db6911fe397b9e/index.fmp4.m3u8"
    print(f"Opening: {url}")
    
    info = player.open(url)
    print(f"Media Info: {info.width}x{info.height}, Duration: {info.duration_ms}ms, Audio: {info.has_audio}")
    
    has_ui = False
    try:
        import cv2
        import numpy as np
        has_ui = True
        print("OpenCV found! Visual rendering enabled.")
        window_name = "SNEK_Apollo Python FFI Demo"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    except ImportError:
        print("Note: Install 'opencv-python' and 'numpy' to see the actual video window.")
        print("Running in headless simulation mode...")

    player.play()
    
    start_time = time.time()
    frames_rendered = 0
    volume = 1.0
    is_muted = False
    
    while True:
        frame_data = player.next_frame()
        if frame_data:
            w, h, data, pts = frame_data
            frames_rendered += 1
            
            if has_ui:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    print("Window closed by user.")
                    player.terminate()
                    break

                arr = np.frombuffer(data, dtype=np.uint8).reshape((h, w, 4))
                # SNEK_Apollo outputs 0x00RRGGBB (little endian: B, G, R, 0)
                bgr_frame = arr[:, :, :3]
                
                cv2.imshow(window_name, bgr_frame)
                
                key = cv2.waitKeyEx(1)
                
                if key == 27: # ESC
                    print("ESC pressed, terminating.")
                    player.terminate()
                    break
                elif key == 32: # Space
                    state = player.get_state()
                    if state == PLAYER_STATE_PLAYING:
                        player.pause()
                    else:
                        player.play()
                elif key in [109, 77]: # 'm' or 'M'
                    is_muted = not is_muted
                    player.set_mute(is_muted)
                elif key in [2424832, 65361]: # Left Arrow (Windows / Linux)
                    pos = max(0, player.get_position_ms() - 10000)
                    player.seek(pos)
                elif key in [2555904, 65363]: # Right Arrow (Windows / Linux)
                    pos = player.get_position_ms() + 10000
                    player.seek(pos)
                elif key in [2490368, 65362]: # Up Arrow
                    volume = min(1.0, volume + 0.1)
                    player.set_volume(volume)
                elif key in [2621440, 65364]: # Down Arrow
                    volume = max(0.0, volume - 0.1)
                    player.set_volume(volume)
            
        state = player.get_state()
        if state == PLAYER_STATE_END_OF_STREAM:
            break
            
        if not has_ui and time.time() - start_time > 5.0:
            print("Simulated 5 seconds. Exiting.")
            break
            
        if not has_ui:
            time.sleep(0.01)
        
    print(f"Rendered {frames_rendered} frames via Python FFI.")
    if has_ui:
        cv2.destroyAllWindows()
    player.terminate()
    print("Done.")
