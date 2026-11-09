# YouTube to MP3 Downloader

Downloads videos from YouTube as MP3 files using yt-dlp and ffmpeg.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python yt2mp3.py [YouTube_URL] [--output <output_dir>]
```

## Example

```bash
python yt2mp3.py https://youtube.com/watch?v=dQw4w9WgXcQ
```

## Features

- Downloads audio from YouTube
- Converts to MP3 format
- Extracts metadata (title, duration, thumbnail)
- Outputs to current directory by default
