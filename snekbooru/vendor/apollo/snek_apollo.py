import ctypes
import os
import sys
import time

# --- C Struct Definitions ---

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

class SnekUpscaleStats(ctypes.Structure):
    _fields_ = [
        ("frames_processed", ctypes.c_uint64),
        ("scene_cuts", ctypes.c_uint64),
        ("duplicate_frames", ctypes.c_uint64),
        ("temporal_blocks_used", ctypes.c_uint64),
        ("temporal_blocks_total", ctypes.c_uint64),
        ("output_width", ctypes.c_uint32),
        ("output_height", ctypes.c_uint32),
        ("last_noise_score", ctypes.c_float),
        ("last_blocking_score", ctypes.c_float),
        ("smear_frames", ctypes.c_uint64),
    ]

UPSCALE_OFF = 0
UPSCALE_SPATIAL = 1
UPSCALE_SPATIAL_TEMPORAL = 2
YUV_MATRIX_AUTO = 0
YUV_MATRIX_BT601 = 1
YUV_MATRIX_BT709 = 2
YUV_RANGE_AUTO = 0
YUV_RANGE_LIMITED = 1
YUV_RANGE_FULL = 2

# PlayerState enum matching Rust
PLAYER_STATE_IDLE = 0
PLAYER_STATE_PLAYING = 1
PLAYER_STATE_PAUSED = 2
PLAYER_STATE_STOPPED = 3
PLAYER_STATE_END_OF_STREAM = 4
PLAYER_STATE_ERROR = 5

class SnekApolloPlayer:
    def __init__(self, dll_path=None):
        if dll_path is None:
            # Default to checking the target/release directory
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dll_name = "snek_apollo.dll" if sys.platform == "win32" else "libsnek_apollo.so"
            candidates = (os.path.join(base_dir, dll_name),
                          os.path.join(base_dir, "target", "release", dll_name))
            dll_path = next((path for path in candidates if os.path.exists(path)), candidates[0])
            
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

        self.lib.snek_configure_upscaler.argtypes = [
            ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_uint8,
            ctypes.c_float, ctypes.c_uint8,
            ctypes.c_float, ctypes.c_uint8, ctypes.c_uint8,
        ]
        self.lib.snek_configure_upscaler.restype = ctypes.c_bool

        self.lib.snek_get_upscale_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(SnekUpscaleStats)]
        self.lib.snek_get_upscale_stats.restype = ctypes.c_bool

        self.lib.snek_set_smear.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_float]
        self.lib.snek_set_smear.restype = ctypes.c_bool

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
        self.lib.snek_cleanup()
        self.lib.snek_terminate()
        
    def cleanup(self):
        self.lib.snek_cleanup()

    def open(self, url: str, hwnd: int = 0) -> dict:
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
        self.lib.snek_set_volume(self.ptr, volume)

    def set_mute(self, mute: bool):
        self.lib.snek_set_mute(self.ptr, mute)

    def get_position_ms(self) -> int:
        return self.lib.snek_position_ms(self.ptr)

    def get_download_progress(self) -> float:
        return self.lib.snek_get_download_progress(self.ptr)

    def get_state(self) -> int:
        return self.lib.snek_state(self.ptr)

    def configure_upscaler(self, mode="temporal", target_width=0, target_height=0,
                           max_scale=2.0, detail_strength=None,
                           temporal_strength=None, motion_search=None,
                           history_frames=None, deblock_strength=None,
                           scene_change_threshold=28.0, color_range="auto",
                           matrix="auto", quality="insane"):
        modes = {"off": UPSCALE_OFF, "spatial": UPSCALE_SPATIAL,
                 "temporal": UPSCALE_SPATIAL_TEMPORAL,
                 "spatial_temporal": UPSCALE_SPATIAL_TEMPORAL}
        matrices = {"auto": YUV_MATRIX_AUTO, "bt601": YUV_MATRIX_BT601,
                    "bt.601": YUV_MATRIX_BT601, "bt709": YUV_MATRIX_BT709,
                    "bt.709": YUV_MATRIX_BT709}
        ranges = {"auto": YUV_RANGE_AUTO, "limited": YUV_RANGE_LIMITED,
                  "tv": YUV_RANGE_LIMITED, "full": YUV_RANGE_FULL,
                  "pc": YUV_RANGE_FULL}
        presets = {
            "balanced": (0.55, 0.35, 4, 3, 0.25),
            "insane": (0.72, 0.48, 6, 5, 0.40),
        }
        quality = quality.lower()
        if quality not in presets:
            raise ValueError("quality must be 'balanced' or 'insane'")
        preset = presets[quality]
        detail_strength = preset[0] if detail_strength is None else detail_strength
        temporal_strength = preset[1] if temporal_strength is None else temporal_strength
        motion_search = preset[2] if motion_search is None else motion_search
        history_frames = preset[3] if history_frames is None else history_frames
        deblock_strength = preset[4] if deblock_strength is None else deblock_strength
        if target_width < 0 or target_height < 0:
            raise ValueError("Target dimensions cannot be negative")
        if not 0 <= motion_search <= 12:
            raise ValueError("motion_search must be between 0 and 12")
        if not 1 <= history_frames <= 5:
            raise ValueError("history_frames must be between 1 and 5")
        try:
            mode_value = modes[mode.lower()] if isinstance(mode, str) else int(mode)
            matrix_value = matrices[matrix.lower()] if isinstance(matrix, str) else int(matrix)
            range_value = ranges[color_range.lower()] if isinstance(color_range, str) else int(color_range)
        except (KeyError, ValueError) as exc:
            raise ValueError("Invalid upscaler mode, YUV matrix, or color range") from exc
        ok = self.lib.snek_configure_upscaler(
            self.ptr, mode_value, target_width, target_height, max_scale,
            detail_strength, temporal_strength, history_frames, deblock_strength, motion_search,
            scene_change_threshold, range_value, matrix_value,
        )
        if not ok:
            raise RuntimeError("Failed to configure upscaler")

    def get_upscale_stats(self) -> dict:
        stats = SnekUpscaleStats()
        if not self.lib.snek_get_upscale_stats(self.ptr, ctypes.byref(stats)):
            raise RuntimeError("Failed to read upscaler statistics")
        total = stats.temporal_blocks_total
        return {
            "frames_processed": stats.frames_processed,
            "scene_cuts": stats.scene_cuts,
            "duplicate_frames": stats.duplicate_frames,
            "temporal_blocks_used": stats.temporal_blocks_used,
            "temporal_blocks_total": total,
            "temporal_acceptance": stats.temporal_blocks_used / total if total else 0.0,
            "output_width": stats.output_width,
            "output_height": stats.output_height,
            "noise_score": stats.last_noise_score,
            "blocking_score": stats.last_blocking_score,
            "smear_frames": stats.smear_frames,
        }

    def set_smear(self, enabled=True, hold_frames=None, strength=None):
        if not enabled:
            hold_frames = 0
        else:
            hold_frames = 3 if hold_frames is None else hold_frames
        strength = 0.6 if strength is None else strength
        if not 0 <= hold_frames <= 8:
            raise ValueError("hold_frames must be between 0 and 8")
        if not 0.0 <= strength <= 1.0:
            raise ValueError("strength must be between 0.0 and 1.0")
        ok = self.lib.snek_set_smear(self.ptr, hold_frames, strength)
        if not ok:
            raise RuntimeError("Failed to configure smear frames")

    def next_frame(self):
        frame = SnekVideoFrame()
        if self.lib.snek_next_frame(self.ptr, ctypes.byref(frame)):
            # Cast the pointer to an array of uint32, then get bytes
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
    
    # Try to import cv2 and numpy for visual rendering
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
                # Check if user clicked the 'X' button
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    print("Window closed by user.")
                    player.terminate()
                    break

                # Convert raw bytes to numpy array
                arr = np.frombuffer(data, dtype=np.uint8).reshape((h, w, 4))
                # SNEK_Apollo outputs 0x00RRGGBB (little endian: B, G, R, 0)
                bgr_frame = arr[:, :, :3]
                
                cv2.imshow(window_name, bgr_frame)
                
                # Handle Keyboard inputs via waitKeyEx to support Arrow Keys
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
    # Using terminate() instead of stop() for immediate exit without hangs
    player.terminate()
    print("Done.")
