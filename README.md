# 🎬 Cheat Clip PRO

> **AI Powered Auto Clipper — Turn long YouTube, Google Drive, and uploaded videos into viral TikToks, Shorts, and Reels with animated subtitles, face centering, and music in minutes.**

---

## ⚡ Quick Start & Setup

Follow these steps to set up and run Cheat Clip PRO locally on **Windows**, **macOS**, or **Linux**.

### Step 1: Prerequisites

Make sure you have the following installed:

1. **[Git](https://git-scm.com/)**
   * **Windows:** `winget install Git.Git` or download from [git-scm.com](https://git-scm.com/)
   * **macOS:** `brew install git`
   * **Linux:** `sudo apt install git`
2. **[Node.js](https://nodejs.org/)** (v18 or newer)
   * Download from [nodejs.org](https://nodejs.org/) or install via your package manager.
3. **[Python](https://www.python.org/)** (v3.10 or newer)
   * **Windows:** Install from [python.org](https://www.python.org/downloads/) (make sure to check *"Add Python to PATH"* during setup) or from Microsoft Store.
   * **macOS:** `brew install python`
   * **Linux:** `sudo apt install python3 python3-pip python3-venv`
4. **FFmpeg & yt-dlp** (Required to download, slice, and render clips)
   * **Windows (PowerShell):**
     ```powershell
     winget install Gyan.FFmpeg
     winget install yt-dlp.yt-dlp
     ```
     *(Close and reopen your terminal after installing so Windows recognizes them)*
   * **macOS (Terminal):**
     ```bash
     brew install ffmpeg-full yt-dlp
     ```
      `ffmpeg-full` is required for the libass subtitle filter used by rendered captions.
   * **Linux:**
     ```bash
     sudo apt update && sudo apt install ffmpeg
     pip install yt-dlp
     ```

---

### Step 2: Clone the Repository

Open your terminal and clone the repository:

```bash
git clone https://github.com/galihjuansaputra/cheat-clip-pro.git
cd cheat-clip-pro
```

---

### Step 3: Install Dependencies

#### 1. Frontend Dependencies
```bash
npm install
```

#### 2. Backend Dependencies
We recommend setting up a Python virtual environment:

* **Windows:**
  ```powershell
  python -m venv venv
  venv\Scripts\activate
  pip install -r backend/requirements.txt
  ```

* **macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r backend/requirements.txt
  ```

---

### Step 4: Run the App

Launch both the frontend and backend servers concurrently:

```bash
npm run dev
```

* **Web App:** [`http://localhost:5173`](http://localhost:5173)
* **Backend API:** [`http://localhost:8000`](http://localhost:8000)
* **API Documentation:** [`http://localhost:8000/docs`](http://localhost:8000/docs)
* **Health check:** [`http://localhost:8000/api/health`](http://localhost:8000/api/health)

The health endpoint preserves its existing API-liveness `status` for restart
reconnection; inspect `render_health.status` and its individual checks for
FFmpeg, subtitles, encoder, and storage readiness.

#### Start automatically after Windows sign-in

After installing Node.js and running `npm install`, double-click
`scripts/install-startup.bat` once. This registers a per-user Windows Task Scheduler
task to start both app servers after you sign in; it does not require administrator
permissions and does not run before login. Start the servers manually with
`start.bat` if they do not come up, then inspect
`%LOCALAPPDATA%\CheatClipPro\logs\startup.log` and `app.stderr.log`.
Double-click `scripts/uninstall-startup.bat` to remove automatic startup. Removing
the task does not stop an app that is already running.

#### Optional persistent render queue

By default, render jobs use an in-memory queue for desktop installations. To persist
render batches and queued work across backend restarts, install the backend
dependencies and set `REDIS_URL` to a reachable Redis instance before starting the
backend. For example:

```env
REDIS_URL=redis://localhost:6379/0
REDIS_PREFIX=cheat-clip-pro
```

When `REDIS_URL` is set, the backend starts a Redis-backed render worker and fails
startup if Redis is unavailable rather than silently falling back to volatile
storage. Leave `REDIS_URL` unset to keep using the in-memory desktop queue.
Run a single Uvicorn backend process for each `REDIS_PREFIX`; API progress state
is synchronized inside that process while Redis provides queue and restart
persistence.
Run backend regression tests with `python -m unittest discover -s backend/tests`.
The real-Redis recovery test is skipped unless `REDIS_URL` points to a reachable
Redis server; run it with that environment variable set to verify the Redis
queue/persistence behavior against the configured instance.

### Accounts, shared projects, and audit

The app requires an account to use its API. Create an account from the sign-in screen;
the account that creates a project becomes its **Owner**. Owners can grant **Admin**,
**Editor**, or **Viewer** access to other registered email addresses. Admins manage
project members, Editors can save shared content, and Viewers have read-only access.
Project members can share saved video analyses and render settings. Project owners
and admins can review the project activity audit; users can only access projects they
belong to.

Account and project data is stored in `backend/data/enterprise.sqlite3` by default
and is intentionally excluded from Git. Set `ENTERPRISE_DB_PATH` to use another
persistent SQLite file. Account passwords are salted and hashed; sign-in uses
HttpOnly, SameSite session cookies. For HTTPS deployments, set
`SESSION_COOKIE_SECURE=true`. The SQLite database is intended for a single backend
instance with persistent local storage; use an appropriately shared database and
session architecture before scaling to multiple backend instances.

---

## 🔄 Updating to the Latest Version

To update Cheat Clip PRO to the latest release:

```bash
git pull
npm install
pip install -r backend/requirements.txt
```
*(Make sure your virtual environment is activated if you created one)*

---

## 🔑 Free Google Gemini API Key (Takes 1 Minute)

Cheat Clip PRO uses Google's AI to find the best viral moments for free:
1. Go to **[Google AI Studio](https://aistudio.google.com/)** and sign in with any Google account.
2. Click **"Get API key"** (or **"Create API key"**).
3. Copy your key (starts with `AIzaSy...`).
4. Paste it into the **Gemini API Key** field in the app.

> 💡 **Tip:** You can also type `mock` in the API Key box to test out the app with sample data without an API key!

---

## 🎯 How to Use

1. **Paste a YouTube URL** — Enter any podcast, stream, or video link.
2. **Choose Duration** — Pick `~15s` (fast hooks), `~30s` (standard shorts), or `~60s` (story clips).
3. **Click "Analyze Video"** — The AI finds the most exciting moments using YouTube audience retention data.
4. **Customize in Clip Studio** — Adjust your video style:
   * **Frame & Crop**: Fullscreen 9:16 vertical, square, or split-screen facecam.
   * **Face Tracking**: Automatically keeps the speaker in the center of the frame.
   * **Subtitles**: Choose viral animated karaoke caption styles and fonts.
   * **Branding & Audio**: Add your watermark logo, background music, and hook sound effects.
   * **Hardware Acceleration**: Choose your graphics card (NVIDIA, AMD, Intel) or CPU.
5. **Batch Render & Download** — Click **Batch Render**, then download all your finished videos together in one **.ZIP** file!

---

## ❓ Common Problems & Easy Fixes

### 1. "Failed to render video" or `The system cannot find the file specified`
* **Cause:** `ffmpeg` or `yt-dlp` is missing on your computer.
* **Fix:**
  * **Windows (PowerShell):**
    ```powershell
    winget install Gyan.FFmpeg
    winget install yt-dlp.yt-dlp
    ```
    *(Then close and reopen your terminal)*
  * **Mac (Terminal):**
    ```bash
    brew install ffmpeg-full yt-dlp
    ```
  * Or install directly via Python: `pip install yt-dlp`

### 2. `No such filter: 'subtitles'`
* **Cause:** FFmpeg was installed without the libass subtitle filter.
* **Fix (macOS):**
  ```bash
  brew install ffmpeg-full
  ```
  Restart the backend after installation. The app automatically prefers Homebrew's subtitle-capable `ffmpeg-full` binary.

### 3. "Sign in to confirm you're not a bot"
* **Cause:** YouTube blocks video downloads if too many requests are sent without logging in.
* **Fix:** Click the 🍪 **Cookies** button in the top navigation bar, export your YouTube cookies using a free browser extension (like *Get cookies.txt locally*), and paste them into the app.

### 4. Does this work on AMD graphics cards and Mac?
* **Yes!** Cheat Clip PRO automatically supports:
  * **NVIDIA** (`h264_nvenc`)
  * **AMD** (`h264_amf` on Radeon GPUs & Ryzen CPUs)
  * **Intel** (`h264_qsv` on Arc & UHD Graphics)
  * **Apple Mac & CPU Software** (`libx264` universal high-speed fallback)
* You can switch your preferred hardware acceleration encoder anytime in the Render Settings or History card.

---

## 📄 License

Distributed under the **MIT License**. Free for personal and commercial use!
