# Social Video Reader — TikTok public test

**Date**: 2026-09-13 12:58:20Z  
**Status**: COMPLETE  
**Researcher Agent**: ruflow-researcher

## Request

- URL: https://www.tiktok.com/@santeluca/video/7681401583359331616?q=very%20chinese%20time%20in%20my%20life&t=1789298134701
- Operation: read_social_url
- transcribe=true
- force_transcribe=true
- analyze_visuals=true
- translate_to=th
- check_claims=true
- redact_pii=true
- browser_fallback=true
- analysis_depth=detailed
- max_frames=16
- use_cache=false
- Access: public-only; no cookies, login, CAPTCHA, or access-control bypass.

## Exact returned status/evidence

~~~yaml
source:
  platform: tiktok
  content_type: video
  access_mode: public_only
metadata:
  title: Bakugan collection
  description: Bakugan collection
  author: santeluca
  published_at: 2026-09-03
  duration_sec: 27
caption: Bakugan collection
browser_fallback:
  requested: true
  attempted: false
  status: not_needed
evidence:
  - yt-dlp public extractor
  - public page metadata
  - local_whisper
  - downloaded public media (yt_dlp)
fetched_at: 2026-09-13T12:58:20.649Z
analysis_depth: detailed
~~~

## Transcript

~~~yaml
status: available
source: local_whisper
language: en
detected_language: en
preprocessing: ffmpeg_wav_16khz_mono
speaker_segmentation:
  status: unavailable
coverage:
  duration_sec: 27
  timestamped_segments: 12
  first_speech_sec: 0.36
  last_speech_end_sec: 26.66
  recognized_speech_only: true
~~~

Timestamped segments:

1. 0.36–2.24 — She says she only dates rich guys.
2. 2.78–5.66 — So, I showed her my Bakugan collection during our first date,
3. 5.78–6.86 — and she was so impressed.
4. 7.10–8.94 — She walked away and never came back.
5. 9.78–11.52 — Wish I had someone to play together with.
6. 12.28–15.78 — Oh, well, this one right here can fetch over 6K, man.
7. 16.06–16.66 — Markets up.
8. 17.36–18.96 — Handcrafted by my guy from Chennai.
9. 19.28–20.74 — It doesn't get any better than this, man.
10. 21.60–23.98 — You met me at a very Chinese time in my life.
11. 24.26–25.94 — Get yours at childrenofkhan.com.
12. 26.08–26.66 — Link in bio.

Full returned transcript:

~~~text
She says she only dates rich guys. So, I showed her my Bakugan collection during our first date, and she was so impressed. She walked away and never came back. Wish I had someone to play together with. Oh, well, this one right here can fetch over 6K, man. Markets up. Handcrafted by my guy from Chennai. It doesn't get any better than this, man. You met me at a very Chinese time in my life. Get yours at childrenofkhan.com. Link in bio.
~~~

## Media

~~~yaml
requested: true
download_attempted: true
downloaded: true
source: yt_dlp
media_kind: video
content_type: null
bytes: 1076291
retained: false
deleted_after_analysis: true
~~~

## Visual/OCR

~~~yaml
status: partial
provider: tesseract_ocr
ocr_available: true
ffmpeg: true
frame_sampling:
  mode: evenly_spaced
  requested_frames: 16
  extracted_frames: 16
  first_sample_sec: 0
  last_sample_sec: 24.901
  coverage_percent: 92
  complete_frame_scan: false
scenes: []
people: []
products: []
visual_hook: null
~~~

OCR was returned for all 16 sampled frames, but it is noisy and is retained
verbatim here as evidence, not interpreted text:

| Frame | Start (sec) | OCR text |
|---:|---:|---|
| 1 | 0 | ระฯ 8 \| \| \| \| |
| 2 | 1.66 | ะ า ผิ เฒ ก 6 รทธ 5ลบูร รทธ 0๐ทเท (ส่ลไอร.ท่๐ท |
| 3 | 3.32 | ” อ เวฏศเลสมพล์ 2 ว ๕%7 1 (ศศม - ไ\|เล่อพอด์ ทธะ ทาท ธิลเนฮูลท 1ัวัช 00แอ0๐ม9วท |
| 4 | 4.98 | ” 6 น ธะ 0 ซ๊ งื่นท่ทย 0น1 กักร[ สล1อ |
| 5 | 6.64 | ” วจ ๒ จ . ธะ แจ == ๒ 2 -สทส รทธ พล5 ร0 ไททฏธรรอผ่ |
| 6 | 8.3 | 4 2 0 5กธ พญ่แอส สพลท ลทส ทธงธ[ รว ๐ฆาธ 0ล0 % . |
| 7 | 9.961 | «” จ ง พไรท \| ทลส ร0ทา6ธ0๐ทธ 16 ฏิเล 10606ฝป่า6[ หทเป่า น |
| 8 | 11.621 | = ซุ 0 1 ก ! “ พเไรท \| ทลส รอทาธ0ทธ 10 มิเลส' 1006ฝป่า6อ[ หเป่า |
| 9 | 13.281 | ง “ ซี ่ เเจยนิ. ต ' 6 % ปะ 0นรทุฒ\| 1ท6๓, แม) ” จ้๊ (ไทลชูท กพ |
| 10 | 14.941 | ล,, 0 : ศ์ 6 น ณ ปฝ้า1ร 0๐ทธ ทยท1 ทอแอ. ๐ฒา 1อฮใ0 0ฯหธธ7 6 เทลท 2ล๒ เดท - ๕ |
| 11 | 16.601 | ล,. = ว 7 : ' ' ละ |
| 12 | 18.261 | อ \| ท ป ” \| ทลเทส่๐เลไอส อท ทาษ ตูนทไฮอทา 6๐ทรทยทฆ์ |
| 13 | 19.921 | ส์4 1 \| \| . จ ง !! ต่๐ธรท'1 06ไ1 ลทท 6ไอฮเ ป่าฆา ป่า\|ร เทลท* |
| 14 | 21.581 | “ฯ 2 ก= ฯ ' เร ซ์ |
| 15 | 23.241 | 0 วร ศ '@ ภ วัตว > 4 ซี: . 2 - ป0ป0 ทา6! ทธ ล1! ล งธญ/ 0ทไทธรธ ว จู ฟีทาธ เท ทาง !หือ |
| 16 | 24.901 | ฟู่ ๕๕๕๕๕ -.. 6 0 6 .0ทแล่แอท๐ศีตาฉา6 |

Hosted vision was skipped because returned image content may contain personal
information. The sampled frames do not constitute a complete frame scan.

## Translation

~~~yaml
status: unavailable
source_language: en
target_language: th
text: ""
segments: []
reason: Translation requires OPENAI_API_KEY or a compatible translation provider.
~~~

## Claims

~~~yaml
status: available
provider: source_consistency_heuristic
scope: source_consistency_only
~~~

The returned claims were all requires_external_verification with
confidence: low; they were not externally verified:

| ID | Claim | Time | Evidence ref |
|---|---|---:|---|
| claim.1 | and she was so impressed. | 5.78–6.86 | transcript.3 |
| claim.2 | She walked away and never came back. | 7.10–8.94 | transcript.4 |
| claim.3 | Wish I had someone to play together with. | 9.78–11.52 | transcript.5 |
| claim.4 | Oh, well, this one right here can fetch over 6K, man. | 12.28–15.78 | transcript.6 |
| claim.5 | It doesn't get any better than this, man. | 19.28–20.74 | transcript.9 |

Returned note: claim checking extracts claims from readable content and is
not confirmation of truth on the web.

## Privacy/cache

~~~yaml
privacy:
  redaction_applied: true
  credentials_used: false
  media_deleted_after_analysis: true
cache:
  status: miss
  saved: false
~~~

## Limitations / pending

- Speaker diarization is not configured; no speaker labels were produced.
- Thai translation was requested but unavailable because no translation
  provider/API key was configured.
- Visual analysis is partial: Tesseract OCR only; hosted vision was skipped;
  scenes, people, products, and visual hook are empty/null.
- OCR output is noisy and should not be treated as reliable transcription.
- The frame set is evenly sampled (16 frames, 92% temporal coverage), not a
  complete scan; events between samples may be missed.
- Whisper reports recognized speech only; missing segments do not prove silence
  or no audio.
- Claims are source-consistency findings only and require external
  verification.

---

## Fresh plugin run - 2026-09-13T13:32:30Z

**Status**: COMPLETE, with transcript/translation unavailable in this run.

Request delta from earlier run:

~~~yaml
visual_scan: scene_change
scene_threshold: 0.01
max_scan_frames: 30
video_quality: highest
save_media: false
browser_fallback: true
public_only: true
~~~

Structured result highlights:

~~~yaml
source:
  platform: tiktok
  content_type: video
  access_mode: public_only
metadata:
  title: Bakugan collection
  description: Bakugan collection
  author: santeluca
  published_at: 2026-09-03
  duration_sec: 27
caption: Bakugan collection
browser_fallback:
  requested: true
  attempted: false
  status: not_needed
evidence:
  - yt-dlp public extractor
  - public page metadata
  - downloaded public media (browser_rendered_media)
media:
  downloaded: true
  source: browser_rendered_media
  content_type: video/mp4
  bytes: 197971
  retained: false
  deleted_after_analysis: true
  video_quality: highest
transcript:
  status: not_found
  source: null
  language: null
  segments: []
  note: Local Whisper returned empty text.
translation:
  status: unavailable
  target_language: th
  reason: Translation requires OPENAI_API_KEY or a compatible translation provider.
fact_check:
  status: no_claims_found
  provider: source_consistency_heuristic
  scope: source_consistency_only
cache:
  status: disabled
  saved: false
privacy:
  redaction_applied: true
  credentials_used: false
  media_deleted_after_analysis: true
~~~

Visual scan:

~~~yaml
status: partial
provider: tesseract_ocr
media_source: browser_rendered_media
ocr_available: true
ffmpeg: true
frame_sampling:
  mode: scene_change
  requested_frames: 30
  extracted_frames: 30
  first_sample_sec: 0.033
  last_sample_sec: 1.133
  source_frame_rate: 30
  coverage_percent: 55
  complete_frame_scan: false
  scene_threshold: 0.01
source_video:
  width: 720
  height: 816
  frame_rate: 30
  quality_mode: highest
scenes: []
people: []
products: []
visual_hook: null
detected_text:
  - ข้
  - ช้
  - รวั๋
  - ฮั่
  - ย
  - ขั
  - วั๋
  - ข่
  - ข
  - รั๋
privacy_note: Hosted vision was skipped because returned image content may contain personal information.
~~~

Limitations:

- Plugin/schema version was not visible in the structured result.
- Transcript and timestamped speech were absent in this run; no speech is inferred
  from metadata or OCR.
- OCR was noisy Thai-like fragments only; not interpreted as scene or speech.
- Visual analysis is partial: OCR/frame metadata only, hosted vision skipped.
- Scene-change scan selected frames only through 1.133s; unchanged intervals may
  be absent.
- Fact-check found no readable claims in this run; it did not perform web truth
  verification.
