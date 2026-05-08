"""
VLC-based embedded video player widget for PyQt5.
Replaces QMediaPlayer to avoid Windows DirectShow errors.
Properly handles HLS/M3U8 streams and embeds directly in PyQt5.
"""
import sys
import os
try:
    import vlc
    VLC_AVAILABLE = True
except (ImportError, OSError):
    VLC_AVAILABLE = False
    vlc = None

from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt, QSize, QRect
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel, QWidget, QVBoxLayout
import ctypes
from snekbooru_linux.common.constants import USER_AGENT


class VLCPlayerThread(QThread):
    """Thread to handle VLC media playback with proper signal emission."""
    position_changed = pyqtSignal(int)  # Position in milliseconds
    duration_changed = pyqtSignal(int)  # Duration in milliseconds
    state_changed = pyqtSignal(str)  # 'playing', 'paused', 'stopped'
    error = pyqtSignal(str)
    
    def __init__(self, media_url, hwnd=None):
        super().__init__()
        self.media_url = media_url
        self.hwnd = hwnd
        self.instance = None
        self.player = None
        self.media = None
        self.mp = None
        
        self.is_running = True
        self.duration = 0
        self.position = 0
        self.current_state = 'stopped'
        self.last_state = None
        self._current_volume = 100  # Track volume state
        
    def run(self):
        if not VLC_AVAILABLE:
            if sys.platform == 'win32':
                self.error.emit("VLC Media Player not found or incompatible. Please install the 64-bit version of VLC.")
            else:
                self.error.emit("VLC Media Player not found. Please install VLC (libvlc) via your package manager (e.g., sudo apt install vlc).")
            return

        try:
            # Create VLC instance with embedded output
            # Use software decoding for local files and set reasonable caching
            instance_args = [
                '--vout=direct3d',
                '--aout=waveout',  # Enable Windows audio output
                '--avcodec-hw=none',  # Disable hardware video decoding for reliability
                '--file-caching=1000'  # Moderate file caching for local files
            ] if sys.platform == 'win32' else []
            self.instance = vlc.Instance(*instance_args)
            self.player = self.instance.media_list_player_new()
            media_list = self.instance.media_list_new()
            self.player.set_media_list(media_list)
            
            # Create media
            self.media = self.instance.media_new(self.media_url)
            if isinstance(self.media_url, str) and self.media_url.startswith(("http://", "https://")):
                self.media.add_option(f":http-user-agent={USER_AGENT}")
                if "gelbooru" in self.media_url:
                    self.media.add_option(":http-referrer=https://gelbooru.com/")
                self.media.add_option(":network-caching=2000")
            media_list.add_media(self.media)
            
            # Get the underlying media player
            self.mp = self.player.get_media_player()
            
            # Set window for embedded playback
            if self.hwnd:
                if sys.platform == 'win32':
                    self.mp.set_hwnd(self.hwnd)
                elif sys.platform == 'linux':
                    self.mp.set_xwindow(self.hwnd)
            
            # Start playback
            self.player.play()
            
            # Poll for state changes and position updates
            while self.is_running:
                if self.player and self.mp:
                    state = self.mp.get_state()
                    
                    # Convert VLC state to readable state
                    if state == vlc.State.Playing:
                        new_state = 'playing'
                    elif state == vlc.State.Paused:
                        new_state = 'paused'
                    elif state == vlc.State.Stopped or state == vlc.State.NothingSpecial:
                        new_state = 'stopped'
                    else:
                        new_state = 'stopped'
                    
                    if new_state != self.last_state:
                        self.last_state = new_state
                        self.state_changed.emit(new_state)
                    
                    # Get duration and position
                    current_duration = self.mp.get_length()
                    current_position = self.mp.get_time()
                    
                    if current_duration > 0 and current_duration != self.duration:
                        self.duration = current_duration
                        self.duration_changed.emit(current_duration)
                    
                    if current_position >= 0 and current_position != self.position:
                        self.position = current_position
                        self.position_changed.emit(current_position)
                
                self.msleep(100)
                
        except Exception as e:
            self.error.emit(str(e))
    
    def pause(self):
        if self.player:
            self.player.pause()
    
    def resume(self):
        if self.player:
            self.player.play()
    
    def play(self):
        if self.player:
            self.player.play()
    
    def stop(self):
        self.is_running = False
        if self.player:
            self.player.stop()
        self.wait()
    
    def seek(self, position_ms):
        """Seek to a specific position in milliseconds."""
        if self.mp:
            self.mp.set_time(int(position_ms))
    
    def set_volume(self, volume):
        """Set volume (0-100)."""
        if self.mp:
            self.mp.audio_set_volume(int(volume))
            self._current_volume = int(volume)
    
    def toggle_mute(self):
        """Toggle mute state."""
        if self.mp:
            self.mp.audio_toggle_mute()
    
    def is_muted(self):
        """Check if audio is muted."""
        if self.mp:
            return self.mp.audio_get_mute()
        return False


class VLCVideoPlayer(QWidget):
    """VLC-based embedded video player widget for PyQt5. Handles local files and HLS streams."""
    
    # Signals for state changes
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    state_changed = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.media_url = None
        self.player_thread = None
        self.is_playing = False
        self.hwnd = None
        self.is_fullscreen = False
        self.normal_geometry = None
        
        # UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create a native widget for VLC to embed in
        self.video_widget = QWidget()
        self.video_widget.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_widget)
        
        self.setLayout(layout)
        
        # Get window handle for embedding VLC
        if sys.platform == 'win32' or sys.platform == 'linux':
            self.hwnd = int(self.video_widget.winId())
    
    def load(self, media_url):
        """Load a media file or stream URL."""
        if isinstance(media_url, str):
            media_url = media_url.strip().replace("\\", "/")
            if media_url.startswith("//"):
                media_url = "https:" + media_url
        self.media_url = media_url
        self.stop()
    
    def play(self):
        """Start playing the media."""
        if not self.media_url:
            return
        
        if self.player_thread is None:
            self.player_thread = VLCPlayerThread(self.media_url, self.hwnd)
            self.player_thread.position_changed.connect(self.on_position_changed)
            self.player_thread.duration_changed.connect(self.on_duration_changed)
            self.player_thread.state_changed.connect(self.on_state_changed)
            self.player_thread.error.connect(self.on_error)
        
        self.player_thread.resume()
        if not self.player_thread.isRunning():
            self.player_thread.start()
        self.is_playing = True
    
    def pause(self):
        """Pause the media."""
        if self.player_thread:
            self.player_thread.pause()
        self.is_playing = False
    
    def stop(self):
        """Stop the media."""
        if self.player_thread:
            self.player_thread.stop()
            self.player_thread = None
        self.is_playing = False
    
    def seek(self, position_ms):
        """Seek to a specific position in milliseconds."""
        if self.player_thread:
            self.player_thread.seek(position_ms)
    
    def set_volume(self, volume):
        """Set volume (0-100)."""
        if self.player_thread:
            self.player_thread.set_volume(volume)
    
    def toggle_mute(self):
        """Toggle mute state."""
        if self.player_thread:
            self.player_thread.toggle_mute()
    
    def is_muted(self):
        """Check if audio is muted."""
        if self.player_thread:
            return self.player_thread.is_muted()
        return False
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        if self.is_fullscreen:
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()
    
    def enter_fullscreen(self):
        """Enter fullscreen mode."""
        if not self.is_fullscreen:
            self.normal_geometry = self.geometry()
            # Get the parent window and go fullscreen
            top_widget = self.window()
            top_widget.showFullScreen()
            self.is_fullscreen = True
    
    def exit_fullscreen(self):
        """Exit fullscreen mode."""
        if self.is_fullscreen:
            top_widget = self.window()
            top_widget.showNormal()
            if self.normal_geometry:
                top_widget.setGeometry(self.normal_geometry)
            self.is_fullscreen = False
    
    def on_position_changed(self, pos_ms):
        """Handle position changes."""
        self.position_changed.emit(pos_ms)
    
    def on_duration_changed(self, duration_ms):
        """Handle duration changes."""
        self.duration_changed.emit(duration_ms)
    
    def on_state_changed(self, state):
        """Handle state changes."""
        self.state_changed.emit(state)
    
    def on_error(self, error_msg):
        """Handle errors."""
        self.error.emit(error_msg)

