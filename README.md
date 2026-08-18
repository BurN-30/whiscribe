**English** · [Français](README.fr.md)

# WhiScribe

Turn recordings into text on your own machine. No account, no cloud, no upload.

[![Release](https://img.shields.io/github/v/release/BurN-30/whiscribe?label=release)](https://github.com/BurN-30/whiscribe/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Windows](https://img.shields.io/badge/platform-Windows%2064--bit-lightgrey)

WhiScribe is a desktop app for Windows built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Drop audio files on the window, get text files next to them. It was written for meeting recordings: room audio, several voices, proper nouns and in-house jargon. The interface is available in English and French.

<!-- screenshot 1: main window, dark theme, drop area empty, hardware card visible -->

---

## Install

1. Download **`WhiScribe-Setup-X.Y.Z.exe`** from the [Releases](https://github.com/BurN-30/whiscribe/releases) page.
2. Run it.
3. Start **WhiScribe** from the Start menu.

Nothing else to install. The setup is per user, **no administrator rights**, and it installs into `%LOCALAPPDATA%\Programs\WhiScribe`. Your settings, glossary and logs live in `%LOCALAPPDATA%\WhiScribe`, never inside the program folder, so reinstalling a newer version over the old one loses nothing.

The setup asks **where to keep the transcription models**, 1.6 to 3.1 GB depending on the preset. The models are not bundled: they are downloaded once, on first use, and the app tells you the size before starting. After that it works offline.

The installer is not signed, so SmartScreen may warn on first run: "More info", then "Run anyway". See [Known limits](#known-limits).

> Two features are not in the setup, on purpose: **speaker separation** needs PyTorch, about 2.5 GB, and lives in the [source install](#run-from-source). Everything else is there.

---

## What it does

- **Drop and go.** Drag files or a folder onto the window, pick a preset, start. Files are processed one after another, a failure does not stop the queue.
- **Formats in:** `m4a` (including phone recordings), `mp3`, `wav`, `ogg`, `flac`, `opus`, `webm`, `wma`, `aac`, `amr`, and the usual video containers (`mp4`, `mkv`, `mov`), whose audio track is extracted.
- **Formats out:** `.txt` with a header (source, duration, model, date, real compute time), plus optional `.srt` and `.vtt`. Output names follow a configurable pattern with `{nom}`, `{date}`, `{heure}` and `{modele}`.
- **Two presets.** *Highest quality* (`large-v3`) for anything that will be read back, *Fast* (`large-v3-turbo`) to get the gist. Other Whisper models are reachable in advanced mode.
- **Glossary and corrections.** A list of proper nouns primes the model before it transcribes, and a list of rewrite rules cleans up the recurring mistakes afterwards. See [Vocabulary](#vocabulary-and-corrections).
- **Read back in the app.** Uncertain words are highlighted, any word shows its confidence on hover, and correcting one can be remembered for good. See [Reading back](#reading-back-a-transcript).
- **Copy for AI.** One button puts your own instruction template, the metadata and the full text on the clipboard, ready to paste into the assistant of your choice. Nothing is sent by the app.
- **Progressive saving.** Text is written segment by segment. A crash or a power cut does not lose the work: the app offers to resume at the next start.
- **Watched folder,** off by default. A folder can be watched so that new recordings join the queue on their own, which suits a dictaphone or a meeting recorder that always drops files in the same place.
- **Speaker separation,** optional, source install only. Produces a labelled transcript, `Speaker 1`, `Speaker 2`, which is worth a lot for a meeting summary.
- **Taskbar progress,** disk usage report, export and import of your data as a single zip file, dark and light theme, three keyboard shortcuts and no more: `Ctrl` + `O`, `Ctrl` + `Enter`, `Esc`.

<!-- gif: drop two files, pick the Fast preset, start, progress bar filling, a finished line with its Read back button (about 15 s, no sound) -->

---

## Privacy

**Nothing you transcribe leaves your computer.** No account, no API key, no upload to an online service, no telemetry. The audio is read from your disk, computed by your processor, and the text is written next to it.

Two things can use the network, both of them explicit:

- **Downloading a model**, once, the first time you use a preset. The app announces the size before starting.
- **The update check**, which is **off by default**. As long as it is off, the application makes no outgoing network call at all, apart from downloading the models you ask for.

Turned on, the update check queries the public releases page of this project at startup, **once a day at most**. Nothing about you or your files is sent, the call has a short timeout, and a failure, offline machine or firewall, produces no message at all: it goes to the log and that is it. A newer version shows a discreet banner with a button that opens the release page in your browser. Nothing downloads or installs on its own.

The Hugging Face token used for speaker separation is never included in an export, and never versioned.

---

## Vocabulary and corrections

Proper nouns, company names and technical terms are what automatic transcription mangles most. Two settings deal with that, and they complement each other.

**The glossary, `vocabulaire.txt`.** One term per line. The list is fed to the model **before** it transcribes, as the start of its context, which steers Whisper towards those spellings.

```
Jean Dupont
MyCompany
GitLab
Kubernetes
GDPR
```

A Whisper prompt cannot exceed **224 tokens**, roughly a hundred short terms. Beyond that, faster-whisper silently truncates. WhiScribe truncates cleanly instead, keeping the terms **at the top of the list**, and says so in the interface. Put the important ones first. The token count is exact: it uses the tokeniser of the model actually loaded. The introduction sentence of the prompt follows the **spoken language** of the recording, never the interface language: the model reads it as the beginning of a text, and a French sentence has no business at the head of an English recording.

**The corrections, `corrections.txt`.** For the recurring damage the prompt does not prevent. One rule per line, applied to the final text, case insensitive, whole words only, so the rule `git` will not touch `digital`.

```
guitte lab => GitLab
cubernetes => Kubernetes
```

Both files are plain text. Edit them by hand or from the panels in the app. The **My data** panel exports them, with your settings and your AI template if you have one, as a single `whiscribe-donnees-YYYY-MM-DD.zip` you can put on a USB stick or in a company backup. An import shows a preview of what would change and writes nothing before you confirm, and the previous state is saved next to it first.

---

## Reading back a transcript

A transcript opens **in the app**, no editor needed: click a line in the Transcripts tab, or the read button on a file that just finished.

<!-- screenshot 2: reading view, a paragraph with two or three amber highlighted words, the confidence tooltip visible on one of them -->

Whisper gives a probability for every word it writes. The reading view **highlights only the uncertain ones**, in discreet amber: below 0.50 the mark is light, below 0.30 it is clearer. Hovering any word shows its confidence, highlighted or not. In practice that flags around one word in ten in the worst case, and one in thirty-five with a decent model, so a handful of places to listen to again rather than a striped document.

These values live in a **companion `.json` file** written next to the text, a few tens of kilobytes per hour of audio. It is optional: an older transcript, or one produced with the option off, opens normally without highlighting.

Selecting a word or a short phrase offers to **correct it**. The app applies the replacement to the text on screen and to the saved file, updates the companion, and adds the rule to a dedicated section of `corrections.txt` so the same mistake is fixed automatically from then on.

**Copy for AI** puts an instruction template, the recording metadata and the full transcript on the clipboard. The template is your own file, `gabarit-ia.txt`, created on first use and editable from the settings, with `{texte}`, `{fichier}`, `{date}`, `{duree}`, `{locuteurs}` and `{modele}` replaced at copy time.

---

## Speed

The factor below is compute time divided by audio duration. Under 1 is faster than listening.

| Hardware | Highest quality | Fast | One hour of audio, in quality |
|---|---|---|---|
| Thin laptop, 12 to 14 threads, no dedicated card | about 1.2 x | about 0.3 x | about 1 h 15 |
| Desktop processor, 16 threads and up | about 0.7 x | about 0.2 x | about 40 min |
| Modest laptop, 4 to 8 threads | about 2 x | about 0.5 x | about 2 h |
| NVIDIA card (CUDA, float16) | about 0.1 x | about 0.05 x | about 6 min |

**These are estimates, not guarantees.** They are calibrated on public measurements and adjusted to the number of cores on your machine. The app shows the **time actually measured** after every transcription, and writes it in the header of the output file. Speaker separation adds roughly 0.2 x on CPU.

Acceleration in this version: **CPU everywhere** with `int8` quantisation, which is the default and perfectly usable, and **NVIDIA cards** in CUDA `float16`, automatically, when the driver and libraries answer. AMD Radeon cards, Intel integrated graphics and NPUs are detected and displayed but **not used**, because faster-whisper sits on [CTranslate2](https://opennmt.net/CTranslate2/hardware_support.html), which supports x86-64 and ARM64 CPUs and NVIDIA GPUs only. The app says so plainly rather than implying an acceleration that does not exist.

<details>
<summary>What could change that, later</summary>

**whisper.cpp with the Vulkan backend** is the solid path, and the only realistic one to accelerate a Radeon on Windows: a C/C++ port independent of PyTorch and CUDA, doing multi-vendor GPU inference without vendor specific code. Public measurements put it around 8 x real time on an RX 9070 XT, and 3 to 4 times better than CPU alone on a Radeon 680M integrated GPU. It would ship as a prebuilt Windows Vulkan binary driven as a subprocess, so that nobody has to install a C++ toolchain. The cost is a second model format, GGUF instead of CTranslate2, and an engine abstraction layer, which is why it is not here yet.

**OpenVINO for Intel integrated GPUs and NPUs** is interesting but not mature enough for a turnkey tool: the backend wants a precise OpenVINO version, and Whisper model conversion breaks with some `transformers` versions. As for the NPU itself, its appeal is battery life, a few watts against 15 to 25 for the integrated GPU, not raw speed. If Intel acceleration ever becomes a goal, Vulkan is the simpler and more robust route.

</details>

---

## Known limits

- **Windows 64-bit only.** The code is portable, but hardware detection and the launch scripts target Windows. The interface relies on Microsoft Edge WebView2 Runtime, shipped with Windows 11 and up to date Windows 10; the setup installs it if missing.
- **One spoken language per recording.** Mixing languages inside the same conversation is handled poorly: Whisper settles on one language and transcribes the rest through it. English terms scattered through a French discussion are a different matter, and that is exactly what the glossary is for.
- **Designed for French first,** which is where it was tested most. Quality is equal or better in English and in the languages Whisper covers well, and the app tells you what to expect under the language selector: excellent, good, or variable.
- **The first run needs an internet connection** to download the model, 1.6 to 3.1 GB depending on the preset. After that, never again.
- **No AMD or Intel GPU acceleration.** Those machines transcribe on the processor.
- **Speaker separation is not in the setup.** It needs the source install, about 2.5 GB of dependencies and a Hugging Face token. Without it, everything else works.
- **The installer is not signed.** SmartScreen may warn on first run. A code signing certificate costs several hundred euros a year, which makes no sense for a free personal tool.
- **Audio is decoded entirely in memory,** about 230 MB per hour of recording. Comfortable up to several hours, but this is not stream processing.
- **Speaker labels are useful, not authoritative.** Overlapping speech and distant voices are the hard cases. Setting the number of participants improves the split noticeably.

---

## Run from source

Only two reasons to go this way: **change the code**, or get **speaker separation**. For normal use, the setup above is enough.

1. Install [Python 3.9 or newer](https://www.python.org/downloads/), ticking **Add python.exe to PATH**.
2. Double-click **`installer.bat`**.
3. Answer the question about speaker separation, then let it run.
4. Double-click **`lancer.bat`**.

The installer is re-runnable, only installs what is missing, and creates an isolated environment in `.venv` without touching the system Python. It needs neither administrator rights, nor winget, nor Chocolatey: FFmpeg comes from a Python package that ships the binary.

| Option | Effect |
|---|---|
| `installer.bat` | Standard install, asks about speakers |
| `installer.bat --locuteurs` | Adds speaker separation (PyTorch and pyannote) |
| `installer.bat --sans-locuteurs` | Light install, no question |
| `installer.bat --verifier` | Prints the state of the machine and exits |

Run from source, the app keeps everything next to the script: `config.json`, `logs/`, `modeles/`, glossary and corrections. That is the only behavioural difference with the installed version.

<details>
<summary>Manual install, for those who prefer to keep control</summary>

```bat
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

REM Only with an NVIDIA card: avoids the "cublas64_12.dll not found" error
REM without touching the system PATH.
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*

REM Only for speaker separation. Without an NVIDIA card:
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
REM With an NVIDIA card:
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-locuteurs.txt

.venv\Scripts\pythonw transcriber.pyw
```

The base is about 250 MB. Speaker separation adds roughly 2.5 GB because it pulls in PyTorch, which is precisely why it is optional and why it stays out of the setup.

Check the state of the machine, the FFmpeg decoder, the work folders and hardware detection:

```bat
.venv\Scripts\python transcriber.pyw --verifier
```

</details>

<details>
<summary>Setting up speaker separation</summary>

The model that recognises voices, pyannote, is free but gated: its author asks you to accept the terms and identify yourself.

1. Create an account on [huggingface.co](https://huggingface.co).
2. Open [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) and accept the terms.
3. Create a **Read** access token in your account settings.
4. Paste it into the Speakers panel of the app.

The token is saved in `jeton_hf.txt`, with your data, and is never versioned. The `HF_TOKEN` environment variable is recognised too, and takes precedence. Without a token everything still works, simply without labels and with a clear message rather than an error.

Whisper and pyannote are **sequenced**, never loaded at the same time: the app transcribes, releases the Whisper model explicitly, forces a garbage collection, then loads diarisation. Peaks follow each other instead of adding up, so `large-v3` plus pyannote fit in 16 GB.

</details>

<details>
<summary>How the project is laid out</summary>

One engine, faster-whisper on CTranslate2. whisperX was removed: it forces PyTorch, its word level alignment is not needed here, its VAD is now built into faster-whisper, and driving a library rather than a subprocess gives per segment progress, exact control over memory release between stages, typed errors, and access to the model tokeniser to measure the prompt budget precisely.

```
transcriber.pyw       window, bridge to the interface, --verifier mode
installer.py          re-runnable installer, source version
app/
  chemins.py          locations, source or installed version
  materiel.py         processor, memory, GPU and NPU detection
  presets.py          presets, estimates, memory guardrails
  audio.py            FFmpeg, duration, 16 kHz mono decoding
  moteur.py           faster-whisper, loading and release
  diarisation.py      pyannote, token, speaker attribution
  vocabulaire.py      glossary, prompt, corrections
  sorties.py          txt, srt, vtt, headers
  nommage.py          output file name pattern
  surveillance.py     watched folder, polling and memory
  stockage.py         disk usage of models, data and program
  maj.py              optional check of published releases
  barre_taches.py     Windows taskbar progress
  compagnon.py        .json file of word by word confidence
  lecture.py          reading view, learned corrections, copy for AI
  gabarit.py          instruction template for an AI assistant
  reprise.py          progressive saving and resume after interruption
  traitement.py       sequential queue
  config.py           configuration
  journal.py          logging and translation of incidents
  langues.py          French and English catalogues, Python side
web/                  interface (HTML, CSS, JavaScript), langues.js
outils/               measurement and verification harnesses, outside the app
packaging/            PyInstaller recipe, Inno Setup script, icon
.github/workflows/    release pipeline
```

Where files live, depending on how the app was started:

| | Installed version | Source version |
|---|---|---|
| Program | `%LOCALAPPDATA%\Programs\WhiScribe` | the cloned repository |
| Settings, logs, glossary | `%LOCALAPPDATA%\WhiScribe` | next to the script |
| Models | chosen at install time, changeable in the settings | `modeles/`, changeable in the settings |

</details>

<details>
<summary>Building the installer</summary>

Publication is automated: pushing a `vX.Y.Z` tag triggers `.github/workflows/release.yml`, which builds, verifies, produces the setup and creates the Release with the file attached. Release notes are the matching section of [CHANGELOG.md](CHANGELOG.md). The same workflow runs by hand from the Actions tab, without a tag: it builds and verifies everything but publishes nothing.

```bat
pip install -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\whiscribe.spec
dist\WhiScribe\whiscribe-verifier.exe
iscc /DVersionApp=2.2.0 packaging\setup.iss
```

The version number has a single source, `VERSION` in `app/__init__.py`, and the workflow refuses to publish if the tag does not match. PyInstaller 6.22 is the minimum: earlier versions cannot freeze numpy 2.5.

A release that cannot update in place is announced by writing `[reinstallation-requise]` anywhere in its CHANGELOG section. The update banner then tells the user to uninstall first, and that data and models are kept, which is true since they live outside the program folder.

</details>

---

## Diagnostics

Every failure is explained in the interface, in plain language: unreadable file, model to download, not enough memory, missing or invalid token, full disk, missing CUDA libraries. No traceback ever reaches the screen.

The technical detail goes to a timestamped file in `logs/`, whose name is quoted in the error message. The **Open the detailed log** button, in the bottom bar, opens it directly. The last 30 logs are kept. That file is what to attach to a bug report, and the logs are written in French: they are aimed at the maintainer, not at the user.

---

## Contributing

Issues and small pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see [LICENSE](LICENSE). Version history in [CHANGELOG.md](CHANGELOG.md).

Built on free software: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and [CTranslate2](https://github.com/OpenNMT/CTranslate2), the [Whisper](https://github.com/openai/whisper) models from OpenAI, [pyannote.audio](https://github.com/pyannote/pyannote-audio), [pywebview](https://pywebview.flowrl.com/) and [FFmpeg](https://ffmpeg.org/).
