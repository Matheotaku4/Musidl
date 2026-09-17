#!/usr/bin/env python3
"""
CachyOS Music Downloader - A beautiful GUI application for downloading music from Tidal via hifi-api
Features:
- Search for tracks, albums, artists
- Download single tracks, albums, or entire artist discographies
- Organize downloads as: Artist/Artist - Album/track.flac + lyrics.lrc
- Fetch and embed album art
- Download lyrics (.lrc files) when available
"""

import sys
import os
import json
import time
import threading
import re
from pathlib import Path
from typing import Optional, Dict, List, Any

import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLineEdit, QLabel, QComboBox, QProgressBar, 
    QScrollArea, QFrame, QSizePolicy, QFileDialog, QMessageBox,
    QStackedWidget, QListWidget, QListWidgetItem, QTextEdit, QSplitter,
    QGroupBox, QFormLayout, QCheckBox, QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QUrl
from PyQt6.QtGui import QPixmap, QFont, QIcon, QDesktopServices

try:
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC, USLT, TRCK
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("Warning: mutagen not available. Tags won't be embedded.")


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Music" / "Tidal")

QUALITY_OPTIONS = {
    "LOW": "Low (96kbps)",
    "HIGH": "High (320kbps)",
    "LOSSLESS": "Lossless (FLAC)",
    "HI_RES_LOSSLESS": "Hi-Res Lossless (Max)",
}


# ============================================================================
# API CLIENT
# ============================================================================

class HifiAPIClient:
    """Client for interacting with the hifi-api"""
    
    def __init__(self, base_url: str = DEFAULT_API_URL):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CachyOS-Music-Downloader/1.0",
            "Accept": "application/json",
        })
    
    def search(self, query: str, search_type: str = "tracks", limit: int = 20) -> Dict[str, Any]:
        """Search for music"""
        params = {"limit": limit, "offset": 0}
        
        if search_type == "tracks":
            params["s"] = query
            endpoint = "/search/"
        elif search_type == "albums":
            params["al"] = query
            endpoint = "/search/"
        elif search_type == "artists":
            params["a"] = query
            endpoint = "/search/"
        else:
            raise ValueError(f"Unknown search type: {search_type}")
        
        try:
            response = self.session.get(f"{self.base_url}{endpoint}", params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "items": []}
    
    def get_track_info(self, track_id: int) -> Dict[str, Any]:
        """Get track metadata"""
        try:
            response = self.session.get(
                f"{self.base_url}/pages/tracks/",
                params={"id": track_id},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_album_info(self, album_id: int) -> Dict[str, Any]:
        """Get album metadata with tracks"""
        try:
            response = self.session.get(
                f"{self.base_url}/album/",
                params={"id": album_id, "limit": 100},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_artist_info(self, artist_id: int) -> Dict[str, Any]:
        """Get artist info with albums"""
        try:
            response = self.session.get(
                f"{self.base_url}/artist/",
                params={"f": artist_id, "skip_tracks": False},
                timeout=60
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_track_stream_url(self, track_id: int, quality: str = "HI_RES_LOSSLESS") -> Optional[str]:
        """Get streaming URL for a track"""
        try:
            response = self.session.get(
                f"{self.base_url}/track/",
                params={"id": track_id, "quality": quality},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Parse the manifest to get actual stream URL
            if "manifest" in data:
                manifest = data["manifest"]
                mime_type = manifest.get("mimeType", "")
                
                if "dash+xml" in mime_type:
                    # DASH manifest - need to parse XML
                    import base64
                    manifest_data = base64.b64decode(manifest.get("data", ""))
                    return self._parse_dash_manifest(manifest_data.decode('utf-8'))
                elif "vnd.apple.mpegurl" in mime_type:
                    # HLS manifest
                    manifest_data = base64.b64decode(manifest.get("data", ""))
                    return self._parse_hls_manifest(manifest_data.decode('utf-8'))
            
            return None
        except Exception as e:
            print(f"Error getting stream URL: {e}")
            return None
    
    def _parse_dash_manifest(self, manifest_xml: str) -> Optional[str]:
        """Extract audio URL from DASH manifest"""
        # Simple regex to find BaseURL
        match = re.search(r'<BaseURL>([^<]+)</BaseURL>', manifest_xml)
        if match:
            return match.group(1)
        return None
    
    def _parse_hls_manifest(self, manifest_content: str) -> Optional[str]:
        """Extract audio URL from HLS manifest"""
        lines = manifest_content.strip().split('\n')
        for line in lines:
            if line.startswith('http') and not line.startswith('#'):
                return line
        return None
    
    def download_file(self, url: str, dest_path: str, progress_callback=None) -> bool:
        """Download a file with progress tracking"""
        try:
            response = self.session.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress_callback(downloaded, total_size)
            
            return True
        except Exception as e:
            print(f"Download error: {e}")
            return False
    
    def get_lyrics(self, track_id: int) -> Optional[str]:
        """Get lyrics for a track"""
        try:
            response = self.session.get(
                f"{self.base_url}/lyrics/",
                params={"id": track_id},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                # Return synchronized lyrics if available
                return data.get("lyrics") or data.get("text")
            return None
        except Exception:
            return None
    
    def get_cover_art(self, album_id: int, size: str = "1280") -> Optional[bytes]:
        """Get cover art image"""
        try:
            response = self.session.get(
                f"{self.base_url}/cover/",
                params={"id": album_id},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                covers = data.get("covers", [])
                if covers:
                    cover_url = covers[0].get(size, covers[0].get("1280"))
                    if cover_url:
                        img_response = self.session.get(cover_url, timeout=30)
                        if img_response.status_code == 200:
                            return img_response.content
            return None
        except Exception:
            return None


# ============================================================================
# DOWNLOADER THREAD
# ============================================================================

class DownloadTask:
    """Represents a download task"""
    def __init__(self, item_type: str, item_id: int, title: str, artist: str = ""):
        self.item_type = item_type  # "track", "album", "artist"
        self.item_id = item_id
        self.title = title
        self.artist = artist
        self.status = "pending"  # pending, downloading, completed, failed
        self.progress = 0
        self.error = None


class DownloadWorker(QThread):
    """Background thread for downloading music"""
    
    progress_signal = pyqtSignal(int, int, str)  # current, total, message
    task_progress = pyqtSignal(int, int, str)  # task_id, percent, status
    task_complete = pyqtSignal(int, str)  # task_id, path
    task_error = pyqtSignal(int, str)  # task_id, error
    finished_signal = pyqtSignal()
    
    def __init__(self, api_client: HifiAPIClient, tasks: List[DownloadTask], 
                 download_dir: str, quality: str = "HI_RES_LOSSLESS"):
        super().__init__()
        self.api = api_client
        self.tasks = tasks
        self.download_dir = download_dir
        self.quality = quality
        self._stop_flag = False
    
    def stop(self):
        self._stop_flag = True
    
    def run(self):
        for i, task in enumerate(self.tasks):
            if self._stop_flag:
                break
            
            try:
                if task.item_type == "track":
                    self._download_track(task)
                elif task.item_type == "album":
                    self._download_album(task)
                elif task.item_type == "artist":
                    self._download_artist(task)
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                self.task_error.emit(i, str(e))
        
        self.finished_signal.emit()
    
    def _download_track(self, task: DownloadTask):
        """Download a single track"""
        self.task_progress.emit(id(task), 10, "Getting track info...")
        
        # Get track info
        track_info = self.api.get_track_info(task.item_id)
        if "error" in track_info:
            raise Exception(track_info["error"])
        
        track_data = track_info.get("data", {})
        if not track_data:
            track_data = track_info
        
        title = track_data.get("title", task.title)
        artist_name = track_data.get("artist", {}).get("name", task.artist)
        album_title = track_data.get("album", {}).get("title", "Unknown Album")
        track_number = track_data.get("trackNumber", 1)
        year = track_data.get("streamStartDate", "")[:4] if track_data.get("streamStartDate") else ""
        
        # Create directory structure: Artist/Artist - Album/
        safe_artist = self._sanitize_filename(artist_name)
        safe_album = self._sanitize_filename(f"{artist_name} - {album_title}")
        track_dir = Path(self.download_dir) / safe_artist / safe_album
        track_dir.mkdir(parents=True, exist_ok=True)
        
        # Get stream URL
        self.task_progress.emit(id(task), 30, "Getting stream URL...")
        stream_url = self.api.get_track_stream_url(task.item_id, self.quality)
        if not stream_url:
            raise Exception("Could not get stream URL")
        
        # Download audio
        self.task_progress.emit(id(task), 50, "Downloading audio...")
        ext = ".flac" if "flac" in self.quality.lower() else ".m4a"
        filename = self._sanitize_filename(f"{track_number:02d} - {title}{ext}")
        audio_path = track_dir / filename
        
        def dl_progress(current, total):
            percent = 50 + (current / total * 40)
            self.task_progress.emit(id(task), int(percent), f"Downloading: {current//1024}KB/{total//1024}KB")
        
        if not self.api.download_file(stream_url, str(audio_path), dl_progress):
            raise Exception("Download failed")
        
        # Download lyrics
        self.task_progress.emit(id(task), 90, "Saving metadata...")
        lyrics = self.api.get_lyrics(task.item_id)
        if lyrics:
            lrc_path = track_dir / f"{self._sanitize_filename(f'{track_number:02d} - {title}')}.lrc"
            with open(lrc_path, 'w', encoding='utf-8') as f:
                f.write(lyrics)
        
        # Embed tags if mutagen is available
        if MUTAGEN_AVAILABLE:
            self._embed_tags(str(audio_path), title, artist_name, album_title, 
                           track_number, year, track_info)
        
        self.task_progress.emit(id(task), 100, "Completed!")
        self.task_complete.emit(id(task), str(audio_path))
        task.status = "completed"
    
    def _download_album(self, task: DownloadTask):
        """Download an entire album"""
        self.task_progress.emit(id(task), 5, "Getting album info...")
        
        album_info = self.api.get_album_info(task.item_id)
        if "error" in album_info:
            raise Exception(album_info["error"])
        
        album_data = album_info.get("data", {})
        if not album_data:
            album_data = album_info
        
        album_title = album_data.get("title", task.title)
        artist_name = album_data.get("artist", {}).get("name", task.artist)
        year = album_data.get("releaseDate", "")[:4] if album_data.get("releaseDate") else ""
        total_tracks = album_data.get("numberOfTracks", 0)
        
        # Create directory structure
        safe_artist = self._sanitize_filename(artist_name)
        safe_album = self._sanitize_filename(f"{artist_name} - {album_title}")
        album_dir = Path(self.download_dir) / safe_artist / safe_album
        album_dir.mkdir(parents=True, exist_ok=True)
        
        # Download cover art
        cover_data = self.api.get_cover_art(task.item_id)
        if cover_data:
            cover_path = album_dir / "cover.jpg"
            with open(cover_path, 'wb') as f:
                f.write(cover_data)
        
        # Get tracks
        tracks = album_data.get("items", [])
        if not tracks:
            # Try alternative structure
            tracks = album_data.get("tracks", [])
        
        for i, track in enumerate(tracks):
            if self._stop_flag:
                break
            
            track_id = track.get("id") or track.get("item", {}).get("id")
            if not track_id:
                continue
            
            track_title = track.get("title") or track.get("item", {}).get("title", "Unknown")
            track_num = track.get("trackNumber") or track.get("item", {}).get("trackNumber", i + 1)
            
            # Update task for this track
            sub_task = DownloadTask("track", track_id, track_title, artist_name)
            
            percent = 10 + (i / len(tracks) * 80)
            self.task_progress.emit(id(task), int(percent), f"Track {i+1}/{len(tracks)}: {track_title}")
            
            try:
                # Get stream URL
                stream_url = self.api.get_track_stream_url(track_id, self.quality)
                if not stream_url:
                    continue
                
                ext = ".flac" if "flac" in self.quality.lower() else ".m4a"
                filename = self._sanitize_filename(f"{track_num:02d} - {track_title}{ext}")
                audio_path = album_dir / filename
                
                if self.api.download_file(stream_url, str(audio_path)):
                    # Lyrics
                    lyrics = self.api.get_lyrics(track_id)
                    if lyrics:
                        lrc_path = album_dir / f"{self._sanitize_filename(f'{track_num:02d} - {track_title}')}.lrc"
                        with open(lrc_path, 'w', encoding='utf-8') as f:
                            f.write(lyrics)
                    
                    # Tags
                    if MUTAGEN_AVAILABLE:
                        self._embed_tags(str(audio_path), track_title, artist_name, 
                                       album_title, track_num, year, album_info)
            except Exception as e:
                print(f"Error downloading track {track_title}: {e}")
        
        self.task_progress.emit(id(task), 100, "Album complete!")
        self.task_complete.emit(id(task), str(album_dir))
        task.status = "completed"
    
    def _download_artist(self, task: DownloadTask):
        """Download all albums from an artist"""
        self.task_progress.emit(id(task), 5, "Getting artist info...")
        
        artist_info = self.api.get_artist_info(task.item_id)
        if "error" in artist_info:
            raise Exception(artist_info["error"])
        
        albums = artist_info.get("albums", {}).get("items", [])
        if not albums:
            raise Exception("No albums found for this artist")
        
        artist_name = task.artist
        if not artist_name and albums:
            first_album = albums[0]
            artist_name = first_album.get("artist", {}).get("name", "Unknown Artist")
        
        self.task_progress.emit(id(task), 10, f"Found {len(albums)} albums by {artist_name}")
        
        for i, album in enumerate(albums):
            if self._stop_flag:
                break
            
            album_id = album.get("id")
            album_title = album.get("title", "Unknown Album")
            
            percent = 10 + (i / len(albums) * 85)
            self.task_progress.emit(id(task), int(percent), f"Album {i+1}/{len(albums)}: {album_title}")
            
            # Create sub-task for album
            album_task = DownloadTask("album", album_id, album_title, artist_name)
            
            try:
                self._download_album(album_task)
            except Exception as e:
                print(f"Error downloading album {album_title}: {e}")
        
        self.task_progress.emit(id(task), 100, "Artist discography complete!")
        self.task_complete.emit(id(task), str(Path(self.download_dir) / self._sanitize_filename(artist_name)))
        task.status = "completed"
    
    def _sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()
    
    def _embed_tags(self, filepath: str, title: str, artist: str, album: str,
                   track_num: int, year: str, full_info: dict):
        """Embed metadata tags into audio file"""
        try:
            ext = Path(filepath).suffix.lower()
            
            if ext == '.flac':
                audio = FLAC(filepath)
                audio['title'] = title
                audio['artist'] = artist
                audio['album'] = album
                audio['tracknumber'] = str(track_num)
                if year:
                    audio['date'] = year
                audio.save()
            elif ext in ['.m4a', '.mp4']:
                audio = MP4(filepath)
                audio['\xa9nam'] = title
                audio['\xa9ART'] = artist
                audio['\xa9alb'] = album
                audio['trkn'] = [(track_num, 0)]
                if year:
                    audio['\xa9day'] = year
                audio.save()
            elif ext == '.mp3':
                audio = ID3(filepath)
                audio.add(TIT2(encoding=3, text=title))
                audio.add(TPE1(encoding=3, text=artist))
                audio.add(TALB(encoding=3, text=album))
                audio.add(TRCK(encoding=3, text=str(track_num)))
                if year:
                    audio.add(TDRC(encoding=3, text=year))
                audio.save()
        except Exception as e:
            print(f"Error embedding tags: {e}")


# ============================================================================
# MAIN WINDOW
# ============================================================================

class CachyOSMusicDownloader(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.api = HifiAPIClient()
        self.download_tasks: List[DownloadTask] = []
        self.worker: Optional[DownloadWorker] = None
        
        self.setWindowTitle("🎵 CachyOS Music Downloader")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(self._get_stylesheet())
        
        self._setup_ui()
    
    def _get_stylesheet(self) -> str:
        """Modern dark theme stylesheet"""
        return """
        QMainWindow {
            background-color: #1a1b26;
        }
        
        QWidget {
            background-color: #1a1b26;
            color: #a9b1d6;
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        
        QLabel {
            color: #a9b1d6;
            font-size: 14px;
        }
        
        QLabel#title {
            font-size: 28px;
            font-weight: bold;
            color: #7aa2f7;
            padding: 10px;
        }
        
        QLabel#subtitle {
            font-size: 12px;
            color: #565f89;
        }
        
        QLineEdit {
            background-color: #24283b;
            border: 2px solid #414868;
            border-radius: 8px;
            padding: 10px 15px;
            font-size: 14px;
            color: #c0caf5;
        }
        
        QLineEdit:focus {
            border-color: #7aa2f7;
        }
        
        QPushButton {
            background-color: #7aa2f7;
            color: #1a1b26;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: bold;
        }
        
        QPushButton:hover {
            background-color: #5d87e5;
        }
        
        QPushButton:pressed {
            background-color: #3d5cb5;
        }
        
        QPushButton:disabled {
            background-color: #414868;
            color: #565f89;
        }
        
        QPushButton#secondary {
            background-color: #414868;
            color: #a9b1d6;
        }
        
        QPushButton#secondary:hover {
            background-color: #565f89;
        }
        
        QComboBox {
            background-color: #24283b;
            border: 2px solid #414868;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 14px;
            color: #c0caf5;
        }
        
        QComboBox:focus {
            border-color: #7aa2f7;
        }
        
        QComboBox::drop-down {
            border: none;
            width: 30px;
        }
        
        QProgressBar {
            background-color: #24283b;
            border: none;
            border-radius: 5px;
            height: 8px;
        }
        
        QProgressBar::chunk {
            background-color: #7aa2f7;
            border-radius: 5px;
        }
        
        QScrollArea {
            border: none;
            background-color: transparent;
        }
        
        QListWidget {
            background-color: #24283b;
            border: 2px solid #414868;
            border-radius: 8px;
            outline: none;
            font-size: 14px;
        }
        
        QListWidget::item {
            padding: 10px;
            border-bottom: 1px solid #414868;
        }
        
        QListWidget::item:selected {
            background-color: #7aa2f7;
            color: #1a1b26;
        }
        
        QListWidget::item:hover {
            background-color: #414868;
        }
        
        QGroupBox {
            border: 2px solid #414868;
            border-radius: 8px;
            margin-top: 10px;
            padding-top: 10px;
            font-weight: bold;
            color: #7aa2f7;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
        }
        
        QTextEdit {
            background-color: #24283b;
            border: 2px solid #414868;
            border-radius: 8px;
            padding: 10px;
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: #9ece6a;
        }
        
        QSpinBox {
            background-color: #24283b;
            border: 2px solid #414868;
            border-radius: 8px;
            padding: 8px;
            font-size: 14px;
            color: #c0caf5;
        }
        
        QCheckBox {
            color: #a9b1d6;
            font-size: 14px;
            spacing: 8px;
        }
        
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 2px solid #414868;
            background-color: #24283b;
        }
        
        QCheckBox::indicator:checked {
            background-color: #7aa2f7;
            border-color: #7aa2f7;
        }
        """
    
    def _setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        # Header
        header_label = QLabel("🎵 CachyOS Music Downloader")
        header_label.setObjectName("title")
        subtitle_label = QLabel("Download high-quality music from Tidal")
        subtitle_label.setObjectName("subtitle")
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)
        main_layout.addWidget(subtitle_label)
        
        # Main content area with splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel - Search and Settings
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(15)
        
        # API Configuration
        api_group = QGroupBox("API Configuration")
        api_layout = QFormLayout()
        
        self.api_url_input = QLineEdit(DEFAULT_API_URL)
        self.api_url_input.setPlaceholderText("http://localhost:8000")
        api_layout.addRow("API URL:", self.api_url_input)
        
        left_layout.addWidget(api_group)
        
        # Search Section
        search_group = QGroupBox("Search Music")
        search_layout = QVBoxLayout()
        
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search for artists, albums, or tracks...")
        self.search_input.returnPressed.connect(self._perform_search)
        
        self.search_type_combo = QComboBox()
        self.search_type_combo.addItems(["Tracks", "Albums", "Artists"])
        
        search_btn = QPushButton("🔍 Search")
        search_btn.clicked.connect(self._perform_search)
        
        search_row.addWidget(self.search_input, 3)
        search_row.addWidget(self.search_type_combo, 1)
        search_row.addWidget(search_btn, 1)
        
        search_layout.addLayout(search_row)
        
        # Results list
        self.results_list = QListWidget()
        self.results_list.setFixedHeight(300)
        self.results_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        
        search_layout.addWidget(QLabel("Results:"))
        search_layout.addWidget(self.results_list)
        
        search_group.setLayout(search_layout)
        left_layout.addWidget(search_group)
        
        # Download Settings
        settings_group = QGroupBox("Download Settings")
        settings_layout = QFormLayout()
        
        self.download_dir_input = QLineEdit(DEFAULT_DOWNLOAD_DIR)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("secondary")
        browse_btn.clicked.connect(self._browse_download_dir)
        
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.download_dir_input)
        dir_row.addWidget(browse_btn)
        
        settings_layout.addRow("Download Folder:", dir_row)
        
        self.quality_combo = QComboBox()
        for key, value in QUALITY_OPTIONS.items():
            self.quality_combo.addItem(value, key)
        self.quality_combo.setCurrentIndex(3)  # Default to HI_RES_LOSSLESS
        
        settings_layout.addRow("Quality:", self.quality_combo)
        
        settings_group.setLayout(settings_layout)
        left_layout.addWidget(settings_group)
        
        left_layout.addStretch()
        
        splitter.addWidget(left_panel)
        
        # Right panel - Downloads and Log
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(15)
        
        # Downloads section
        downloads_group = QGroupBox("Active Downloads")
        downloads_layout = QVBoxLayout()
        
        self.downloads_list = QListWidget()
        self.downloads_list.setFixedHeight(200)
        
        downloads_controls = QHBoxLayout()
        self.start_download_btn = QPushButton("⬇️ Start Download")
        self.start_download_btn.clicked.connect(self._start_download)
        self.start_download_btn.setEnabled(False)
        
        self.stop_download_btn = QPushButton("⏹️ Stop All")
        self.stop_download_btn.setObjectName("secondary")
        self.stop_download_btn.clicked.connect(self._stop_download)
        self.stop_download_btn.setEnabled(False)
        
        downloads_controls.addWidget(self.start_download_btn)
        downloads_controls.addWidget(self.stop_download_btn)
        downloads_controls.addStretch()
        
        downloads_layout.addWidget(self.downloads_list)
        downloads_layout.addLayout(downloads_controls)
        
        downloads_group.setLayout(downloads_layout)
        right_layout.addWidget(downloads_group)
        
        # Progress section
        progress_group = QGroupBox("Current Progress")
        progress_layout = QVBoxLayout()
        
        self.current_task_label = QLabel("No active downloads")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        progress_layout.addWidget(self.current_task_label)
        progress_layout.addWidget(self.progress_bar)
        
        progress_group.setLayout(progress_layout)
        right_layout.addWidget(progress_group)
        
        # Log section
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout()
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(200)
        
        log_layout.addWidget(self.log_output)
        
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.setObjectName("secondary")
        clear_log_btn.clicked.connect(self.log_output.clear)
        log_layout.addWidget(clear_log_btn)
        
        log_group.setLayout(log_layout)
        right_layout.addWidget(log_group)
        
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def _log(self, message: str):
        """Add message to log"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_output.append(f"[{timestamp}] {message}")
    
    def _browse_download_dir(self):
        """Open folder browser for download directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Download Directory",
            self.download_dir_input.text()
        )
        if directory:
            self.download_dir_input.setText(directory)
    
    def _perform_search(self):
        """Perform search based on input"""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Search", "Please enter a search query")
            return
        
        search_type_map = {
            "Tracks": "tracks",
            "Albums": "albums",
            "Artists": "artists"
        }
        search_type = search_type_map[self.search_type_combo.currentText()]
        
        self._log(f"Searching for '{query}' ({search_type})...")
        self.results_list.clear()
        
        # Update API URL if changed
        self.api = HifiAPIClient(self.api_url_input.text())
        
        results = self.api.search(query, search_type, limit=20)
        
        if "error" in results:
            self._log(f"Search error: {results['error']}")
            QMessageBox.critical(self, "Search Error", f"Failed to search: {results['error']}")
            return
        
        items = results.get("items", [])
        if not items:
            self._log("No results found")
            return
        
        self._log(f"Found {len(items)} results")
        
        for item in items:
            item_type = search_type.rstrip('s')  # tracks -> track
            
            if search_type == "tracks":
                title = item.get("title", "Unknown")
                artist = item.get("artist", {}).get("name", "Unknown Artist")
                album = item.get("album", {}).get("title", "")
                display_text = f"🎵 {title} - {artist}"
                if album:
                    display_text += f" ({album})"
            elif search_type == "albums":
                title = item.get("title", "Unknown")
                artist = item.get("artist", {}).get("name", "Unknown Artist")
                year = item.get("releaseDate", "")[:4] if item.get("releaseDate") else ""
                display_text = f"💿 {artist} - {title}"
                if year:
                    display_text += f" ({year})"
            else:  # artists
                name = item.get("name", "Unknown Artist")
                display_text = f"🎤 {name}"
            
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.ItemDataRole.UserRole, {
                "type": item_type,
                "id": item.get("id"),
                "title": title if search_type != "artists" else name,
                "artist": artist if search_type != "artists" else name
            })
            self.results_list.addItem(list_item)
    
    def _on_result_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on search result"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        self._add_to_download_queue(data)
    
    def _add_to_download_queue(self, data: dict):
        """Add item to download queue"""
        task = DownloadTask(
            item_type=data["type"],
            item_id=data["id"],
            title=data["title"],
            artist=data.get("artist", "")
        )
        self.download_tasks.append(task)
        
        icon = {"track": "🎵", "album": "💿", "artist": "🎤"}.get(data["type"], "📁")
        self.downloads_list.addItem(f"{icon} {task.artist} - {task.title}")
        
        self._log(f"Added to queue: {task.artist} - {task.title} ({task.item_type})")
        self.start_download_btn.setEnabled(len(self.download_tasks) > 0)
    
    def _start_download(self):
        """Start downloading queued items"""
        if not self.download_tasks:
            return
        
        download_dir = self.download_dir_input.text()
        quality_key = self.quality_combo.currentData()
        
        self._log(f"Starting download of {len(self.download_tasks)} items...")
        self._log(f"Quality: {QUALITY_OPTIONS[quality_key]}")
        self._log(f"Destination: {download_dir}")
        
        self.start_download_btn.setEnabled(False)
        self.stop_download_btn.setEnabled(True)
        
        self.worker = DownloadWorker(
            self.api,
            self.download_tasks.copy(),
            download_dir,
            quality_key
        )
        
        self.worker.task_progress.connect(self._on_task_progress)
        self.worker.task_complete.connect(self._on_task_complete)
        self.worker.task_error.connect(self._on_task_error)
        self.worker.finished_signal.connect(self._on_download_finished)
        
        self.worker.start()
    
    def _stop_download(self):
        """Stop all downloads"""
        if self.worker:
            self.worker.stop()
            self._log("Stopping downloads...")
    
    def _on_task_progress(self, task_id: int, percent: int, status: str):
        """Update progress for a task"""
        self.current_task_label.setText(status)
        self.progress_bar.setValue(percent)
    
    def _on_task_complete(self, task_id: int, path: str):
        """Handle task completion"""
        self._log(f"✓ Downloaded: {path}")
    
    def _on_task_error(self, task_id: int, error: str):
        """Handle task error"""
        self._log(f"✗ Error: {error}")
    
    def _on_download_finished(self):
        """Handle download completion"""
        self._log("All downloads completed!")
        self.start_download_btn.setEnabled(True)
        self.stop_download_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.current_task_label.setText("Downloads complete")
        
        # Clear completed tasks
        self.download_tasks.clear()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = CachyOSMusicDownloader()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
