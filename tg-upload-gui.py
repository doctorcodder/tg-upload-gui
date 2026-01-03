#!/usr/bin/env python3
"""
tg-upload GUI - Windows GUI Interface for tg-upload
Enhanced version with Graphical User Interface for Windows Users

Author: doctorcodder
Version: 1.1.5-gui
"""

import os
import sys
import json
import threading
import hashlib
import concurrent.futures
import queue
from pathlib import Path
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog
from sys import version_info as py_ver
from pkg_resources import get_distribution as get_dist
from time import time
from json import load as json_load, dump as json_dump
import logging

try:
    import customtkinter as ctk
    from PIL import Image
    HAS_CUSTOMTKINTER = True
except ImportError:
    HAS_CUSTOMTKINTER = False
    print("Warning: customtkinter not installed. Installing...")
    os.system(f"{sys.executable} -m pip install customtkinter -q")
    import customtkinter as ctk
    from PIL import Image

from httpx import get as get_url
from os import environ as env

try:
    from moviepy.video.io.VideoFileClip import VideoFileClip
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    HAS_MOVIEPY = True
except ImportError:
    HAS_MOVIEPY = False

try:
    from pyrogram import Client, enums, errors
    HAS_PYROGRAM = True
except ImportError:
    HAS_PYROGRAM = False

# Version info
TG_UPLOAD_VERSION = "1.1.5-gui"
AUTHOR_NAME = "doctorcodder"

# Configuration paths
APP_DIR = Path.home() / ".tg-upload-gui"
CONFIG_FILE = APP_DIR / "config.json"
PROFILES_DIR = APP_DIR / "profiles"
PROXIES_FILE = APP_DIR / "proxies.json"
CAPTIONS_FILE = APP_DIR / "captions.json"

# Create directories if they don't exist
APP_DIR.mkdir(exist_ok=True)
PROFILES_DIR.mkdir(exist_ok=True)

# GUI Theme Configuration
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TGUploadGUI(ctk.CTk):
    """Main GUI Application Class for tg-upload"""

    def __init__(self):
        super().__init__()

        self.title(f"tg-upload GUI v{TG_UPLOAD_VERSION}")
        self.geometry("1000x750")
        self.minsize(900, 650)

        self.current_profile = None
        self.client = None
        self.client_lock = threading.Lock()
        self.operation_running = False

        # Setup logging
        self.setup_logging()

        # Command queue for communication between GUI thread and connection thread
        self.command_queue = queue.Queue()
        self.result_queue = queue.Queue()

        # Start the worker thread that handles all Telegram operations
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self._log("INFO", "Worker thread started")

        # Load saved configuration
        self.load_config()

        # Setup UI
        self.setup_ui()

        # Check for updates
        self.after(1000, self.check_updates)

    def _worker_loop(self):
        """Worker thread that handles all Telegram operations in a single event loop"""
        import asyncio
        import concurrent.futures

        print("[WORKER] Worker thread starting...")
        self._log("INFO", "Worker thread starting")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._connection_loop = loop
        client = None

        async def run_command(cmd):
            """Execute a command in the event loop"""
            cmd_type = cmd.get("type")
            print(f"[WORKER] Processing command: {cmd_type}")

            try:
                if cmd_type == "connect":
                    print("[WORKER] Processing CONNECT command")
                    profile = cmd.get("profile")
                    profile_name = cmd.get("profile_name")

                    # Stop existing client
                    nonlocal client
                    if client:
                        print("[WORKER] Stopping existing client...")
                        try:
                            await client.stop()
                        except:
                            pass
                        client = None

                    # Create and start new client
                    kwargs = {
                        "name": profile_name,
                        "api_id": str(profile["api_id"]),
                        "api_hash": profile["api_hash"],
                        "app_version": TG_UPLOAD_VERSION,
                        "device_model": profile.get("device_model", "tg-upload-gui"),
                        "system_version": profile.get("system_version", "Windows"),
                        "workdir": str(APP_DIR),
                    }

                    if profile.get("proxy"):
                        kwargs["proxy"] = profile["proxy"]

                    if profile.get("bot_token"):
                        kwargs["bot_token"] = profile["bot_token"]
                    elif profile.get("session_string"):
                        kwargs["session_string"] = profile["session_string"]
                    elif profile.get("phone"):
                        kwargs["phone_number"] = profile["phone"]
                        kwargs["hide_password"] = profile.get("hide_password", False)

                    client = Client(**kwargs)
                    print("[WORKER] Starting Pyrogram client...")
                    await client.start()
                    print("[WORKER] Getting user info...")
                    me = await client.get_me()
                    print(f"[WORKER] Connected successfully: {me.first_name}")

                    return {"success": True, "me": me}

                elif cmd_type == "disconnect":
                    print("[WORKER] Processing DISCONNECT command")
                    if client:
                        print("[WORKER] Stopping client...")
                        await client.stop()
                        client = None
                    print("[WORKER] Disconnected successfully")
                    return {"success": True}

                elif cmd_type == "upload":
                    if not client:
                        raise RuntimeError("Not connected")

                    args = cmd.get("args")
                    path = Path(args["path"])

                    if path.is_file():
                        await self._worker_upload_single_file(client, args)
                    elif path.is_dir():
                        await self._worker_upload_folder(client, args)

                    return {"success": True}

                elif cmd_type == "download":
                    print("[WORKER] Processing DOWNLOAD command")
                    if not client:
                        raise RuntimeError("Not connected")

                    mode = cmd.get("mode")
                    download_dir = cmd.get("download_dir")

                    if mode == "From Link(s)":
                        links = cmd.get("links", [])
                        print(f"[WORKER] Downloading {len(links)} links")
                        for link in links:
                            await self._worker_download_link(client, link, download_dir)
                    elif mode == "From Message ID(s)":
                        chat_id = cmd.get("chat_id")
                        msg_ids = cmd.get("msg_ids", [])
                        print(f"[WORKER] Downloading {len(msg_ids)} messages from {chat_id}")
                        for msg_id in msg_ids:
                            message = await client.get_messages(chat_id, int(msg_id))
                            await client.download_media(message, file_name=download_dir)

                    print("[WORKER] Download completed")
                    return {"success": True}

                elif cmd_type == "batch_upload":
                    print("[WORKER] Processing BATCH_UPLOAD command")
                    if not client:
                        raise RuntimeError("Not connected")

                    args_list = cmd.get("args_list", [])
                    print(f"[WORKER] Uploading {len(args_list)} files in order (order preserved)")

                    # Upload files in exact order - no rearrangement
                    for i, args in enumerate(args_list):
                        # Update batch progress
                        batch_progress = (i + 1) / len(args_list)
                        self._log("INFO", f"Batch progress: {i+1}/{len(args_list)} (order preserved)")
                        
                        path = Path(args["path"])
                        if path.is_file():
                            await self._worker_upload_single_file(client, args)
                        elif path.is_dir():
                            await self._worker_upload_folder(client, args)

                    print(f"[WORKER] Batch upload completed")
                    return {"success": True}

                elif cmd_type == "stop":
                    if client:
                        await client.stop()
                        client = None
                    return {"success": True}

            except Exception as e:
                return {"success": False, "error": str(e)}

        # Main loop
        print("[WORKER] Entering main command processing loop...")
        while True:
            try:
                # Wait for command with timeout
                try:
                    cmd = self.command_queue.get(timeout=1.0)
                    print(f"[WORKER] Got command from queue: {cmd.get('type')}")
                except queue.Empty:
                    # Check if loop should continue
                    if loop.is_closed():
                        print("[WORKER] Loop closed, exiting...")
                        break
                    continue

                # Execute command directly on the loop (not using run_coroutine_threadsafe)
                print(f"[WORKER] Executing command: {cmd.get('type')}")
                result = loop.run_until_complete(run_command(cmd))
                print(f"[WORKER] Command result: {result}")
                self.result_queue.put(result)

            except Exception as e:
                print(f"[WORKER] Loop error: {e}")
                import traceback
                traceback.print_exc()
                self._log("ERROR", f"Worker loop error: {e}")
                self.result_queue.put({"success": False, "error": str(e)})

        self._log("INFO", "Worker loop stopped")

    async def _worker_upload_single_file(self, client, args):
        """Upload a single file from worker thread"""
        path = Path(args["path"])
        filename = path.name

        if args["prefix"]:
            filename = args["prefix"] + filename

        file_size = path.stat().st_size
        self._operation_start_time = time()
        self._operation_filename = filename

        # Determine caption - use filename if option enabled, otherwise use provided caption
        if args.get("use_filename_caption", False):
            caption = path.stem  # filename without extension
        else:
            caption = args.get("caption", "")

        # Notify GUI of start
        self._log("INFO", f"Uploading: {filename} (caption: {caption[:50] if caption else 'none'}...)")

        file_type = args["file_type"]
        chat_id = args["chat_id"]

        def progress_callback(current, total):
            self._progress_callback(current, total, "upload", filename)

        try:
            if file_type == "Photo" or (file_type == "Auto-detect" and path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']):
                await client.send_photo(
                    chat_id, str(path),
                    caption=caption if caption else None,
                    disable_notification=args["silent"],
                    progress=progress_callback
                )
            elif file_type == "Video" or (file_type == "Auto-detect" and path.suffix.lower() in ['.mp4', '.mkv', '.avi', '.mov', '.webm']):
                thumb = None
                if args["thumbnail"] == "auto":
                    if HAS_MOVIEPY:
                        thumb = Path("thumb") / f"THUMB_{path.stem}.jpg"
                        Path("thumb").mkdir(exist_ok=True)
                        with VideoFileClip(str(path)) as video:
                            from math import floor
                            video.save_frame(str(thumb), t=floor(video.duration / 2))
                elif args["thumbnail"]:
                    thumb = args["thumbnail"]

                await client.send_video(
                    chat_id, str(path),
                    caption=caption if caption else None,
                    disable_notification=args["silent"],
                    thumb=thumb,
                    progress=progress_callback
                )
            elif file_type == "Audio" or (file_type == "Auto-detect" and path.suffix.lower() in ['.mp3', '.wav', '.ogg', '.flac', '.m4a']):
                await client.send_audio(
                    chat_id, str(path),
                    caption=caption if caption else None,
                    disable_notification=args["silent"],
                    progress=progress_callback
                )
            else:
                await client.send_document(
                    chat_id, str(path),
                    caption=caption if caption else None,
                    disable_notification=args["silent"],
                    file_name=filename,
                    progress=progress_callback
                )

            if args["delete_original"]:
                path.unlink()

            self._log("INFO", f"Uploaded: {filename}")

        except Exception as e:
            self._log("ERROR", f"Upload failed: {e}")
            raise

    async def _worker_upload_folder(self, client, args):
        """Upload all files in a folder from worker thread"""
        path = Path(args["path"])
        files = []

        if args["recursive"]:
            for f in path.rglob("*"):
                if f.is_file():
                    files.append(f)
        else:
            for f in path.glob("*"):
                if f.is_file():
                    files.append(f)

        for i, file_path in enumerate(files):
            file_args = args.copy()
            file_args["path"] = str(file_path)
            try:
                await self._worker_upload_single_file(client, file_args)
            except Exception as e:
                self._log("ERROR", f"Error uploading {file_path}: {e}")

    async def _worker_download_link(self, client, link, download_dir):
        """Download from a link in worker thread"""
        parts = link.replace(" ", "").split('/')

        if 't.me' not in parts:
            raise ValueError("Invalid Telegram link")

        if 'c' in parts:
            chat_id = int(f"-100{parts[4]}")
        else:
            chat_id = parts[3]

        msg_id = int(parts[-1])

        self._operation_start_time = time()

        message = await client.get_messages(chat_id, msg_id)

        filename = "file"
        if message.document:
            filename = message.document.file_name or "file"
        elif message.video:
            filename = message.video.file_name or "video"
        elif message.audio:
            filename = message.audio.file_name or "audio"
        elif message.photo:
            filename = "photo.jpg"

        self._operation_filename = filename

        def progress_callback(current, total):
            self._progress_callback(current, total, "download", filename)

        await client.download_media(message, file_name=download_dir, progress=progress_callback)
        self._log("INFO", f"Downloaded: {filename}")

    def setup_logging(self):
        """Setup logging system"""
        # Create logs directory
        self.logs_dir = APP_DIR / "logs"
        self.logs_dir.mkdir(exist_ok=True)

        # Setup file logger
        log_file = self.logs_dir / f"tg-upload-{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        # Configure root logger
        self.logger = logging.getLogger('tg-upload')
        self.logger.setLevel(logging.DEBUG)

        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)

        self.log_file_path = log_file
        self._log_messages = []  # Store recent log messages for GUI
        self._max_log_messages = 100  # Max messages to keep in memory

    def _log(self, level, message):
        """Log a message to file and store for GUI"""
        timestamp = datetime.now().strftime('%H:%M:%S')

        # Log to file
        if level == "DEBUG":
            self.logger.debug(message)
        elif level == "INFO":
            self.logger.info(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)

        # Store for GUI display
        log_entry = f"[{timestamp}] [{level}] {message}"
        self._log_messages.append(log_entry)

        # Keep only recent messages
        if len(self._log_messages) > self._max_log_messages:
            self._log_messages = self._log_messages[-self._max_log_messages:]

        # Update log display if it exists
        if hasattr(self, 'log_textbox') and self.log_textbox:
            self.after(0, self._update_log_display)

    def _update_log_display(self):
        """Update the log text display"""
        if hasattr(self, 'log_textbox') and self.log_textbox:
            self.log_textbox.delete("1.0", "end")
            self.log_textbox.insert("end", "\n".join(self._log_messages[-50:]) + "\n")
            self.log_textbox.see("end")  # Auto-scroll to bottom

    def clear_log(self):
        """Clear the log display"""
        self._log_messages = []
        if hasattr(self, 'log_textbox') and self.log_textbox:
            self.log_textbox.delete("1.0", "end")

    def load_config(self):
        """Load saved configuration"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self.config = json_load(f)
            except:
                self.config = {"current_profile": None, "theme": "dark"}
        else:
            self.config = {"current_profile": None, "theme": "dark"}

    def save_config(self):
        """Save configuration"""
        with open(CONFIG_FILE, 'w') as f:
            json_dump(self.config, f, indent=2)

    def setup_ui(self):
        """Setup the main UI layout"""
        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left sidebar
        self.setup_sidebar()

        # Main content area
        self.setup_main_content()

    def setup_sidebar(self):
        """Setup the sidebar with profile management"""
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # Logo/Title
        self.logo_label = ctk.CTkLabel(
            self.sidebar,
            text="tg-upload GUI",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.logo_label.pack(pady=20)

        # Version label
        self.ver_label = ctk.CTkLabel(
            self.sidebar,
            text=f"Version: {TG_UPLOAD_VERSION}",
            font=ctk.CTkFont(size=10)
        )
        self.ver_label.pack(pady=(0, 10))

        # Profile selector
        self.profile_label = ctk.CTkLabel(self.sidebar, text="Profile:")
        self.profile_label.pack(pady=(10, 0), padx=20, anchor="w")

        profiles = self.get_profiles()
        self.profile_combo = ctk.CTkComboBox(self.sidebar, values=profiles)
        self.profile_combo.pack(pady=5, padx=20, fill="x")

        # Set current profile if exists and is valid
        current_profile = self.config.get("current_profile", "")
        if current_profile and current_profile in profiles:
            self.profile_combo.set(current_profile)
        elif profiles:
            self.profile_combo.set(profiles[0])

        # Profile buttons
        self.btn_new_profile = ctk.CTkButton(
            self.sidebar, text="+ New Profile", command=self.new_profile
        )
        self.btn_new_profile.pack(pady=5, padx=20, fill="x")

        self.btn_edit_profile = ctk.CTkButton(
            self.sidebar, text="Edit Profile", command=self.edit_profile
        )
        self.btn_edit_profile.pack(pady=5, padx=20, fill="x")

        self.btn_delete_profile = ctk.CTkButton(
            self.sidebar, text="Delete Profile", fg_color="#d32f2f",
            hover_color="#b71c1c", command=self.delete_profile
        )
        self.btn_delete_profile.pack(pady=5, padx=20, fill="x")

        # Separator
        ctk.CTkFrame(self.sidebar, height=2).pack(pady=10, padx=10, fill="x")

        # Connection status
        self.status_label = ctk.CTkLabel(self.sidebar, text="Status: Not Connected")
        self.status_label.pack(pady=10, padx=20, anchor="w")

        self.btn_connect = ctk.CTkButton(
            self.sidebar, text="Connect", command=self.connect_telegram
        )
        self.btn_connect.pack(pady=5, padx=20, fill="x")

        self.btn_disconnect = ctk.CTkButton(
            self.sidebar, text="Disconnect", fg_color="#d32f2f",
            hover_color="#b71c1c", command=self.disconnect_telegram
        )
        self.btn_disconnect.pack(pady=5, padx=20, fill="x")

        # Account info
        self.account_frame = ctk.CTkFrame(self.sidebar)
        self.account_frame.pack(pady=10, padx=20, fill="x")

        self.account_label = ctk.CTkLabel(self.account_frame, text="No account info")
        self.account_label.pack(pady=10, padx=10)

        # Spacer
        ctk.CTkFrame(self.sidebar, height=2).pack(pady=10, padx=10, fill="x")

        # Settings button
        self.btn_settings = ctk.CTkButton(
            self.sidebar, text="Settings", command=self.show_settings
        )
        self.btn_settings.pack(pady=5, padx=20, fill="x")

        # Exit button
        self.btn_exit = ctk.CTkButton(
            self.sidebar, text="Exit", fg_color="#d32f2f",
            hover_color="#b71c1c", command=self.destroy
        )
        self.btn_exit.pack(pady=5, padx=20, fill="x")

    def setup_main_content(self):
        """Setup main content with tabs"""
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        # Tab view
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.grid(row=1, column=0, sticky="nsew", pady=10)

        # Create tabs
        self.tab_upload = self.tabview.add("Upload")
        self.tab_download = self.tabview.add("Download")
        self.tab_utilities = self.tabview.add("Utilities")
        self.tab_batch = self.tabview.add("Batch")
        self.tab_logs = self.tabview.add("Logs")

        # Setup each tab
        self.setup_upload_tab()
        self.setup_download_tab()
        self.setup_utilities_tab()
        self.setup_batch_tab()
        self.setup_logs_tab()

        # Status bar
        self.status_bar = ctk.CTkLabel(
            self.main_frame, text="Ready", anchor="w"
        )
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self.main_frame)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

    def setup_upload_tab(self):
        """Setup upload tab UI"""
        self.tab_upload.grid_columnconfigure(1, weight=1)

        # File/folder selection
        ctk.CTkLabel(self.tab_upload, text="File/Folder:").grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )

        self.upload_path_var = ctk.StringVar()
        self.entry_upload_path = ctk.CTkEntry(
            self.tab_upload, textvariable=self.upload_path_var
        )
        self.entry_upload_path.grid(
            row=0, column=1, padx=10, pady=10, sticky="ew"
        )

        self.btn_browse = ctk.CTkButton(
            self.tab_upload, text="Browse", command=self.browse_upload_path
        )
        self.btn_browse.grid(row=0, column=2, padx=10, pady=10)

        # Recursive checkbox
        self.upload_recursive = ctk.BooleanVar()
        self.check_recursive = ctk.CTkCheckBox(
            self.tab_upload, text="Recursive (for folders)",
            variable=self.upload_recursive
        )
        self.check_recursive.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        # File type selection
        ctk.CTkLabel(self.tab_upload, text="Send As:").grid(
            row=2, column=0, padx=10, pady=10, sticky="w"
        )

        self.upload_type_combo = ctk.CTkComboBox(
            self.tab_upload,
            values=["Auto-detect", "Photo", "Video", "Audio", "Document", "Voice", "Video Note"]
        )
        self.upload_type_combo.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        # Thumbnail
        ctk.CTkLabel(self.tab_upload, text="Thumbnail:").grid(
            row=3, column=0, padx=10, pady=10, sticky="w"
        )

        self.upload_thumb_var = ctk.StringVar()
        self.entry_upload_thumb = ctk.CTkEntry(
            self.tab_upload, textvariable=self.upload_thumb_var
        )
        self.entry_upload_thumb.grid(
            row=3, column=1, padx=10, pady=10, sticky="ew"
        )

        self.btn_browse_thumb = ctk.CTkButton(
            self.tab_upload, text="Browse", width=80,
            command=self.browse_thumbnail
        )
        self.btn_browse_thumb.grid(row=3, column=2, padx=10, pady=10)

        self.btn_auto_thumb = ctk.CTkButton(
            self.tab_upload, text="Auto", width=80,
            command=lambda: self.upload_thumb_var.set("auto")
        )
        self.btn_auto_thumb.grid(row=3, column=3, padx=(0, 10), pady=10)

        # Caption
        ctk.CTkLabel(self.tab_upload, text="Caption:").grid(
            row=4, column=0, padx=10, pady=10, sticky="nw"
        )

        self.text_caption = ctk.CTkTextbox(self.tab_upload, height=100)
        self.text_caption.grid(
            row=4, column=1, columnspan=3, padx=10, pady=10, sticky="ew"
        )

        # Caption templates
        ctk.CTkLabel(self.tab_upload, text="Caption Template:").grid(
            row=5, column=0, padx=10, pady=10, sticky="w"
        )

        self.caption_template_combo = ctk.CTkComboBox(
            self.tab_upload, values=self.get_caption_templates()
        )
        self.caption_template_combo.grid(
            row=5, column=1, padx=10, pady=10, sticky="w"
        )

        self.btn_load_template = ctk.CTkButton(
            self.tab_upload, text="Load", width=80,
            command=self.load_caption_template
        )
        self.btn_load_template.grid(row=5, column=2, padx=10, pady=10)

        # Destination
        ctk.CTkLabel(self.tab_upload, text="Send To (Chat ID/Username):").grid(
            row=6, column=0, padx=10, pady=10, sticky="w"
        )

        self.upload_chat_var = ctk.StringVar(value="me")
        self.entry_chat = ctk.CTkEntry(
            self.tab_upload, textvariable=self.upload_chat_var
        )
        self.entry_chat.grid(
            row=6, column=1, columnspan=2, padx=10, pady=10, sticky="ew"
        )

        # Additional options frame
        self.options_frame = ctk.CTkFrame(self.tab_upload)
        self.options_frame.grid(
            row=7, column=0, columnspan=4, padx=10, pady=10, sticky="ew"
        )

        # Header label (use pack since we'll use grid in a sub-frame)
        ctk.CTkLabel(self.options_frame, text="Additional Options:").pack(
            pady=5, padx=10, anchor="w"
        )

        # Options content frame (use grid for options)
        self.options_content = ctk.CTkFrame(self.options_frame)
        self.options_content.pack(fill="both", expand=True, padx=5, pady=5)
        self.options_content.grid_columnconfigure(1, weight=1)

        # Prefix
        ctk.CTkLabel(self.options_content, text="Filename Prefix:").grid(
            row=0, column=0, padx=10, pady=5, sticky="w"
        )
        self.upload_prefix_var = ctk.StringVar()
        ctk.CTkEntry(
            self.options_content, textvariable=self.upload_prefix_var
        ).grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        # Split size
        ctk.CTkLabel(self.options_content, text="Split Size (bytes, 0=don't split):").grid(
            row=1, column=0, padx=10, pady=5, sticky="w"
        )
        self.upload_split_var = ctk.StringVar(value="0")
        ctk.CTkEntry(
            self.options_content, textvariable=self.upload_split_var
        ).grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        # Checkboxes
        self.upload_silent = ctk.BooleanVar()
        ctk.CTkCheckBox(
            self.options_content, text="Silent (no notification)",
            variable=self.upload_silent
        ).grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        self.upload_filename_caption = ctk.BooleanVar()
        ctk.CTkCheckBox(
            self.options_content, text="Use filename as caption",
            variable=self.upload_filename_caption
        ).grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        self.upload_spoiler = ctk.BooleanVar()
        ctk.CTkCheckBox(
            self.options_content, text="Spoiler",
            variable=self.upload_spoiler
        ).grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        self.upload_protect = ctk.BooleanVar()
        ctk.CTkCheckBox(
            self.options_content, text="Protect (no forward/save)",
            variable=self.upload_protect
        ).grid(row=5, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        self.upload_delete = ctk.BooleanVar()
        ctk.CTkCheckBox(
            self.options_content, text="Delete original after upload",
            variable=self.upload_delete
        ).grid(row=6, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        # Upload button
        self.btn_upload = ctk.CTkButton(
            self.tab_upload, text="Start Upload",
            command=self.start_upload, height=50
        )
        self.btn_upload.grid(
            row=8, column=0, columnspan=4, padx=10, pady=20, sticky="ew"
        )

        # Cancel button
        self.btn_cancel_upload = ctk.CTkButton(
            self.tab_upload, text="Cancel",
            fg_color="#d32f2f", hover_color="#b71c1c",
            command=self.cancel_operation, state="disabled"
        )
        self.btn_cancel_upload.grid(
            row=9, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="ew"
        )

    def setup_download_tab(self):
        """Setup download tab UI"""
        self.tab_download.grid_columnconfigure(1, weight=1)

        # Download mode selector
        ctk.CTkLabel(self.tab_download, text="Download Mode:").grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )

        self.download_mode_combo = ctk.CTkComboBox(
            self.tab_download,
            values=["From Link(s)", "From Message ID(s)", "From Chat History"],
            command=self.download_mode_changed
        )
        self.download_mode_combo.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        # Link input (for link mode)
        self.link_frame = ctk.CTkFrame(self.tab_download)
        self.link_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=10, sticky="ew")
        self.link_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.link_frame, text="Telegram Links (one per line):").grid(
            row=0, column=0, padx=10, pady=5, sticky="w"
        )

        self.text_links = ctk.CTkTextbox(self.link_frame, height=100)
        self.text_links.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.btn_load_links = ctk.CTkButton(
            self.link_frame, text="Load from File",
            command=self.load_links_from_file
        )
        self.btn_load_links.grid(row=2, column=0, padx=10, pady=5, sticky="e")

        # Message ID input (for msg ID mode)
        self.msg_id_frame = ctk.CTkFrame(self.tab_download)
        self.msg_id_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=10, sticky="ew")
        self.msg_id_frame.grid_columnconfigure(1, weight=1)
        self.msg_id_frame.grid_remove()  # Hide initially

        ctk.CTkLabel(self.msg_id_frame, text="Chat ID/Username:").grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )

        self.download_chat_var = ctk.StringVar()
        ctk.CTkEntry(
            self.msg_id_frame, textvariable=self.download_chat_var
        ).grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(self.msg_id_frame, text="Message IDs (separated by space):").grid(
            row=1, column=0, padx=10, pady=10, sticky="w"
        )

        self.msg_ids_var = ctk.StringVar()
        ctk.CTkEntry(
            self.msg_id_frame, textvariable=self.msg_ids_var
        ).grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # Range download
        self.download_range = ctk.BooleanVar()
        ctk.CTkCheckBox(
            self.msg_id_frame, text="Download range (msg_id1 to msg_id2)",
            variable=self.download_range
        ).grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        # Download directory
        ctk.CTkLabel(self.tab_download, text="Download Directory:").grid(
            row=2, column=0, padx=10, pady=10, sticky="w"
        )

        self.download_dir_var = ctk.StringVar(value=str(Path.cwd() / "downloads"))
        self.entry_download_dir = ctk.CTkEntry(
            self.tab_download, textvariable=self.download_dir_var
        )
        self.entry_download_dir.grid(
            row=2, column=1, padx=10, pady=10, sticky="ew"
        )

        self.btn_browse_download = ctk.CTkButton(
            self.tab_download, text="Browse", width=80,
            command=self.browse_download_dir
        )
        self.btn_browse_download.grid(row=2, column=2, padx=10, pady=10)

        # Auto combine
        self.download_auto_combine = ctk.BooleanVar()
        ctk.CTkCheckBox(
            self.tab_download, text="Auto-combine split files after download",
            variable=self.download_auto_combine
        ).grid(row=3, column=0, columnspan=3, padx=10, pady=10, sticky="w")

        # Download button
        self.btn_download = ctk.CTkButton(
            self.tab_download, text="Start Download",
            command=self.start_download, height=50
        )
        self.btn_download.grid(
            row=4, column=0, columnspan=3, padx=10, pady=20, sticky="ew"
        )

        # Cancel button
        self.btn_cancel_download = ctk.CTkButton(
            self.tab_download, text="Cancel",
            fg_color="#d32f2f", hover_color="#b71c1c",
            command=self.cancel_operation, state="disabled"
        )
        self.btn_cancel_download.grid(
            row=5, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="ew"
        )

    def setup_utilities_tab(self):
        """Setup utilities tab UI"""
        self.utilities_tab = self.tab_utilities

        # Create utility sections
        self.setup_hash_utility()
        self.setup_split_utility()
        self.setup_combine_utility()
        self.setup_frame_utility()
        self.setup_file_info_utility()
        self.setup_convert_utility()

    def setup_hash_utility(self):
        """Setup file hash utility"""
        self.hash_frame = ctk.CTkFrame(self.utilities_tab)
        self.hash_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            self.hash_frame, text="File Hash Calculator",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)

        ctk.CTkLabel(self.hash_frame, text="Select File:").pack(
            padx=10, pady=5, anchor="w"
        )

        self.hash_file_var = ctk.StringVar()
        ctk.CTkEntry(
            self.hash_frame, textvariable=self.hash_file_var
        ).pack(padx=10, pady=5, fill="x")

        btn_frame = ctk.CTkFrame(self.hash_frame)
        btn_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(
            btn_frame, text="Browse", command=self.browse_hash_file
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_frame, text="Clear", command=lambda: self.hash_file_var.set("")
        ).pack(side="left")

        ctk.CTkLabel(self.hash_frame, text="Hash Type:").pack(
            padx=10, pady=5, anchor="w"
        )

        self.hash_type_combo = ctk.CTkComboBox(
            self.hash_frame,
            values=["SHA256", "MD5", "SHA256 + MD5"]
        )
        self.hash_type_combo.pack(padx=10, pady=5, anchor="w")

        self.btn_calc_hash = ctk.CTkButton(
            self.hash_frame, text="Calculate Hash",
            command=self.calculate_hash
        )
        self.btn_calc_hash.pack(padx=10, pady=10)

        self.hash_result = ctk.CTkTextbox(self.hash_frame, height=80)
        self.hash_result.pack(padx=10, pady=10, fill="x")

    def setup_split_utility(self):
        """Setup file split utility"""
        self.split_frame = ctk.CTkFrame(self.utilities_tab)
        self.split_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            self.split_frame, text="File Splitter",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)

        ctk.CTkLabel(self.split_frame, text="Select File:").pack(
            padx=10, pady=5, anchor="w"
        )

        self.split_file_var = ctk.StringVar()
        ctk.CTkEntry(
            self.split_frame, textvariable=self.split_file_var
        ).pack(padx=10, pady=5, fill="x")

        btn_frame = ctk.CTkFrame(self.split_frame)
        btn_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(
            btn_frame, text="Browse", command=self.browse_split_file
        ).pack(side="left", padx=(0, 5))

        ctk.CTkLabel(btn_frame, text="Chunk Size:").pack(side="left", padx=(20, 5))

        self.split_size_var = ctk.StringVar(value="1073741824")  # 1GB default
        ctk.CTkEntry(
            btn_frame, textvariable=self.split_size_var, width=150
        ).pack(side="left", padx=5)

        ctk.CTkLabel(btn_frame, text="bytes").pack(side="left")

        # Quick size buttons
        quick_frame = ctk.CTkFrame(self.split_frame)
        quick_frame.pack(fill="x", padx=10, pady=5)

        sizes = [
            ("100 MB", 104857600),
            ("500 MB", 524288000),
            ("1 GB", 1073741824),
            ("2 GB", 2147483648),
        ]

        for label, size in sizes:
            ctk.CTkButton(
                quick_frame, text=label, width=70,
                command=lambda s=size: self.split_size_var.set(str(s))
            ).pack(side="left", padx=2)

        ctk.CTkButton(
            self.split_frame, text="Split File",
            command=self.split_file_utility
        ).pack(padx=10, pady=10)

    def setup_combine_utility(self):
        """Setup file combine utility"""
        self.combine_frame = ctk.CTkFrame(self.utilities_tab)
        self.combine_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            self.combine_frame, text="File Combiner",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)

        ctk.CTkLabel(self.combine_frame, text="Select Part Files:").pack(
            padx=10, pady=5, anchor="w"
        )

        ctk.CTkButton(
            self.combine_frame, text="Select Part Files",
            command=self.select_combine_files
        ).pack(padx=10, pady=5)

        self.combine_files_label = ctk.CTkLabel(
            self.combine_frame, text="No files selected", text_color="gray"
        )
        self.combine_files_label.pack(padx=10, pady=5)

        ctk.CTkLabel(self.combine_frame, text="Output Filename:").pack(
            padx=10, pady=5, anchor="w"
        )

        self.combine_output_var = ctk.StringVar()
        ctk.CTkEntry(
            self.combine_frame, textvariable=self.combine_output_var
        ).pack(padx=10, pady=5, fill="x")

        ctk.CTkButton(
            self.combine_frame, text="Combine Files",
            command=self.combine_files_utility
        ).pack(padx=10, pady=10)

    def setup_frame_utility(self):
        """Setup video frame capture utility"""
        self.frame_frame = ctk.CTkFrame(self.utilities_tab)
        self.frame_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            self.frame_frame, text="Video Frame Capture",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)

        ctk.CTkLabel(self.frame_frame, text="Select Video:").pack(
            padx=10, pady=5, anchor="w"
        )

        self.frame_video_var = ctk.StringVar()
        ctk.CTkEntry(
            self.frame_frame, textvariable=self.frame_video_var
        ).pack(padx=10, pady=5, fill="x")

        btn_frame = ctk.CTkFrame(self.frame_frame)
        btn_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(
            btn_frame, text="Browse", command=self.browse_video_file
        ).pack(side="left", padx=(0, 5))

        ctk.CTkLabel(btn_frame, text="Time (seconds):").pack(side="left", padx=(20, 5))

        self.frame_time_var = ctk.StringVar(value="0")
        ctk.CTkEntry(
            btn_frame, textvariable=self.frame_time_var, width=80
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Capture", command=self.capture_frame
        ).pack(side="left", padx=10)

    def setup_file_info_utility(self):
        """Setup file info utility"""
        self.info_frame = ctk.CTkFrame(self.utilities_tab)
        self.info_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            self.info_frame, text="File Information",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)

        self.info_file_var = ctk.StringVar()
        ctk.CTkEntry(
            self.info_frame, textvariable=self.info_file_var
        ).pack(padx=10, pady=5, fill="x")

        btn_frame = ctk.CTkFrame(self.info_frame)
        btn_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(
            btn_frame, text="Browse", command=self.browse_info_file
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_frame, text="Get Info", command=self.get_file_info
        ).pack(side="left")

        self.info_result = ctk.CTkTextbox(self.info_frame, height=100)
        self.info_result.pack(padx=10, pady=10, fill="x")

    def setup_convert_utility(self):
        """Setup image convert utility"""
        self.convert_frame = ctk.CTkFrame(self.utilities_tab)
        self.convert_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            self.convert_frame, text="Image Converter (to JPEG)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)

        self.convert_file_var = ctk.StringVar()
        ctk.CTkEntry(
            self.convert_frame, textvariable=self.convert_file_var
        ).pack(padx=10, pady=5, fill="x")

        btn_frame = ctk.CTkFrame(self.convert_frame)
        btn_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(
            btn_frame, text="Browse", command=self.browse_convert_file
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_frame, text="Convert", command=self.convert_image
        ).pack(side="left")

    def setup_batch_tab(self):
        """Setup batch operations tab"""
        self.tab_batch.grid_columnconfigure(0, weight=1)

        # Batch upload section
        batch_upload_frame = ctk.CTkFrame(self.tab_batch)
        batch_upload_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(
            batch_upload_frame, text="Batch Upload Queue",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=10)

        # Add files button
        self.btn_batch_add = ctk.CTkButton(
            batch_upload_frame, text="Add Files",
            command=self.batch_add_files
        )
        self.btn_batch_add.pack(pady=5, padx=5, side="left")

        # Add folders button
        self.btn_batch_add_folder = ctk.CTkButton(
            batch_upload_frame, text="Add Folder",
            command=self.batch_add_folder
        )
        self.btn_batch_add_folder.pack(pady=5, padx=5, side="left")

        # Queue listbox
        self.batch_listbox = ctk.CTkTextbox(
            batch_upload_frame, height=150
        )
        self.batch_listbox.pack(pady=10, padx=10, fill="x")

        # Destination chat
        dest_frame = ctk.CTkFrame(batch_upload_frame)
        dest_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(dest_frame, text="Send To:").pack(side="left", padx=5)
        self.batch_chat_var = ctk.StringVar(value="me")
        ctk.CTkEntry(dest_frame, textvariable=self.batch_chat_var, width=200).pack(side="left", padx=5)

        # Caption section
        caption_frame = ctk.CTkFrame(batch_upload_frame)
        caption_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(caption_frame, text="Caption:").pack(anchor="w", padx=5)
        self.batch_caption_text = ctk.CTkTextbox(caption_frame, height=60)
        self.batch_caption_text.pack(fill="x", padx=5, pady=2)

        # Use filename as caption option
        self.batch_use_filename_caption = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            caption_frame, text="Use filename as caption for each file",
            variable=self.batch_use_filename_caption
        ).pack(anchor="w", padx=5, pady=2)

        # Batch options
        options_frame = ctk.CTkFrame(batch_upload_frame)
        options_frame.pack(fill="x", padx=10, pady=5)

        self.batch_recursive = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            options_frame, text="Recursive (for folders)",
            variable=self.batch_recursive
        ).pack(side="left", padx=10)

        self.batch_silent = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            options_frame, text="Silent (no notification)",
            variable=self.batch_silent
        ).pack(side="left", padx=10)

        self.batch_delete = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            options_frame, text="Delete original after upload",
            variable=self.batch_delete
        ).pack(side="left", padx=10)

        # Action buttons
        btn_frame = ctk.CTkFrame(batch_upload_frame)
        btn_frame.pack(fill="x", padx=10, pady=10)

        self.btn_batch_start = ctk.CTkButton(
            btn_frame, text="Start Batch Upload",
            command=self.start_batch_upload
        )
        self.btn_batch_start.pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Clear Queue",
            command=self.batch_clear_queue
        ).pack(side="left", padx=5)

        # Batch queue storage
        self.batch_queue = []

    def setup_logs_tab(self):
        """Setup logs tab UI with real-time log display"""
        self.tab_logs.grid_columnconfigure(0, weight=1)
        self.tab_logs.grid_rowconfigure(1, weight=1)

        # Header frame
        header_frame = ctk.CTkFrame(self.tab_logs)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        ctk.CTkLabel(
            header_frame, text="Real-Time Logs",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left", padx=10, pady=10)

        # Log file path display
        self.log_path_label = ctk.CTkLabel(
            header_frame, text=f"Log file: {self.log_file_path.name}",
            font=ctk.CTkFont(size=10)
        )
        self.log_path_label.pack(side="left", padx=10)

        # Buttons
        btn_frame = ctk.CTkFrame(self.tab_logs)
        btn_frame.grid(row=0, column=1, sticky="e", padx=10, pady=10)

        ctk.CTkButton(
            btn_frame, text="Clear", width=80,
            command=self.clear_log
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Open Log File", width=120,
            command=self.open_log_file
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Open Logs Folder", width=140,
            command=self.open_logs_folder
        ).pack(side="left", padx=5)

        # Log text display
        self.log_textbox = ctk.CTkTextbox(self.tab_logs, font=("Consolas", 10))
        self.log_textbox.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))

        # Initial log message
        self._log("INFO", "Application started")
        self._log("INFO", f"Log file: {self.log_file_path}")

    def open_log_file(self):
        """Open the current log file in default editor"""
        try:
            import subprocess
            subprocess.run(['notepad', str(self.log_file_path)])
        except:
            self.status_bar.configure(text=f"Open manually: {self.log_file_path}")

    def open_logs_folder(self):
        """Open the logs folder in file explorer"""
        try:
            import subprocess
            subprocess.run(['explorer', str(self.logs_dir)])
        except:
            self.status_bar.configure(text=f"Open manually: {self.logs_dir}")

    # Helper methods
    def get_profiles(self):
        """Get list of available profiles"""
        profiles = []
        for f in PROFILES_DIR.glob("*.json"):
            profiles.append(f.stem)
        return profiles if profiles else ["Default"]

    def get_caption_templates(self):
        """Get list of caption templates"""
        templates = ["None"]
        if CAPTIONS_FILE.exists():
            try:
                with open(CAPTIONS_FILE, 'r') as f:
                    captions = json_load(f)
                    templates.extend(captions.keys())
            except:
                pass
        return templates

    def new_profile(self):
        """Create a new profile"""
        name = simpledialog.askstring("New Profile", "Enter profile name:")
        if not name:
            return

        profile_file = PROFILES_DIR / f"{name}.json"
        if profile_file.exists():
            messagebox.showerror("Error", "Profile already exists!")
            return

        self.edit_profile_data(name, {})

    def edit_profile(self):
        """Edit selected profile"""
        name = self.profile_combo.get()
        if not name:
            messagebox.showwarning("Warning", "No profile selected!")
            return

        profile_file = PROFILES_DIR / f"{name}.json"
        if profile_file.exists():
            with open(profile_file, 'r') as f:
                data = json_load(f)
        else:
            data = {}

        self.edit_profile_data(name, data)

    def edit_profile_data(self, name, data):
        """Edit profile data with dialog"""
        dialog = ProfileDialog(self, name, data)
        if dialog.result:
            profile_file = PROFILES_DIR / f"{name}.json"
            with open(profile_file, 'w') as f:
                json_dump(dialog.result, f, indent=2)
            self.profile_combo.configure(values=self.get_profiles())
            self.profile_combo.set(name)
            self.config["current_profile"] = name
            self.save_config()

    def delete_profile(self):
        """Delete selected profile"""
        name = self.profile_combo.get()
        if not name:
            messagebox.showwarning("Warning", "No profile selected!")
            return

        if not messagebox.askyesno("Confirm", f"Delete profile '{name}'?"):
            return

        profile_file = PROFILES_DIR / f"{name}.json"
        session_file = Path(f"{name}.session")

        if profile_file.exists():
            profile_file.unlink()
        if session_file.exists():
            session_file.unlink()

        self.profile_combo.configure(values=self.get_profiles())
        if self.get_profiles():
            self.profile_combo.set(self.get_profiles()[0])
        self.config["current_profile"] = None
        self.save_config()

    def browse_upload_path(self):
        """Browse for upload file/folder"""
        path = filedialog.askopenfilename()
        if path:
            self.upload_path_var.set(path)

    def browse_thumbnail(self):
        """Browse for thumbnail"""
        path = filedialog.askopenfilename(
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.gif")]
        )
        if path:
            self.upload_thumb_var.set(path)

    def browse_download_dir(self):
        """Browse for download directory"""
        path = filedialog.askdirectory()
        if path:
            self.download_dir_var.set(path)

    def load_caption_template(self):
        """Load selected caption template"""
        template = self.caption_template_combo.get()
        if template == "None":
            self.text_caption.delete("1.0", "end")
            return

        if CAPTIONS_FILE.exists():
            with open(CAPTIONS_FILE, 'r') as f:
                captions = json_load(f)
                if template in captions:
                    self.text_caption.delete("1.0", "end")
                    self.text_caption.insert("1.0", captions[template].get("text", ""))

    def download_mode_changed(self, mode):
        """Handle download mode change"""
        if mode == "From Link(s)":
            self.link_frame.grid()
            self.msg_id_frame.grid_remove()
        else:
            self.link_frame.grid_remove()
            self.msg_id_frame.grid()

    def load_links_from_file(self):
        """Load links from text file"""
        path = filedialog.askopenfilename(
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if path:
            with open(path, 'r') as f:
                links = f.read()
            self.text_links.delete("1.0", "end")
            self.text_links.insert("1.0", links)

    def browse_hash_file(self):
        """Browse for hash calculation file"""
        path = filedialog.askopenfilename()
        if path:
            self.hash_file_var.set(path)

    def browse_split_file(self):
        """Browse for file to split"""
        path = filedialog.askopenfilename()
        if path:
            self.split_file_var.set(path)

    def browse_video_file(self):
        """Browse for video file"""
        path = filedialog.askopenfilename(
            filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov"), ("All Files", "*.*")]
        )
        if path:
            self.frame_video_var.set(path)

    def browse_info_file(self):
        """Browse for file info"""
        path = filedialog.askopenfilename()
        if path:
            self.info_file_var.set(path)

    def browse_convert_file(self):
        """Browse for image to convert"""
        path = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.bmp *.gif *.tiff")]
        )
        if path:
            self.convert_file_var.set(path)

    def select_combine_files(self):
        """Select files to combine"""
        paths = filedialog.askopenfilenames(
            filetypes=[("Part Files", "*.part*"), ("All Files", "*.*")]
        )
        if paths:
            self.combine_files_selected = sorted(paths)
            self.combine_files_label.configure(
                text=f"{len(paths)} files selected"
            )

    def batch_add_files(self):
        """Add files to batch queue"""
        paths = filedialog.askopenfilenames()
        if paths:
            for path in paths:
                if path not in self.batch_queue:
                    self.batch_queue.append(path)
            self.update_batch_listbox()

    def batch_add_folder(self):
        """Add folder contents to batch queue - preserves order (1st file first)"""
        path = filedialog.askdirectory()
        if path:
            folder_path = Path(path)
            if self.batch_recursive.get():
                # Add all files recursively in OS-provided order (no sorting)
                for f in folder_path.rglob("*"):
                    if f.is_file():
                        file_path = str(f)
                        if file_path not in self.batch_queue:
                            self.batch_queue.append(file_path)
            else:
                # Add only top-level files in OS-provided order (no sorting)
                for f in folder_path.glob("*"):
                    if f.is_file():
                        file_path = str(f)
                        if file_path not in self.batch_queue:
                            self.batch_queue.append(file_path)
            self.update_batch_listbox()

    def batch_clear_queue(self):
        """Clear batch queue"""
        self.batch_queue = []
        self.update_batch_listbox()

    def batch_remove_selected(self):
        """Remove selected items from batch queue"""
        # This is a simple implementation - in a full version,
        # you would need to track which lines are selected
        if self.batch_queue:
            self.batch_queue.pop()
            self.update_batch_listbox()

    def update_batch_listbox(self):
        """Update the batch queue display"""
        self.batch_listbox.delete("1.0", "end")
        for i, path in enumerate(self.batch_queue):
            self.batch_listbox.insert("end", f"{i + 1}. {path}\n")

    def show_settings(self):
        """Show settings dialog"""
        SettingsDialog(self)

    def cancel_operation(self):
        """Cancel running operation"""
        self.operation_running = False
        self.status_bar.configure(text="Operation cancelled")
        self.btn_upload.configure(state="normal")
        self.btn_download.configure(state="normal")
        self.btn_cancel_upload.configure(state="disabled")
        self.btn_cancel_download.configure(state="disabled")

    def connect_telegram(self):
        """Connect to Telegram using the worker thread"""
        print("[DEBUG] connect_telegram() called")
        
        if not HAS_PYROGRAM:
            print("[ERROR] Pyrogram not installed")
            messagebox.showerror(
                "Error",
                "Pyrogram not installed!\nRun: pip install pyrogram tgcrypto"
            )
            return

        profile_name = self.profile_combo.get()
        print(f"[DEBUG] Selected profile: {profile_name}")
        
        if not profile_name:
            print("[WARNING] No profile selected")
            messagebox.showwarning("Warning", "Please select or create a profile first!")
            return

        profile_file = PROFILES_DIR / f"{profile_name}.json"
        if not profile_file.exists():
            print(f"[WARNING] Profile file not found: {profile_file}")
            messagebox.showwarning("Warning", "Please configure the profile first!")
            self.edit_profile_data(profile_name, {})
            return

        with open(profile_file, 'r') as f:
            profile = json_load(f)

        if not profile.get("api_id") or not profile.get("api_hash"):
            print("[WARNING] API ID or API Hash missing")
            messagebox.showwarning("Warning", "API ID and API Hash are required!")
            return

        print(f"[INFO] Connecting with profile: {profile_name}")
        self.btn_connect.configure(state="disabled")
        self.status_label.configure(text="Status: Connecting...")
        self._log("INFO", f"Connecting to Telegram with profile: {profile_name}")

        # Send connect command to worker thread
        print("[DEBUG] Sending CONNECT command to worker thread")
        self.command_queue.put({
            "type": "connect",
            "profile": profile,
            "profile_name": profile_name
        })

        # Start polling for results
        print("[DEBUG] Starting poll for connection result")
        self.after(100, self._poll_connect_result, profile_name)

    def _connect_thread_async(self, profile, profile_name):
        """Proper async connection thread"""
        import asyncio
        import concurrent.futures

        async def connect_async():
            """Async connection function"""
            try:
                # Stop existing client first
                with self.client_lock:
                    if self.client:
                        try:
                            await self.client.stop()
                        except:
                            pass
                        self.client = None

                # Create client
                kwargs = {
                    "name": profile_name,
                    "api_id": str(profile["api_id"]),
                    "api_hash": profile["api_hash"],
                    "app_version": TG_UPLOAD_VERSION,
                    "device_model": profile.get("device_model", "tg-upload-gui"),
                    "system_version": profile.get("system_version", "Windows"),
                    "workdir": str(APP_DIR),  # Store sessions in app dir
                }

                if profile.get("proxy"):
                    kwargs["proxy"] = profile["proxy"]

                # Set authentication
                if profile.get("bot_token"):
                    kwargs["bot_token"] = profile["bot_token"]
                elif profile.get("session_string"):
                    kwargs["session_string"] = profile["session_string"]
                elif profile.get("phone"):
                    kwargs["phone_number"] = profile["phone"]
                    kwargs["hide_password"] = profile.get("hide_password", False)

                # Create client
                self.client = Client(**kwargs)

                # Start the client (handles login)
                await self.client.start()

                # Get user info
                me = await self.client.get_me()

                return me

            except Exception as e:
                raise e

        # Run async function in thread with new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            me = loop.run_until_complete(connect_async())
            # Don't close the loop - keep client alive for future operations!
            self._connection_loop = loop
            self._connection_active = True
            self.after(0, self._on_connect_success, me, profile_name)
        except Exception as e:
            # Close loop on error
            try:
                loop.close()
            except:
                pass
            error_msg = str(e)
            if "no current event loop" in error_msg.lower():
                error_msg = "Event loop error. Try restarting the application."
            self.after(0, self._on_connect_error, error_msg)

    def _on_connect_success(self, me, profile_name):
        """Handle successful connection"""
        self.status_label.configure(text=f"Status: Connected")
        self.btn_connect.configure(state="normal")

        first_name = me.first_name or "Unknown"
        username = f"@{me.username}" if me.username else "No username"
        self.account_label.configure(
            text=f"{first_name}\n{username}\nID: {me.id}"
        )

        messagebox.showinfo("Connected", f"Successfully connected as {first_name}!")

    def _on_connect_error(self, error):
        """Handle connection error"""
        self.status_label.configure(text="Status: Connection Failed")
        self.btn_connect.configure(state="normal")
        messagebox.showerror("Connection Error", f"Failed to connect:\n{error}")

    def _poll_connect_result(self, profile_name):
        """Poll for connection result"""
        try:
            result = self.result_queue.get_nowait()

            if result.get("success"):
                me = result.get("me")
                first_name = me.first_name or "Unknown"
                username = f"@{me.username}" if me.username else "No username"
                self.account_label.configure(
                    text=f"{first_name}\n{username}\nID: {me.id}"
                )
                self.status_label.configure(text="Status: Connected")
                self.btn_connect.configure(state="normal")
                self._log("INFO", f"Connected successfully as {first_name}")
                messagebox.showinfo("Connected", f"Successfully connected as {first_name}!")
            else:
                error = result.get("error", "Unknown error")
                self._log("ERROR", f"Connection failed: {error}")
                self.status_label.configure(text="Status: Connection Failed")
                self.btn_connect.configure(state="normal")
                messagebox.showerror("Connection Error", f"Failed to connect:\n{error}")

        except queue.Empty:
            # Not ready yet, check again
            self.after(100, self._poll_connect_result, profile_name)

    def disconnect_telegram(self):
        """Disconnect from Telegram using the worker thread"""
        print("[DEBUG] disconnect_telegram() called")
        
        self.status_label.configure(text="Status: Disconnecting...")
        self.btn_disconnect.configure(state="disabled")
        self._log("INFO", "Disconnecting from Telegram")

        print("[DEBUG] Sending DISCONNECT command to worker thread")
        # Send disconnect command to worker thread
        self.command_queue.put({"type": "disconnect"})

        # Start polling for results
        print("[DEBUG] Starting poll for disconnect result")
        self.after(100, self._poll_disconnect_result)

    def _poll_disconnect_result(self):
        """Poll for disconnect result"""
        try:
            result = self.result_queue.get_nowait()

            if result.get("success"):
                self._log("INFO", "Disconnected successfully")
                self.status_label.configure(text="Status: Disconnected")
                self.account_label.configure(text="No account info")
                self.btn_disconnect.configure(state="normal")
                messagebox.showinfo("Disconnected", "Successfully disconnected from Telegram.")
            else:
                error = result.get("error", "Unknown error")
                self._log("ERROR", f"Disconnect error: {error}")
                self.status_label.configure(text="Status: Disconnected")
                self.account_label.configure(text="No account info")
                self.btn_disconnect.configure(state="normal")

        except queue.Empty:
            # Not ready yet, check again
            self.after(100, self._poll_disconnect_result)

    def _poll_operation_result(self, operation_type):
        """Poll for upload/download result"""
        try:
            result = self.result_queue.get_nowait()

            if result.get("success"):
                self._log("INFO", f"{operation_type.capitalize()} completed successfully")
                if operation_type == "upload":
                    self._on_upload_complete()
                else:
                    self._on_download_complete()
            else:
                error = result.get("error", "Unknown error")
                self._log("ERROR", f"{operation_type.capitalize()} failed: {error}")
                if operation_type == "upload":
                    self._on_upload_error(error)
                else:
                    self._on_download_error(error)

        except queue.Empty:
            # Not ready yet, check again
            self.after(100, self._poll_operation_result, operation_type)

    def _disconnect_thread(self):
        """Thread for disconnecting"""
        import asyncio

        async def disconnect_async():
            try:
                if self.client:
                    await self.client.stop()
            except:
                pass
            with self.client_lock:
                self.client = None
            
            # Close the event loop if it exists
            if hasattr(self, '_connection_loop') and self._connection_loop:
                try:
                    self._connection_loop.close()
                except:
                    pass
                self._connection_loop = None
                self._connection_active = False

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(disconnect_async())
            self.after(0, self._on_disconnect_success)
        except Exception as e:
            self.after(0, self._on_disconnect_error, str(e))
        finally:
            try:
                loop.close()
            except:
                pass

    def _on_disconnect_success(self):
        """Handle successful disconnect"""
        self.status_label.configure(text="Status: Disconnected")
        self.account_label.configure(text="No account info")
        self.btn_disconnect.configure(state="normal")
        messagebox.showinfo("Disconnected", "Successfully disconnected from Telegram.")

    def _on_disconnect_error(self, error):
        """Handle disconnect error"""
        self.status_label.configure(text="Status: Disconnected")
        self.account_label.configure(text="No account info")
        self.btn_disconnect.configure(state="normal")
        messagebox.showinfo("Disconnected", "Disconnected from Telegram.")

    def start_upload(self):
        """Start upload operation using the worker thread"""
        path = self.upload_path_var.get()
        if not path:
            messagebox.showwarning("Warning", "Please select a file or folder!")
            return

        if not Path(path).exists():
            messagebox.showerror("Error", "Path does not exist!")
            return

        self.operation_running = True
        self.btn_upload.configure(state="disabled")
        self.btn_cancel_upload.configure(state="normal")
        self.progress_bar.set(0)

        caption = self.text_caption.get("1.0", "end").strip()

        # Check if we should use filename as caption
        use_filename_caption = self.upload_filename_caption.get()

        upload_args = {
            "path": path,
            "recursive": self.upload_recursive.get(),
            "file_type": self.upload_type_combo.get(),
            "thumbnail": self.upload_thumb_var.get() or None,
            "caption": caption,
            "use_filename_caption": use_filename_caption,
            "chat_id": self.upload_chat_var.get() or "me",
            "prefix": self.upload_prefix_var.get() or None,
            "split_size": int(self.upload_split_var.get()) if self.upload_split_var.get() else 0,
            "silent": self.upload_silent.get(),
            "spoiler": self.upload_spoiler.get(),
            "protect": self.upload_protect.get(),
            "delete_original": self.upload_delete.get(),
        }

        self._log("INFO", f"Starting upload: {path}")

        # Send upload command to worker thread
        self.command_queue.put({
            "type": "upload",
            "args": upload_args
        })

        # Start polling for results
        self.after(100, self._poll_operation_result, "upload")

    def _upload_thread_async(self, args):
        """Async upload thread - uses the connection's event loop"""
        import asyncio

        self._log("INFO", f"Upload started: {args['path']}")

        # Check if we have a valid connection loop
        if not hasattr(self, '_connection_loop') or self._connection_loop is None:
            self._log("ERROR", "No connection event loop available")
            self.after(0, lambda: self._on_upload_error("Not connected to Telegram. Please connect first."))
            return

        async def upload_async():
            try:
                path = Path(args["path"])
                chat_id = args["chat_id"]
                self._log("INFO", f"Preparing to upload: {path}")

                if path.is_file():
                    self._log("INFO", "Uploading single file")
                    await self._upload_single_file_async(args)
                elif path.is_dir():
                    self._log("INFO", "Uploading folder")
                    await self._upload_folder_async(args)

                self._log("INFO", "Upload completed successfully")
            except Exception as e:
                error_msg = str(e)
                self._log("ERROR", f"Upload error: {error_msg}")
                raise e

        # Use the connection's event loop with run_coroutine_threadsafe
        try:
            self._log("INFO", "Scheduling upload on connection event loop")
            future = asyncio.run_coroutine_threadsafe(upload_async(), self._connection_loop)
            result = future.result(timeout=300)  # 5 minute timeout
            self.after(0, self._on_upload_complete)
        except concurrent.futures.TimeoutError:
            self._log("ERROR", "Upload timed out after 5 minutes")
            self.after(0, lambda: self._on_upload_error("Upload timed out after 5 minutes"))
        except Exception as e:
            self._log("ERROR", f"Upload failed: {str(e)}")
            self.after(0, lambda: self._on_upload_error(str(e)))

    def _progress_callback(self, current, total, operation_type="upload", filename=""):
        """Progress callback for upload/download operations with speed and remaining time display"""
        def update_gui():
            """Thread-safe GUI update"""
            # Calculate elapsed time and speed
            elapsed = time() - self._operation_start_time
            speed = current / elapsed / (1024 * 1024) if elapsed > 0 else 0
            percent = (current / total) * 100 if total > 0 else 0
            remaining = (total - current) / (speed * 1024 * 1024) if speed > 0 else 0

            # Format speed display
            if speed >= 1:
                speed_str = f"{speed:.1f} MB/s"
            elif speed > 0:
                speed_str = f"{speed * 1024:.1f} KB/s"
            else:
                speed_str = "0 KB/s"

            # Format remaining time display
            if remaining > 3600:
                remaining_str = f"{remaining / 3600:.1f} hr"
            elif remaining > 60:
                remaining_str = f"{remaining / 60:.1f} min"
            elif remaining > 0:
                remaining_str = f"{remaining:.1f} s"
            else:
                remaining_str = "Done soon"

            # Format size display
            current_mb = current / (1024 * 1024)
            total_mb = total / (1024 * 1024)

            # Create status text based on operation type
            if operation_type == "upload":
                status_text = f"Uploading: {filename}\n{current_mb:.2f} MB / {total_mb:.2f} MB ({percent:.1f}%)\nSpeed: {speed_str} | Remaining: {remaining_str}"
            else:
                status_text = f"Downloading: {filename}\n{current_mb:.2f} MB / {total_mb:.2f} MB ({percent:.1f}%)\nSpeed: {speed_str} | Remaining: {remaining_str}"

            self.status_bar.configure(text=status_text)
            self.progress_bar.set(percent / 100)

        # Schedule GUI update on main thread
        self.after(0, update_gui)

    async def _upload_single_file_async(self, args):
        """Upload a single file asynchronously with progress tracking"""
        path = Path(args["path"])
        filename = path.name

        if args["prefix"]:
            filename = args["prefix"] + filename

        # Initialize progress tracking
        file_size = path.stat().st_size
        self._operation_start_time = time()
        self._operation_filename = filename

        self.status_bar.configure(text=f"Uploading: {filename} (0 MB / {file_size / (1024*1024):.2f} MB)")

        file_type = args["file_type"]
        chat_id = args["chat_id"]

        # Create progress callback with operation type
        def progress_callback(current, total):
            self._progress_callback(current, total, "upload", filename)

        try:
            if file_type == "Photo" or (file_type == "Auto-detect" and path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']):
                await self.client.send_photo(
                    chat_id,
                    str(path),
                    caption=args["caption"] if args["caption"] else None,
                    disable_notification=args["silent"],
                    progress=progress_callback
                )
            elif file_type == "Video" or (file_type == "Auto-detect" and path.suffix.lower() in ['.mp4', '.mkv', '.avi', '.mov', '.webm']):
                thumb = None
                if args["thumbnail"] == "auto":
                    if HAS_MOVIEPY:
                        thumb = Path("thumb") / f"THUMB_{path.stem}.jpg"
                        Path("thumb").mkdir(exist_ok=True)
                        with VideoFileClip(str(path)) as video:
                            from math import floor
                            video.save_frame(str(thumb), t=floor(video.duration / 2))
                elif args["thumbnail"]:
                    thumb = args["thumbnail"]

                await self.client.send_video(
                    chat_id,
                    str(path),
                    caption=args["caption"] if args["caption"] else None,
                    disable_notification=args["silent"],
                    thumb=thumb,
                    progress=progress_callback
                )
            elif file_type == "Audio" or (file_type == "Auto-detect" and path.suffix.lower() in ['.mp3', '.wav', '.ogg', '.flac', '.m4a']):
                await self.client.send_audio(
                    chat_id,
                    str(path),
                    caption=args["caption"] if args["caption"] else None,
                    disable_notification=args["silent"],
                    progress=progress_callback
                )
            else:
                await self.client.send_document(
                    chat_id,
                    str(path),
                    caption=args["caption"] if args["caption"] else None,
                    disable_notification=args["silent"],
                    file_name=filename,
                    progress=progress_callback
                )

            if args["delete_original"]:
                path.unlink()

            self.after(0, lambda: self.status_bar.configure(text=f"Uploaded: {filename}"))
            self.after(0, lambda: self.progress_bar.set(1))

        except Exception as e:
            raise e

    async def _upload_folder_async(self, args):
        """Upload all files in a folder asynchronously"""
        path = Path(args["path"])
        files = []

        if args["recursive"]:
            for f in path.rglob("*"):
                if f.is_file():
                    files.append(f)
        else:
            for f in path.glob("*"):
                if f.is_file():
                    files.append(f)

        for i, file_path in enumerate(files):
            if not self.operation_running:
                break

            progress = (i + 1) / len(files)
            self.progress_bar.set(progress)

            file_args = args.copy()
            file_args["path"] = str(file_path)
            try:
                await self._upload_single_file_async(file_args)
            except Exception as e:
                self.status_bar.configure(text=f"Error uploading {file_file}: {e}")

    def start_batch_upload(self):
        """Start batch upload operation using the worker thread"""
        if not self.batch_queue:
            messagebox.showwarning("Warning", "No files in queue!")
            return

        self.operation_running = True
        self.btn_batch_start.configure(state="disabled")

        chat_id = self.batch_chat_var.get() or "me"
        caption = self.batch_caption_text.get("1.0", "end").strip()
        silent = self.batch_silent.get()
        delete_original = self.batch_delete.get()
        use_filename_caption = self.batch_use_filename_caption.get()

        self._log("INFO", f"Starting batch upload of {len(self.batch_queue)} files (order preserved)")

        # Create upload args for each file in order (no rearrangement)
        upload_args_list = []
        for path in self.batch_queue:
            args = {
                "path": path,
                "recursive": False,
                "file_type": "Auto-detect",
                "thumbnail": None,
                "caption": caption,
                "use_filename_caption": use_filename_caption,
                "chat_id": chat_id,
                "prefix": None,
                "split_size": 0,
                "silent": silent,
                "spoiler": False,
                "protect": False,
                "delete_original": delete_original,
            }
            upload_args_list.append(args)

        # Send batch upload command to worker thread
        self.command_queue.put({
            "type": "batch_upload",
            "args_list": upload_args_list
        })

        # Start polling for results
        self._batch_total = len(upload_args_list)
        self._batch_completed = 0
        self.after(100, self._poll_batch_result)

    def _poll_batch_result(self):
        """Poll for batch upload result"""
        try:
            result = self.result_queue.get_nowait()

            if result.get("success"):
                self._log("INFO", "Batch upload completed successfully")
                self._on_batch_complete()
            else:
                error = result.get("error", "Unknown error")
                self._log("ERROR", f"Batch upload failed: {error}")
                self._on_batch_error(error)

        except queue.Empty:
            # Not ready yet, check again
            self.after(100, self._poll_batch_result)

    def _on_batch_complete(self):
        """Handle batch upload completion"""
        self.operation_running = False
        self.btn_batch_start.configure(state="normal")
        self.progress_bar.set(1)
        self.status_bar.configure(text="Batch upload completed")
        messagebox.showinfo("Complete", "Batch upload completed successfully!")

    def _on_batch_error(self, error):
        """Handle batch upload error"""
        self.operation_running = False
        self.btn_batch_start.configure(state="normal")
        self.status_bar.configure(text="Batch upload failed")
        messagebox.showerror("Error", f"Batch upload failed:\n{error}")

    def _on_upload_complete(self):
        """Handle upload completion"""
        self.operation_running = False
        self.btn_upload.configure(state="normal")
        self.btn_cancel_upload.configure(state="disabled")
        self.progress_bar.set(1)
        self.status_bar.configure(text="Upload completed")
        messagebox.showinfo("Complete", "Upload completed successfully!")

    def _on_upload_error(self, error):
        """Handle upload error"""
        self.operation_running = False
        self.btn_upload.configure(state="normal")
        self.btn_cancel_upload.configure(state="disabled")
        self.status_bar.configure(text="Upload failed")
        messagebox.showerror("Error", f"Upload failed:\n{error}")

    def start_download(self):
        """Start download operation using the worker thread"""
        mode = self.download_mode_combo.get()
        download_dir = self.download_dir_var.get()

        if not download_dir:
            download_dir = str(Path.cwd() / "downloads")

        Path(download_dir).mkdir(parents=True, exist_ok=True)

        self.operation_running = True
        self.btn_download.configure(state="disabled")
        self.btn_cancel_download.configure(state="normal")
        self.progress_bar.set(0)

        self._log("INFO", f"Starting download in mode: {mode}")

        if mode == "From Link(s)":
            links_text = self.text_links.get("1.0", "end").strip()
            links = [l.strip() for l in links_text.split('\n') if l.strip()]

            self.command_queue.put({
                "type": "download",
                "mode": mode,
                "download_dir": download_dir,
                "links": links
            })
        elif mode == "From Message ID(s)":
            chat_id = self.download_chat_var.get()
            msg_ids = self.msg_ids_var.get().split()

            self.command_queue.put({
                "type": "download",
                "mode": mode,
                "download_dir": download_dir,
                "chat_id": chat_id,
                "msg_ids": msg_ids
            })

        # Start polling for results
        self.after(100, self._poll_operation_result, "download")

    async def _download_from_link_async(self, link, download_dir):
        """Download file from Telegram link asynchronously with progress tracking"""
        parts = link.replace(" ", "").split('/')

        if 't.me' not in parts:
            raise ValueError("Invalid Telegram link")

        if 'c' in parts:
            chat_id = int(f"-100{parts[4]}")
        else:
            chat_id = parts[3]

        msg_id = int(parts[-1])

        # Initialize progress tracking for download
        self._operation_start_time = time()

        message = await self.client.get_messages(chat_id, msg_id)

        # Get filename from message media
        filename = "file"
        if message.document:
            filename = message.document.file_name or "file"
        elif message.video:
            filename = message.video.file_name or "video"
        elif message.audio:
            filename = message.audio.file_name or "audio"
        elif message.photo:
            filename = "photo.jpg"

        self._operation_filename = filename

        # Create progress callback for download
        def progress_callback(current, total):
            self._progress_callback(current, total, "download", filename)

        await self.client.download_media(message, file_name=download_dir, progress=progress_callback)

    def _on_download_complete(self):
        """Handle download completion"""
        self.operation_running = False
        self.btn_download.configure(state="normal")
        self.btn_cancel_download.configure(state="disabled")
        self.progress_bar.set(1)
        self.status_bar.configure(text="Download completed")
        messagebox.showinfo("Complete", "Download completed successfully!")

    def _on_download_error(self, error):
        """Handle download error"""
        self.operation_running = False
        self.btn_download.configure(state="normal")
        self.btn_cancel_download.configure(state="disabled")
        self.status_bar.configure(text="Download failed")
        messagebox.showerror("Error", f"Download failed:\n{error}")

    def calculate_hash(self):
        """Calculate file hash"""
        path = self.hash_file_var.get()
        if not path:
            messagebox.showwarning("Warning", "Please select a file!")
            return

        if not Path(path).exists():
            messagebox.showerror("Error", "File does not exist!")
            return

        hash_type = self.hash_type_combo.get()
        self.hash_result.delete("1.0", "end")

        try:
            file_size = Path(path).stat().st_size
            chunk_size = min(1024 * 1024, file_size)
            bytes_read = 0

            sha256 = hashlib.sha256()
            md5 = hashlib.md5()

            with open(path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    if hash_type in ["SHA256", "SHA256 + MD5"]:
                        sha256.update(chunk)
                    if hash_type in ["MD5", "SHA256 + MD5"]:
                        md5.update(chunk)

                    bytes_read += len(chunk)
                    progress = bytes_read / file_size * 100
                    self.progress_bar.set(progress / 100)

            result = f"File: {Path(path).name}\n"
            if hash_type in ["SHA256", "SHA256 + MD5"]:
                result += f"SHA256: {sha256.hexdigest()}\n"
            if hash_type in ["MD5", "SHA256 + MD5"]:
                result += f"MD5: {md5.hexdigest()}\n"

            self.hash_result.insert("1.0", result)
            self.progress_bar.set(0)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to calculate hash:\n{e}")

    def split_file_utility(self):
        """Split file utility"""
        path = self.split_file_var.get()
        if not path:
            messagebox.showwarning("Warning", "Please select a file!")
            return

        try:
            chunk_size = int(self.split_size_var.get())
            if chunk_size <= 0:
                messagebox.showerror("Error", "Chunk size must be greater than 0!")
                return
        except ValueError:
            messagebox.showerror("Error", "Invalid chunk size!")
            return

        output_dir = Path(path).parent / "split"
        output_dir.mkdir(exist_ok=True)

        filename = Path(path).stem

        try:
            file_size = Path(path).stat().st_size
            num_chunks = file_size // chunk_size + (1 if file_size % chunk_size else 0)

            with open(path, 'rb') as f:
                for i in range(num_chunks):
                    chunk_file = output_dir / f"{filename}.part{i}"
                    with open(chunk_file, 'wb') as cf:
                        cf.write(f.read(chunk_size))

                    progress = (i + 1) / num_chunks
                    self.progress_bar.set(progress)

            messagebox.showinfo(
                "Complete",
                f"File split into {num_chunks} parts.\nSaved to: {output_dir}"
            )
            self.progress_bar.set(0)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to split file:\n{e}")

    def combine_files_utility(self):
        """Combine files utility"""
        if not hasattr(self, 'combine_files_selected') or not self.combine_files_selected:
            messagebox.showwarning("Warning", "Please select part files first!")
            return

        output_name = self.combine_output_var.get()
        if not output_name:
            output_name = Path(self.combine_files_selected[0]).stem

        output_path = Path.cwd() / "combine" / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            total_size = sum(Path(f).stat().st_size for f in self.combine_files_selected)
            bytes_written = 0

            with open(output_path, 'wb') as out:
                for filepath in self.combine_files_selected:
                    with open(filepath, 'rb') as f:
                        while True:
                            chunk = f.read(1024 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                            bytes_written += len(chunk)
                            self.progress_bar.set(bytes_written / total_size)

            messagebox.showinfo(
                "Complete",
                f"Files combined successfully.\nSaved to: {output_path}"
            )
            self.progress_bar.set(0)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to combine files:\n{e}")

    def capture_frame(self):
        """Capture video frame"""
        if not HAS_MOVIEPY:
            messagebox.showerror("Error", "moviepy not installed!\nRun: pip install moviepy")
            return

        path = self.frame_video_var.get()
        if not path:
            messagebox.showwarning("Warning", "Please select a video file!")
            return

        try:
            time_sec = int(self.frame_time_var.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid time value!")
            return

        output_path = Path.cwd() / "thumb" / f"THUMB_{Path(path).stem}.jpg"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with VideoFileClip(path) as video:
                video.save_frame(str(output_path), t=time_sec)

            messagebox.showinfo(
                "Complete",
                f"Frame captured successfully.\nSaved to: {output_path}"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to capture frame:\n{e}")

    def get_file_info(self):
        """Get file information"""
        path = self.info_file_var.get()
        if not path:
            messagebox.showwarning("Warning", "Please select a file!")
            return

        if not Path(path).exists():
            messagebox.showerror("Error", "File does not exist!")
            return

        try:
            file_path = Path(path)
            stat = file_path.stat()

            file_size = stat.st_size
            created = datetime.fromtimestamp(stat.st_ctime)
            modified = datetime.fromtimestamp(stat.st_mtime)

            info = f"File: {file_path.name}\n"
            info += f"Path: {file_path.absolute()}\n\n"
            info += f"Size: {file_size:,} bytes\n"
            info += f"        {file_size / 1024:.2f} KB\n"
            info += f"        {file_size / (1024 * 1024):.2f} MB\n\n"
            info += f"Created: {created.strftime('%Y-%m-%d %H:%M:%S')}\n"
            info += f"Modified: {modified.strftime('%Y-%m-%d %H:%M:%S')}\n"

            self.info_result.delete("1.0", "end")
            self.info_result.insert("1.0", info)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to get file info:\n{e}")

    def convert_image(self):
        """Convert image to JPEG"""
        path = self.convert_file_var.get()
        if not path:
            messagebox.showwarning("Warning", "Please select an image file!")
            return

        if not Path(path).exists():
            messagebox.showerror("Error", "File does not exist!")
            return

        try:
            from PIL import Image

            img = Image.open(path)
            output_path = Path(path).stem + ".jpg"
            img.convert('RGB').save(output_path)

            messagebox.showinfo(
                "Complete",
                f"Image converted successfully.\nSaved to: {output_path}"
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to convert image:\n{e}")

    def check_updates(self):
        """Check for updates"""
        try:
            json_endpoint = "https://cdn.thecaduceus.eu.org/tg-upload/release.json"
            response = get_url(json_endpoint, timeout=5)
            release_json = response.json()

            latest = release_json["latestRelease"]["version"]
            if TG_UPLOAD_VERSION != latest:
                self.status_bar.configure(
                    text=f"Update available: v{latest}"
                )
        except:
            pass


class ProfileDialog(ctk.CTkToplevel):
    """Profile editing dialog"""

    def __init__(self, parent, name, data):
        super().__init__(parent)

        self.title(f"Edit Profile: {name}")
        self.geometry("500x500")
        self.resizable(False, False)

        self.result = None
        self.data = data

        self.setup_ui(name)

        self.transient(parent)
        self.grab_set()
        self.wait_window()

    def setup_ui(self, name):
        """Setup profile dialog UI"""
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="API ID:*").grid(
            row=0, column=0, padx=10, pady=10, sticky="w"
        )
        self.entry_api_id = ctk.CTkEntry(self)
        self.entry_api_id.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.entry_api_id.insert(0, self.data.get("api_id", ""))

        ctk.CTkLabel(self, text="API Hash:*").grid(
            row=1, column=0, padx=10, pady=10, sticky="w"
        )
        self.entry_api_hash = ctk.CTkEntry(self, show="*")
        self.entry_api_hash.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.entry_api_hash.insert(0, self.data.get("api_hash", ""))

        ctk.CTkLabel(self, text="Phone:").grid(
            row=2, column=0, padx=10, pady=10, sticky="w"
        )
        self.entry_phone = ctk.CTkEntry(self)
        self.entry_phone.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        self.entry_phone.insert(0, self.data.get("phone", ""))

        ctk.CTkLabel(self, text="Bot Token:").grid(
            row=3, column=0, padx=10, pady=10, sticky="w"
        )
        self.entry_bot = ctk.CTkEntry(self, show="*")
        self.entry_bot.grid(row=3, column=1, padx=10, pady=10, sticky="ew")
        self.entry_bot.insert(0, self.data.get("bot_token", ""))

        ctk.CTkLabel(self, text="Session String:").grid(
            row=4, column=0, padx=10, pady=10, sticky="w"
        )
        self.entry_session = ctk.CTkEntry(self, show="*")
        self.entry_session.grid(row=4, column=1, padx=10, pady=10, sticky="ew")
        self.entry_session.insert(0, self.data.get("session_string", ""))

        ctk.CTkLabel(self, text="Device Model:").grid(
            row=5, column=0, padx=10, pady=10, sticky="w"
        )
        self.entry_device = ctk.CTkEntry(self)
        self.entry_device.grid(row=5, column=1, padx=10, pady=10, sticky="ew")
        self.entry_device.insert(0, self.data.get("device_model", "tg-upload-gui"))

        self.hide_password = ctk.BooleanVar(value=self.data.get("hide_password", False))
        ctk.CTkCheckBox(
            self, text="Hide 2FA password", variable=self.hide_password
        ).grid(row=6, column=0, columnspan=2, padx=10, pady=10, sticky="w")

        btn_frame = ctk.CTkFrame(self)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=20)

        ctk.CTkButton(btn_frame, text="Save", command=self.save).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="#d32f2f",
                      command=self.destroy).pack(side="right", padx=10)

        ctk.CTkLabel(
            self,
            text="* Required fields. Provide only one of: Phone, Bot Token, or Session String",
            font=ctk.CTkFont(size=10)
        ).grid(row=8, column=0, columnspan=2, padx=10, pady=5)

    def save(self):
        """Save profile data"""
        api_id = self.entry_api_id.get().strip()
        api_hash = self.entry_api_hash.get().strip()

        if not api_id or not api_hash:
            messagebox.showerror("Error", "API ID and API Hash are required!")
            return

        phone = self.entry_phone.get().strip()
        bot_token = self.entry_bot.get().strip()
        session_string = self.entry_session.get().strip()

        auth_methods = sum([bool(phone), bool(bot_token), bool(session_string)])
        if auth_methods == 0:
            messagebox.showerror(
                "Error",
                "Please provide at least one authentication method:\n"
                "- Phone number (user account)\n"
                "- Bot token (bot account)\n"
                "- Session string (existing session)"
            )
            return

        if auth_methods > 1:
            messagebox.showerror(
                "Error",
                "Please provide only ONE authentication method!"
            )
            return

        self.result = {
            "api_id": api_id,
            "api_hash": api_hash,
            "phone": phone or None,
            "bot_token": bot_token or None,
            "session_string": session_string or None,
            "hide_password": self.hide_password.get(),
            "device_model": self.entry_device.get().strip() or "tg-upload-gui",
        }

        self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    """Settings dialog"""

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Settings")
        self.geometry("500x400")
        self.resizable(False, False)

        self.parent = parent
        self.setup_ui()

        self.transient(parent)
        self.grab_set()
        self.wait_window()

    def setup_ui(self):
        """Setup settings UI"""
        self.grid_columnconfigure(0, weight=1)

        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame, text="Caption Templates",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)

        ctk.CTkLabel(
            frame,
            text="Edit captions.json file in the application directory\nto manage caption templates."
        ).pack(pady=10)

        ctk.CTkLabel(
            frame, text="Proxy Configuration",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(20, 10))

        ctk.CTkButton(
            frame, text="Open proxies.json",
            command=self.open_proxies_file
        ).pack(pady=5)

        ctk.CTkLabel(
            frame,
            text="Edit proxies.json to add/edit/remove proxy configurations."
        ).pack(pady=5)

        ctk.CTkButton(
            frame, text="Close", command=self.destroy
        ).pack(pady=20)

    def open_proxies_file(self):
        """Open proxies file"""
        if not PROXIES_FILE.exists():
            sample = {
                "my_proxy": {
                    "scheme": "socks5",
                    "hostname": "127.0.0.1",
                    "port": 1080,
                    "username": "",
                    "password": ""
                }
            }
            with open(PROXIES_FILE, 'w') as f:
                json_dump(sample, f, indent=2)

        try:
            import subprocess
            subprocess.run(['notepad', str(PROXIES_FILE)])
        except:
            messagebox.showinfo(
                "Info",
                f"Please open and edit:\n{PROXIES_FILE}"
            )


def main():
    """Main entry point"""
    if not HAS_CUSTOMTKINTER:
        print("Error: customtkinter is required. Please install it with:")
        print("pip install customtkinter")
        sys.exit(1)

    if not HAS_PYROGRAM:
        print("Warning: pyrogram not installed. Install with:")
        print("pip install pyrogram tgcrypto")

    app = TGUploadGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
