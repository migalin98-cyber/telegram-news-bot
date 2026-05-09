"""Minimal realtime translation subtitle overlay.

Usage:
  echo "hello world" | python stream_subtitle_overlay.py --source stdin --target ru
  python stream_subtitle_overlay.py --source microphone --speech-language en-US --target ru

For stream/online content audio, route system audio to a virtual microphone first.
Press Esc to close the overlay.
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
import tkinter as tk
from typing import Optional


def translate_text(text: str, source: str, target: str) -> str:
    if not text.strip() or target in {"same", "same-as-source", source}:
        return text
    try:
        from deep_translator import GoogleTranslator
    except ImportError as exc:
        raise RuntimeError("Install deep-translator or use --target same-as-source") from exc
    return GoogleTranslator(source=source, target=target).translate(text) or text


def listen_stdin(out: queue.Queue[str], stop: threading.Event, source: str, target: str) -> None:
    for line in sys.stdin:
        if stop.is_set():
            break
        text = line.strip()
        if text:
            put_latest(out, safe_translate(text, source, target))


def listen_microphone(out: queue.Queue[str], stop: threading.Event, language: str, source: str, target: str, phrase_limit: int) -> None:
    try:
        import speech_recognition as sr
    except ImportError as exc:
        raise RuntimeError("Install SpeechRecognition and PyAudio, or use --source stdin") from exc

    recognizer = sr.Recognizer()
    with sr.Microphone() as mic:
        recognizer.adjust_for_ambient_noise(mic, duration=0.5)
        while not stop.is_set():
            try:
                audio = recognizer.listen(mic, timeout=1, phrase_time_limit=phrase_limit)
                text = recognizer.recognize_google(audio, language=language).strip()
            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                put_latest(out, f"[speech recognition error: {exc}]")
                time.sleep(2)
                continue
            if text:
                put_latest(out, safe_translate(text, source, target))


def safe_translate(text: str, source: str, target: str) -> str:
    try:
        return translate_text(text, source, target)
    except Exception as exc:
        return f"{text}\n[translation error: {exc}]"


def put_latest(out: queue.Queue[str], text: str) -> None:
    while out.full():
        try:
            out.get_nowait()
        except queue.Empty:
            break
    out.put(text)


class Overlay:
    def __init__(self, font_size: int, opacity: float, bottom_offset: int, max_chars: int) -> None:
        self.max_chars = max_chars
        self.root = tk.Tk()
        self.root.title("Live translation subtitles")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", min(1.0, max(0.2, opacity)))
        self.root.configure(background="#000000")
        self.root.overrideredirect(True)
        width = min(1100, max(640, self.root.winfo_screenwidth() - 160))
        height = 150
        left = max(0, (self.root.winfo_screenwidth() - width) // 2)
        top = max(0, self.root.winfo_screenheight() - height - bottom_offset)
        self.root.geometry(f"{width}x{height}+{left}+{top}")
        self.label = tk.Label(self.root, text="Waiting for subtitles...", font=("Arial", font_size, "bold"), fg="#ffffff", bg="#000000", wraplength=width - 40, justify="center")
        self.label.pack(expand=True, fill="both", padx=20, pady=12)
        self.root.bind("<Escape>", lambda _event: self.close())

    def set_text(self, text: str) -> None:
        if len(text) > self.max_chars:
            text = "..." + text[-self.max_chars:]
        self.label.configure(text=text)

    def close(self) -> None:
        self.root.quit()
        self.root.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render translated subtitles over any stream/window.")
    parser.add_argument("--source", choices=("stdin", "microphone"), default="stdin")
    parser.add_argument("--src", default="auto")
    parser.add_argument("--target", default="ru")
    parser.add_argument("--speech-language", default="en-US")
    parser.add_argument("--phrase-time-limit", type=int, default=5)
    parser.add_argument("--font-size", type=int, default=32)
    parser.add_argument("--max-chars", type=int, default=160)
    parser.add_argument("--bottom-offset", type=int, default=90)
    parser.add_argument("--opacity", type=float, default=0.72)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stop = threading.Event()
    subtitles: queue.Queue[str] = queue.Queue(maxsize=4)
    listener_args = (subtitles, stop, args.speech_language, args.src, args.target, args.phrase_time_limit)
    target = listen_stdin if args.source == "stdin" else listen_microphone
    if args.source == "stdin":
        thread = threading.Thread(target=target, args=(subtitles, stop, args.src, args.target), daemon=True)
    else:
        thread = threading.Thread(target=target, args=listener_args, daemon=True)
    thread.start()

    overlay = Overlay(args.font_size, args.opacity, args.bottom_offset, args.max_chars)

    def tick() -> None:
        try:
            overlay.set_text(subtitles.get_nowait())
        except queue.Empty:
            pass
        overlay.root.after(80, tick)

    try:
        tick()
        overlay.root.mainloop()
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
