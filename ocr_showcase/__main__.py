"""OCR document review and safe local queue, without portal access."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


FIO = re.compile(r"\b([А-ЯЁ][а-яё-]+)\s+([А-ЯЁ][а-яё-]+)\s+([А-ЯЁ][а-яё-]+)\b")
ROOM = re.compile(r"(?<![\w])\d{1,4}(?:[-/]\d{1,4})?[А-ЯЁA-Z]?(?![\w])")
ROOM_LABEL = re.compile(r"(?:номер\s+помещения|№\s*помещения|помещение\s*№)", re.I)
STOP_WORDS = {"Номер", "Площадь", "Помещение", "Собственник", "Решение", "Протокол"}


@dataclass(frozen=True)
class Candidate:
    fio: str | None
    room: str | None
    confidence: float


def extract_fields(text: str, confidence: float = 0.0) -> Candidate:
    """Conservative public demonstration; all fields require operator review."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    fio = next((m.group(0) for line in lines for m in FIO.finditer(line)
                if not set(m.groups()) & STOP_WORDS), None)
    room = None
    for index, line in enumerate(lines):
        label = ROOM_LABEL.search(line)
        if not label:
            continue
        tail = line[label.end():]
        for cell in (tail, lines[index + 1] if index + 1 < len(lines) else ""):
            match = ROOM.search(cell)
            if match:
                room = match.group(0)
                break
        if room:
            break
    return Candidate(fio, room, confidence)


def ocr_first_page(pdf: Path) -> tuple[str, float]:
    """Run two image variants and keep OCR output with higher word confidence."""
    try:
        from pdf2image import convert_from_path
        from PIL import ImageOps
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt and external Tesseract/Poppler") from exc

    pages = convert_from_path(str(pdf), dpi=300, first_page=1, last_page=1)
    if not pages:
        raise ValueError("PDF has no readable pages")
    gray = ImageOps.grayscale(pages[0])
    variants = (gray, ImageOps.autocontrast(gray))
    results = []
    for image in variants:
        data = pytesseract.image_to_data(image, lang="rus+eng", config="--psm 6", output_type=Output.DICT)
        words = [word.strip() for word in data["text"]]
        scores = [float(conf) for word, conf in zip(words, data["conf"]) if word and float(conf) >= 0]
        ordered = {}
        for i, word in enumerate(words):
            if word:
                key = (data["page_num"][i], data["block_num"][i], data["par_num"][i], data["line_num"][i])
                ordered.setdefault(key, []).append(word)
        results.append(("\n".join(" ".join(row) for row in ordered.values()), sum(scores) / len(scores) if scores else 0.0))
    return max(results, key=lambda result: result[1])


def safe_filename(fio: str, room: str) -> str:
    fio = " ".join(fio.split())
    room = room.strip().upper()
    if not FIO.fullmatch(fio) or not ROOM.fullmatch(room):
        raise ValueError("Expected three Cyrillic name parts and a room number")
    return f"{fio} ({room}).pdf"


def copy_unique(source: Path, folder: Path, filename: str) -> Path:
    """Reserve an unused name atomically; keep the original PDF untouched."""
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(filename)
    for index in range(10000):
        target = folder / (filename if index == 0 else f"{name.stem} ({index}){name.suffix}")
        try:
            with target.open("xb") as output, source.open("rb") as original:
                shutil.copyfileobj(original, output)
            return target
        except FileExistsError:
            continue
        except Exception:
            target.unlink(missing_ok=True)
            raise
    raise RuntimeError("Too many duplicate names")


def process(folder: Path) -> None:
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")
    for pdf in sorted(folder.glob("*.pdf")):
        print(f"\n{pdf.name}")
        try:
            text, confidence = ocr_first_page(pdf)
            candidate = extract_fields(text, confidence)
            print(f"OCR: {asdict(candidate)}")
            print("Check the PDF. Enter the verified full name (three words), or press Enter to skip:")
            fio = input("> ").strip() or candidate.fio
            print("Enter the verified room number, or press Enter to use the suggestion:")
            room = input("> ").strip() or candidate.room
            if not fio or not room:
                raise ValueError("Missing verified fields")
            filename = safe_filename(fio, room)
            approval = input(f"Copy as {filename}? Type YES to confirm: ").strip()
            if approval != "YES":
                raise ValueError("Not confirmed")
            output = copy_unique(pdf, Path("ready"), filename)
            print(f"Saved: {output}")
        except (ValueError, RuntimeError, OSError) as exc:
            output = copy_unique(pdf, Path("problems"), pdf.name)
            print(f"Review needed ({exc}); copied to {output}")


def mock_robot(folder: Path) -> None:
    """Show proposed actions without opening a browser or uploading files."""
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")
    actions = [{"action": "would_upload", "filename": pdf.name} for pdf in sorted(folder.glob("*.pdf"))]
    print(json.dumps(actions, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local OCR review and mock robot")
    parser.add_argument("command", choices=("process", "mock-robot"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.command == "process":
        process(args.folder)
    else:
        mock_robot(args.folder)


if __name__ == "__main__":
    main()
