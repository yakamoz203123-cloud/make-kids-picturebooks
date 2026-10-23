"""Validate final reading and booklet PDFs before publication or acceptance."""
from pathlib import Path
import math
import re

import pymupdf as fitz

from impose_booklet import MM, booklet_pairs


DEFAULT_MINIMUM_PRINT_TEXT_SIZE_PT = 18.0
DIMENSION_TOLERANCE_PT = 0.05


def normal(text):
    return re.sub(r'\s+', '', text)


def minimum_print_text_size(layout):
    value = layout.get('minimum_print_text_size_pt', DEFAULT_MINIMUM_PRINT_TEXT_SIZE_PT)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('minimum_print_text_size_pt must be a finite number')
    return max(DEFAULT_MINIMUM_PRINT_TEXT_SIZE_PT, float(value))


def allowed_empty_pages(layout):
    """Return page numbers explicitly marked blank or wordless in a layout."""
    pages = layout.get('pages', [])
    return {
        number for number, page in enumerate(pages, 1)
        if isinstance(page, dict) and (
            page.get('kind') == 'blank'
            or (page.get('kind') == 'story' and page.get('wordless') is True)
        )
    }


def _open_pdf(path, label, errors):
    path = Path(path)
    if not path.is_file():
        errors.append(f'{label} PDF is missing')
        return None
    if path.stat().st_size == 0:
        errors.append(f'{label} PDF is empty')
        return None
    try:
        return fitz.open(path)
    except (fitz.FileDataError, OSError, RuntimeError, ValueError):
        errors.append(f'{label} PDF is unreadable')
        return None


def _text_sizes(page):
    return [
        span['size']
        for block in page.get_text('dict')['blocks']
        if block.get('type') == 0
        for line in block['lines']
        for span in line['spans']
        if span['text'].strip()
    ]


def _normalize_empty_pages(value, expected_pages):
    if value is None:
        return set()
    try:
        pages = set(value)
    except TypeError as exc:
        raise ValueError('allow_empty_pages must be an iterable of page numbers') from exc
    if any(type(number) is not int or number < 1 or number > expected_pages for number in pages):
        raise ValueError('allow_empty_pages contains an invalid page number')
    return pages


def validation_errors(reading_path, print_path, expected_page_texts, page_mm=(148, 210), minimum_print_text_size_pt=DEFAULT_MINIMUM_PRINT_TEXT_SIZE_PT, allow_empty_pages=None):
    """Return deterministic defects found in final reading and booklet PDFs."""
    errors = []
    reading = _open_pdf(reading_path, 'reading', errors)
    printing = _open_pdf(print_path, 'print', errors)
    if reading is None or printing is None:
        if reading is not None:
            reading.close()
        if printing is not None:
            printing.close()
        return errors
    try:
        expected_page_texts = list(expected_page_texts)
        expected_pages = len(expected_page_texts)
        allow_empty_pages = _normalize_empty_pages(allow_empty_pages, expected_pages)
        try:
            fixed_a5 = (
                len(page_mm) == 2
                and all(type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value) for value in page_mm)
                and float(page_mm[0]) == 148.0
                and float(page_mm[1]) == 210.0
            )
        except (TypeError, ValueError):
            fixed_a5 = False
        if not fixed_a5:
            errors.append('reading page dimensions must be fixed A5 [148, 210]')
        if expected_pages and all(not normal(text) for text in expected_page_texts):
            errors.append('book must contain at least one content-bearing page with non-empty text')
        for index, text in enumerate(expected_page_texts, 1):
            if not normal(text):
                if index not in allow_empty_pages:
                    errors.append(f'expected page text must be non-empty for page {index}')
        pairs = booklet_pairs(expected_pages)
        if len(reading) != expected_pages:
            errors.append(f'reading PDF page count: expected {expected_pages}, got {len(reading)}')
        if len(printing) != len(pairs):
            errors.append(f'print PDF page count: expected {len(pairs)}, got {len(printing)}')
        expected_width, expected_height = 148 * MM, 210 * MM
        for index, page in enumerate(reading, 1):
            if abs(page.rect.width - expected_width) > DIMENSION_TOLERANCE_PT or abs(page.rect.height - expected_height) > DIMENSION_TOLERANCE_PT:
                errors.append(f'reading page {index}: expected A5 dimensions')
            if index <= expected_pages:
                extracted = normal(page.get_text())
                expected = normal(expected_page_texts[index - 1])
                if index in allow_empty_pages:
                    if extracted:
                        errors.append(f'reading page {index}: authorized empty page contains extractable text')
                elif not extracted:
                    errors.append(f'reading page {index}: no extractable text')
                elif expected not in extracted:
                    errors.append(f'reading page {index}: expected text is not extractable')
        for index, page in enumerate(printing, 1):
            if abs(page.rect.width - 297 * MM) > DIMENSION_TOLERANCE_PT or abs(page.rect.height - 210 * MM) > DIMENSION_TOLERANCE_PT:
                errors.append(f'print page {index}: expected landscape A4 dimensions')
            if index <= len(pairs):
                for side, page_number in enumerate(pairs[index - 1]):
                    clip = fitz.Rect(side * page.rect.width / 2, 0, (side + 1) * page.rect.width / 2, page.rect.height)
                    extracted = normal(page.get_text(clip=clip))
                    expected = normal(expected_page_texts[page_number - 1])
                    if page_number in allow_empty_pages:
                        if extracted:
                            errors.append(f'print page {index} half {side + 1}: authorized empty page {page_number} contains extractable text')
                    elif not extracted:
                        errors.append(f'print page {index} half {side + 1}: no extractable text')
                    elif expected not in extracted:
                        errors.append(f'print page {index}: expected text for page {page_number} is not extractable')
            if isinstance(minimum_print_text_size_pt, bool) or not isinstance(minimum_print_text_size_pt, (int, float)) or not math.isfinite(minimum_print_text_size_pt):
                raise ValueError('minimum_print_text_size_pt must be a finite number')
            threshold = max(DEFAULT_MINIMUM_PRINT_TEXT_SIZE_PT, float(minimum_print_text_size_pt))
            for size in _text_sizes(page):
                if size < threshold:
                    errors.append(f'print page {index}: text size {size:.1f} pt is below {threshold:.1f} pt')
    finally:
        reading.close()
        printing.close()
    return errors


def validate_exports(reading_path, print_path, expected_page_texts, page_mm=(148, 210), minimum_print_text_size_pt=DEFAULT_MINIMUM_PRINT_TEXT_SIZE_PT, allow_empty_pages=None):
    """Validate exports or raise ``ValueError`` without modifying either PDF."""
    errors = validation_errors(reading_path, print_path, expected_page_texts, page_mm, minimum_print_text_size_pt, allow_empty_pages)
    if errors:
        raise ValueError('; '.join(errors))
    return {'reading_pages': len(expected_page_texts), 'print_sides': len(booklet_pairs(len(expected_page_texts)))}
