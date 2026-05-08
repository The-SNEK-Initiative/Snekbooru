import sys
import os
import threading
import time
from enum import Enum
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
from PyQt5.QtCore import pyqtSignal, QTimer, Qt

# Import the wrapper from our vendor directory
try:
    from snekbooru.vendor.apollo import (SnekApolloPlayer, PLAYER_STATE_IDLE,
                                         PLAYER_STATE_PLAYING, PLAYER_STATE_PAUSED, 
                                         PLAYER_STATE_STOPPED, PLAYER_STATE_END_OF_STREAM, 
                                         PLAYER_STATE_ERROR)
    APOLLO_AVAILABLE = True
except ImportError:
    APOLLO_AVAILABLE = False

class PlayerState(Enum):
    IDLE = "idle"
    OPENING = "opening"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    EOS = "eos"
    ERROR = "error"

class ApolloVideoPlayer(QWidget):
    """
    Snek Apollo based embedded video player widget for PyQt5.
    Replaces VLC and QMediaPlayer for high-performance Windows playback.
    """
    # Signals to match VLCVideoPlayer interface
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    state_changed = pyqtSignal(str) # 'playing', 'paused', 'stopped', 'error'
    error = pyqtSignal(str)
    download_progress = pyqtSignal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.media_url = None
        self.player = None
        self.hwnd = None
        self.duration_ms = 0
        self.video_width = 0
        self.video_height = 0
        
        # Internal state
        self._state = PlayerState.IDLE
        self._current_volume = 1.0 # 0.0 to 1.0
        self._is_muted = False
        self._last_emitted_duration = -1
        
        # UI Setup
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.video_widget = QWidget()
        self.video_widget.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_widget)
        
        self.loading_label = QLabel("Initializing Apollo Player...", self.video_widget)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("color: white; background: transparent; font-size: 14px; font-weight: bold;")
        self.loading_label.hide()
        
        # Get window handle for Direct2D rendering
        if sys.platform == 'win32':
            self.hwnd = int(self.video_widget.winId())
            
        # Initialization
        if APOLLO_AVAILABLE:
            try:
                self.player = SnekApolloPlayer()
            except Exception as e:
                self._change_state(PlayerState.ERROR)
                self.error.emit(f"Failed to initialize Apollo Player: {e}")
                self.player = None
        else:
            self._change_state(PlayerState.ERROR)
            self.error.emit("Snek Apollo SDK not found.")

        # Polling timer for position and state
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_player)
        
    @property
    def is_playing(self):
        return self._state == PlayerState.PLAYING

    def _change_state(self, new_state):
        if self._state == new_state:
            return
        
        old_state = self._state
        self._state = new_state
        print(f"[ApolloPlayer] State Change: {old_state.value} -> {new_state.value}")
        
        # Map to legacy string states for compatibility
        legacy_state_map = {
            PlayerState.PLAYING: "playing",
            PlayerState.PAUSED: "paused",
            PlayerState.STOPPED: "stopped",
            PlayerState.IDLE: "stopped",
            PlayerState.EOS: "stopped",
            PlayerState.ERROR: "error"
        }
        
        self.state_changed.emit(legacy_state_map.get(new_state, "stopped"))

    def load(self, media_url):
        """Load a media file or stream URL."""
        print(f"[ApolloPlayer] load: {media_url}")
        if not self.player:
            return
            
        if isinstance(media_url, str):
            media_url = media_url.strip().replace("\\", "/")
            if media_url.startswith("//"):
                media_url = "https:" + media_url

        # Stop any previous stream/timer
        self.exit()
        
        self.media_url = media_url
        self.duration_ms = 0
        self._last_emitted_duration = -1
        self._change_state(PlayerState.IDLE)
        
    def play(self):
        """Start playing the media."""
        if not self.player or not self.media_url:
            return
            
        if self._state == PlayerState.OPENING:
            return

        # If already playing or paused, just resume
        if self._state in [PlayerState.PLAYING, PlayerState.PAUSED]:
            try:
                self.player.play()
                self._change_state(PlayerState.PLAYING)
                self.poll_timer.start(100)
                return
            except Exception as e:
                print(f"[ApolloPlayer] Resume error: {e}")

        # If at end of stream or soft-stopped, seek to beginning and replay
        if self._state in [PlayerState.EOS, PlayerState.STOPPED]:
            if self.duration_ms > 0:
                try:
                    self.player.seek(0)
                    self.player.play()
                    self._change_state(PlayerState.PLAYING)
                    self.poll_timer.start(100)
                    return
                except Exception:
                    pass

        # Otherwise, open and play
        self._change_state(PlayerState.OPENING)
        self.loading_label.setText("Opening media...")
        self.loading_label.show()
        self._resize_loading_label()
        
        # Open in a separate thread to avoid UI freeze
        self.poll_timer.start(100) # Start polling early to show download progress
        threading.Thread(target=self._bg_open, daemon=True).start()
        
    def _bg_open(self):
        if not self.player: 
            self._change_state(PlayerState.ERROR)
            return
        try:
            # Blocks until metadata is ready
            info = self.player.open(self.media_url, self.hwnd or 0)
            self.duration_ms = info.get('duration_ms', 0)
            self.video_width = info.get('width', 0)
            self.video_height = info.get('height', 0)
            
            # Signal success back to main thread
            QTimer.singleShot(0, self._on_opened)
        except Exception as e:
            QTimer.singleShot(0, lambda: self._handle_open_error(str(e)))

    def _handle_open_error(self, error_msg):
        self._change_state(PlayerState.ERROR)
        self.loading_label.hide()
        self.error.emit(error_msg)

    def _on_opened(self):
        if not self.player: return
        self.loading_label.hide()
        
        # Force emit duration even if it's 0 (might be updated later)
        self._emit_duration()
        
        try:
            self.player.set_volume(self._current_volume)
            self.player.set_mute(self._is_muted)
            self.player.play()
            self._change_state(PlayerState.PLAYING)
            self._adjust_video_geometry()
        except Exception as e:
            self._change_state(PlayerState.ERROR)
            self.error.emit(f"Playback error: {e}")
            
    def _emit_duration(self):
        """Emit duration if it has changed."""
        if self.duration_ms != self._last_emitted_duration:
            self._last_emitted_duration = self.duration_ms
            self.duration_changed.emit(int(self.duration_ms))
        
    def pause(self):
        """Pause the media."""
        if self.player and self._state == PlayerState.PLAYING:
            try:
                self.player.pause()
                self._change_state(PlayerState.PAUSED)
            except Exception:
                pass
            
    def exit(self):
        """Stop the media."""
        self.poll_timer.stop()
        self.loading_label.hide()
        
        print("[ApolloPlayer] exit() called")
        if self.player:
            try:
                self.player.stop()
            except Exception:
                pass
        self._change_state(PlayerState.STOPPED)
        
    def seek(self, position_ms):
        """Seek to a specific position in milliseconds."""
        if self.player:
            try:
                self.player.seek(int(position_ms))
            except Exception:
                pass
            
    def set_volume(self, volume):
        """Set volume (0-100)."""
        self._current_volume = volume / 100.0
        if self.player:
            try:
                self.player.set_volume(self._current_volume)
            except Exception:
                pass
            
    def toggle_mute(self):
        """Toggle mute state."""
        self._is_muted = not self._is_muted
        if self.player:
            try:
                self.player.set_mute(self._is_muted)
            except Exception:
                pass
            
    def is_muted(self):
        """Check if audio is muted."""
        return self._is_muted
        
    def _poll_player(self):
        if not self.player:
            return
            
        state = self.player.get_state()
        pos_ms = self.player.get_position_ms()
        
        # Handle state transitions from backend
        if state == PLAYER_STATE_PLAYING:
            self._change_state(PlayerState.PLAYING)
            self.position_changed.emit(int(pos_ms))
        elif state == PLAYER_STATE_PAUSED:
            self._change_state(PlayerState.PAUSED)
        elif state == PLAYER_STATE_END_OF_STREAM:
            if self._state != PlayerState.EOS:
                self._change_state(PlayerState.EOS)
                self.poll_timer.stop()
        elif state == PLAYER_STATE_ERROR:
            self._change_state(PlayerState.ERROR)
            
        # Emit download progress (0.0 to 100.0)
        progress = self.player.get_download_progress() * 100.0
        self.download_progress.emit(progress)
        
        if self.loading_label.isVisible():
            if progress > 0:
                self.loading_label.setText(f"Loading: {progress:.1f}%")
            else:
                self.loading_label.setText("Opening media...")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_video_geometry()
        self._resize_loading_label()

    def _adjust_video_geometry(self):
        """Center and scale the video widget to maintain aspect ratio."""
        if self.video_width <= 0 or self.video_height <= 0:
            self.video_widget.setGeometry(self.rect())
            return

        container_width = self.width()
        container_height = self.height()
        
        if container_width <= 0 or container_height <= 0:
            return

        aspect_ratio = self.video_width / self.video_height
        
        # Calculate target dimensions
        target_width = container_width
        target_height = int(target_width / aspect_ratio)
        
        if target_height > container_height:
            target_height = container_height
            target_width = int(target_height * aspect_ratio)
            
        # Center the rect
        x = (container_width - target_width) // 2
        y = (container_height - target_height) // 2
        
        self.video_widget.setGeometry(x, y, target_width, target_height)
        
    def _resize_loading_label(self):
        if hasattr(self, 'loading_label'):
            self.loading_label.resize(self.video_widget.size())

    def closeEvent(self, event):
        self.exit()
        if self.player:
            try:
                self.player.terminate()
                self.player.cleanup()
            except Exception:
                pass
        event.accept()
