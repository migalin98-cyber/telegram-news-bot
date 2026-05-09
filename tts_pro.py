import argparse
import asyncio
import pathlib
import re
from typing import List

import edge_tts


def split_text(text: str, max_chars: int = 2500) -> List[str]:
    """Разбивает длинный текст на фрагменты по предложениям."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(sentence) <= max_chars:
                current = sentence
            else:
                # fallback: режем очень длинное предложение
                for i in range(0, len(sentence), max_chars):
                    chunks.append(sentence[i : i + max_chars])
                current = ""

    if current:
        chunks.append(current)
    return chunks


async def synthesize_to_file(
    text: str,
    output_path: pathlib.Path,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
) -> None:
    chunks = split_text(text)

    tmp_files = []
    for i, chunk in enumerate(chunks, start=1):
        tmp_file = output_path.with_suffix(f".part{i}.mp3")
        communicate = edge_tts.Communicate(
            text=chunk,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        await communicate.save(str(tmp_file))
        tmp_files.append(tmp_file)

    # Склеиваем mp3-фрагменты побайтно (валидно для большинства плееров)
    with output_path.open("wb") as out:
        for file in tmp_files:
            out.write(file.read_bytes())

    for file in tmp_files:
        file.unlink(missing_ok=True)


def read_input_text(raw_text: str | None, text_file: str | None) -> str:
    if raw_text:
        return raw_text.strip()
    if text_file:
        return pathlib.Path(text_file).read_text(encoding="utf-8").strip()
    raise ValueError("Нужно передать --text или --file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Профессиональная озвучка текста в MP3 (Neural voices)."
    )
    parser.add_argument("--text", help="Текст для озвучки")
    parser.add_argument("--file", help="Путь к TXT-файлу с текстом")
    parser.add_argument("--output", default="voiceover.mp3", help="Имя выходного MP3")
    parser.add_argument(
        "--voice",
        default="ru-RU-SvetlanaNeural",
        help="Голос Edge TTS, пример: ru-RU-DmitryNeural",
    )
    parser.add_argument("--rate", default="+0%", help="Скорость: например +10% / -15%")
    parser.add_argument("--pitch", default="+0Hz", help="Тон: например +20Hz / -20Hz")
    parser.add_argument("--volume", default="+0%", help="Громкость: например +5% / -10%")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    text = read_input_text(args.text, args.file)
    if not text:
        raise SystemExit("Пустой текст для озвучки")

    out_path = pathlib.Path(args.output).resolve()
    asyncio.run(
        synthesize_to_file(
            text=text,
            output_path=out_path,
            voice=args.voice,
            rate=args.rate,
            pitch=args.pitch,
            volume=args.volume,
        )
    )
    print(f"Готово: {out_path}")


if __name__ == "__main__":
    main()
