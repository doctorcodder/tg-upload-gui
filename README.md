# 🚀 Telegram Upload GUI

<div align="center">

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue?style=for-the-badge&logo=python)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
![Pyrogram](https://img.shields.io/badge/Pyrogram-2.0-orange?style=for-the-badge&logo=telegram)
![CustomTkinter](https://img.shields.io/badge/CustomTkinter-5.0-blueviolet?style=for-the-badge)

*A powerful and feature-rich desktop application for managing Telegram file transfers with parallel operations, batch processing, and chat cloning capabilities.*

</div>

---

## 📋 Table of Contents

- [✨ Features](#-features)
- [🚀 Quick Start](#-quick-start)
- [🛠️ Installation](#️-installation)
- [📖 Usage Guide](#-usage-guide)
- [⚙️ Configuration](#️-configuration)
- [🎨 Interface Overview](#-interface-overview)
- [🐛 Troubleshooting](#-troubleshooting)
- [🤝 Contributing](#-contributing)
- [📝 License](#-license)
- [🙏 Acknowledgments](#-acknowledgments)

---

## ✨ Features

### Core Functionality

| Feature | Description |
|---------|-------------|
| 📤 **Single File Upload** | Upload individual files to any Telegram chat with customizable captions |
| 📥 **Single File Download** | Download media files from Telegram with progress tracking |
| 📚 **Batch Operations** | Process multiple files simultaneously with queue management |
| 🔍 **Chat Explorer** | Browse and manage Telegram chats directly from the interface |

### Advanced Features

#### 🔄 Parallel Operations

Achieve maximum transfer speeds with intelligent parallelization:

- **Parallel Upload** 🔀 - Files are split into chunks and uploaded simultaneously using Telegram's `SaveBigFilePart` method
- **Parallel Download** ⚡ - Downloads leverage Pyrogram's optimized media handling for faster retrieval
- **Configurable Performance** 🎛️ - Adjust chunk sizes and parallelization settings to match your connection

#### 📑 Chat Clone

Powerful feature for duplicating channel or group content:

- **Source & Destination** 🔀 - Choose any Telegram chat as source and any as destination
- **Selective Cloning** 🎯 - Filter by message ID range and media types (photos, videos, documents, etc.)
- **Auto-Cleanup** 🧹 - Automatically remove downloaded files after successful upload to save disk space
- **Smart Intervals** ⏱️ - Set sleep intervals between operations to avoid rate limiting
- **Real-time Progress** 📊 - Track each file's progress during the clone process

#### 📦 Batch Upload with Resume/Retry

Robust batch processing with complete failure recovery:

- **State Persistence** 💾 - Batch progress is automatically saved, allowing resume after interruptions
- **Interactive Recovery** 🔁 - When files fail, choose to retry, skip, skip all, or cancel
- **Visual Status Tracking** 👁️ - Clear indicators: ✅ Success, ❌ Failed, ⏳ Pending, ⏩ Skipped
- **Seamless Resume** ↩️ - Reopen the app and continue where you left off without losing progress

### User Experience

| UX Feature | Benefit |
|------------|---------|
| 🌙 **Dark Mode** | Modern, eye-friendly dark theme built with CustomTkinter |
| 📋 **Clipboard Integration** | Paste button next to all Chat ID fields for quick input |
| 📊 **Progress Monitoring** | Real-time progress bars with speed and ETA calculations |
| 🔌 **Connection Management** | Easy connect/disconnect with visual status indicators |
| 💾 **Auto-Save Settings** | All configurations saved automatically and restored on launch |

---

## 🚀 Quick Start

### Prerequisites

- 🐍 **Python 3.8** or higher
- 📱 **Telegram API credentials** (api_id and api_hash)
- 📦 **Required Python packages**

### 3-Step Setup

```bash
# 1️⃣ Clone the repository
git clone https://github.com/doctorcodder/tg-upload-gui.git
cd tg-upload-gui

# 2️⃣ Install dependencies
pip install -r requirements.txt

# 3️⃣ Run the application
python tg-upload-gui.py
```

> 💡 **Tip:** On Windows, simply double-click `run.bat` to install dependencies and launch!

---

## 🛠️ Installation

### Step 1: Get Telegram API Credentials

1. Go to [my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Click **"API Development Tools"**
4. Create a new application
5. Note your `api_id` and `api_hash`

### Step 2: Install Python Dependencies

#### Using pip (Recommended)

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# OR
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

#### requirements.txt Contents

```
pyrogram>=2.0
customtkinter>=5.0
humanize>=4.0
tgcrypto>=1.2
```

#### System Dependencies

**Windows:** No additional setup required

**Linux:**
```bash
sudo apt-get install python3-tk  # For tkinter support
```

**macOS:**
```bash
brew install python-tk  # Via Homebrew
```

### Step 3: Launch the Application

```bash
# Method 1: Direct Python execution
python tg-upload-gui.py

# Method 2: Using the batch file (Windows)
run.bat

# Method 3: Make executable (Linux/Mac)
chmod +x tg-upload-gui.py
./tg-upload-gui.py
```

---

## 📖 Usage Guide

### 🔗 Connecting to Telegram

1. Launch the application
2. Enter your `api_id` and `api_hash`
3. Click **"Connect"** 🔌
4. Enter your phone number 📱
5. Enter the verification code sent to your Telegram app
6. ✅ Your session will be saved for future use

> ⚠️ **Important:** Keep your `api_id` and `api_hash` confidential!

### 📤 Single File Upload

1. Navigate to the **Upload** tab 📤
2. Enter the destination Chat ID
   - Use **Chat Explorer** to select a chat
   - Or paste manually (e.g., `-1001234567890`)
3. Click **"Select File"** 📂
4. Set a caption (optional)
5. Configure scheduling (optional)
6. Click **"Upload"** 🚀

### 📥 Single File Download

1. Navigate to the **Download** tab 📥
2. Enter the source Chat ID
3. Enter the Message ID 📝
4. Choose a local directory 📁
5. Click **"Download"** ⬇️

### 📦 Batch Upload

#### Adding Files

1. Navigate to the **Batch** tab 📚
2. Click **"Add Files"** ➕ for individual files
3. Or **"Add Folder"** 📂 for entire directories
4. Enter the destination Chat ID
5. Click **"Start Batch Upload"** ▶️

#### Managing Progress

| Action | How |
|--------|-----|
| **Track Progress** | Watch the status column for each file |
| **Resume After Restart** | Reopen the batch - progress resumes automatically |
| **Retry Failed** | Click **"Retry Failed"** 🔄 to attempt again |
| **Clear Completed** | Use **"Clear Done"** 🗑️ to remove successful entries |

#### Status Icons

| Icon | Meaning |
|------|---------|
| ✅ | Upload successful |
| ❌ | Upload failed |
| ⏳ | Pending upload |
| ⏩ | Skipped |

### 📑 Chat Clone

1. Navigate to the **Clone** tab 📑
2. Configure **Source** 📍:
   - Enter source Chat ID
   - Set message range (start/end IDs)
   - Select media types to clone:
     - 🖼️ Photos
     - 🎥 Videos
     - 📄 Documents
     - 🎵 Audio
     - All media types
3. Configure **Destination** 🎯:
   - Enter destination Chat ID
4. Configure **Options** ⚙️:
   - Set sleep interval (seconds)
   - Enable **"Auto-delete local files"** 🗑️
5. Click **"Start Clone"** 🔄

> 💡 **Tip:** Start with a small message range to test the clone process!

### 🔍 Chat Explorer

1. Navigate to the **Explorer** tab 🔍
2. Select a chat from the dropdown 📋
3. Browse recent messages 💬
4. Click message actions to:
   - Copy Message ID 📝
   - Copy Chat ID 🔢
   - View media content 👁️

---

## ⚙️ Configuration

### Performance Settings

Navigate to the **Performance** tab ⚙️ to configure:

| Setting | Description | Default |
|---------|-------------|---------|
| 🔀 Parallel Upload | Split files into chunks for faster uploads | ✅ Enabled |
| ⚡ Parallel Download | Use optimized download method | ✅ Enabled |
| 📏 Chunk Size | Size of each upload chunk | 2 MB |

### Configuration File

The application creates a `config.json` file for settings:

```json
{
    "default_download_path": "./downloads",
    "chunk_size": 2097152,
    "parallel_upload": true,
    "parallel_download": true,
    "auto_delete_clone": false,
    "clone_sleep_interval": 1
}
```

### Session Management

- Sessions are stored in `.session` files
- Delete the session file to reset authentication
- Session is automatically restored on next launch

---

## 🎨 Interface Overview

### Main Window Layout

```
┌─────────────────────────────────────────────────────────────┐
│  📱 Telegram Upload GUI                              ⚙️ 🔌│
├─────────────────────────────────────────────────────────────┤
│  [Upload] [Download] [Batch] [Clone] [Explorer] [Perf]      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    Main Content                     │    │
│  │                                                     │    │
│  │              (Changes per tab)                      │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  📊 Progress Bar                          📝 Status: Idle  │
├─────────────────────────────────────────────────────────────┤
│  💾 Batch: 0/0  |  ⏱️ 00:00:00  |  ⚡ 0 KB/s              │
└─────────────────────────────────────────────────────────────┘
```

### Tab Descriptions

| Tab | Icon | Purpose |
|-----|------|---------|
| Upload | 📤 | Single file uploads |
| Download | 📥 | Single file downloads |
| Batch | 📚 | Multiple file queue processing |
| Clone | 📑 | Duplicate channel content |
| Explorer | 🔍 | Browse Telegram chats |
| Performance | ⚙️ | Configure transfer settings |

---

## 🐛 Troubleshooting

### 🔌 Connection Issues

| Problem | Solution |
|---------|----------|
| "Connect" fails | Verify API credentials are correct 🔑 |
| No internet | Check your network connection 🌐 |
| VPN blocking | Try disabling VPN or use a different network |
| Session expired | Delete `.session` file and reconnect |

### 📤 Upload/Download Failures

| Problem | Solution |
|---------|----------|
| Permission denied | Check destination folder permissions 🔐 |
| Disk full | Free up storage space 💾 |
| Large file timeout | Enable parallel mode in Performance tab ⚡ |
| Rate limited | Increase sleep interval in Clone settings ⏱️ |

### ⚡ Performance Issues

| Problem | Solution |
|---------|----------|
| Slow transfers | Enable parallel mode 🔀 |
| Memory usage high | Reduce chunk size in Performance 📏 |
| UI freezes | Normal during transfers - wait for completion ⏳ |

### 💾 State/Resume Problems

| Problem | Solution |
|---------|----------|
| Batch won't resume | Ensure `batch_state.json` exists |
| Lost progress | Progress auto-saves every few seconds |
| Stuck in loop | Try "Clear Done" then restart batch |

### 🔧 Getting More Help

1. Check the [Issues](../../issues) page
2. Search for similar problems
3. Create a new issue with:
   - Error message 📋
   - Steps to reproduce 🔄
   - System information 🖥️

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### How to Contribute

1. 🍴 Fork the repository
2. 🔧 Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. 💾 Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. 📤 Push to the branch (`git push origin feature/AmazingFeature`)
5. 🎉 Open a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/doctorcodder/tg-upload-gui.git
cd tg-upload-gui

# Create development environment
python -m venv dev
source dev/bin/activate

# Install development dependencies
pip install -r requirements.txt

# Make your changes...
# Test locally
python tg-upload-gui.py
```

### Code Style

- Follow PEP 8 guidelines 📐
- Add comments for complex logic 💬
- Test your changes before submitting ✅

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

### Built With

| Library | Purpose | Link |
|---------|---------|------|
| 🐍 **Pyrogram** | Telegram API client | [docs.pyrogram.org](https://docs.pyrogram.org/) |
| 🎨 **CustomTkinter** | Modern GUI framework | [github.com/TomSchimansky/CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| 👤 **Humanize** | Human-readable utilities | [humanize.readthedocs.io](https://humanize.readthedocs.io/) |
| 🔐 **TGCrypto** | Telegram encryption | [pypi.org/project/tgcrypto](https://pypi.org/project/tgcrypto/) |

### Inspiration

- Thanks to the Telegram team for their excellent API 📱
- Inspiration from various Telegram bot projects 🤖
- The open-source community for continuous support 🌟

---

## 📊 Project Statistics

<div align="center">

![GitHub Stars](https://img.shields.io/github/stars/doctorcodder/tg-upload-gui?style=for-the-badge&logo=github)
![GitHub Forks](https://img.shields.io/github/forks/doctorcodder/tg-upload-gui?style=for-the-badge&logo=github)
![GitHub Issues](https://img.shields.io/github/issues/doctorcodder/tg-upload-gui?style=for-the-badge&logo=github)

</div>

---

<div align="center">

**Made with ❤️ by doctorcodder**

*If you find this project useful, please consider ⭐ starring the repository!*

</div>

