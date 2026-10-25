# Finding and cutting video clips without watching the video

Sending a long video to a multimodal model so it can find "the part where…"
costs roughly a million tokens per hour of footage. AgentForge works from the
video's **timestamped transcript** instead. An hour of speech is about
9–10k words, so even reading the whole thing costs about 12k tokens. A normal
find-and-cut round trip costs a few thousand.

## The three tools (Video pack)

Turn on the **Video pack** in the tool catalog, then attach these tools to an
agent:

| Tool | What it does | Network / cost |
|---|---|---|
| `video_transcript` | Gets the title, duration, chapters and timestamped transcript for a URL or a workspace media file. Can also return a compact paged outline (`[m:ss] text`). | Captions only, no media download. Cached across runs. |
| `clip_finder` | Ranks transcript windows against a query plus keywords using local BM25, with boosts for exact phrases and matching chapter titles. Returns ranked clips with start/end times, short excerpts and YouTube `&t=` links. | Searching uses no model tokens; the agent reads only the shortlist. |
| `clip_extractor` | Cuts the chosen ranges into MP4 files. For URLs it downloads only those sections (yt-dlp `download_ranges`). For local files it trims with ffmpeg. Can also write an `.srt` file for each clip. | Downloads only the requested seconds. |

`video_source` (search) is still available for finding candidate videos.

### Where the transcript comes from

1. Captions published with the video (manual captions).
2. Auto captions in the video's original language (YouTube `*-orig`).
3. If neither exists: download the audio only and transcribe it locally with
   [faster-whisper](https://github.com/SYSTRAN/faster-whisper). This needs the
   optional extra:

   ```bash
   cd python-runtime && uv sync --extra transcribe
   ```

   The model weights (default `base`) download once on first use. You can
   change the model with the `whisper_model` tool config (`tiny`, `small`,
   `medium`, `large-v3`, …).

Transcripts are cached under `<data_dir>/cache/transcripts/`. A URL is cached
with its tracking and timestamp parameters removed. A local file is cached by
its content hash.

### Tool config (optional)

| Key | Tools | Meaning |
|---|---|---|
| `cookies_from_browser` | all three | `chrome`, `firefox`, `edge`, … Reuses your browser login when a host asks you to sign in ("confirm you're not a bot"). |
| `max_height` | `clip_extractor` | Highest video resolution to download (default `720`). |
| `whisper_model` | `video_transcript`, `clip_finder` | faster-whisper model size for videos without captions. |

### Limits

Each `clip_extractor` call can cut at most 20 clips. Each clip can be up to
10 minutes, and all clips together up to 30 minutes. Speech-to-text works on
videos up to 4 hours long. Playlists and live streams are not supported. URLs
pointing at private or loopback addresses are rejected before yt-dlp runs.

## Suggested agent prompt

> You cut clips from videos. For each request: call `video_transcript` on the
> URL. Then call `clip_finder` with the user's description as `query`, and
> 5–15 `keywords` the speaker would actually say: synonyms, names, numbers,
> jargon. Read the excerpts and keep only the clips that really match. If
> nothing matches, retry with different keywords. As a last resort, read the
> outline (`include_outline=true`, paging with `offset`). Then call
> `clip_extractor` with the chosen ranges and labels. Never guess timestamps
> you have not seen in a tool result.

## What this approach cannot do

Moments that are purely visual, such as "the shot where the car flips" with
no narration, do not show up in a transcript. For those, cut a broad range
around the nearest spoken cue and check it with `analyze_image` on a few
frames. This still costs far less than sending the full video.
