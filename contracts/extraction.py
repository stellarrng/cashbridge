"""Bounded PDF/text/image extraction. OCR uses local Tesseract only when installed.

In-memory processing, no cloud data transfer. Scans are never claimed to be verified.
"""
from __future__ import annotations

import io
from typing import Dict

MAX_UPLOAD_BYTES = 5_000_000


def extract_upload(filename: str, data: bytes) -> Dict[str, object]:
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('File must be 1 byte to 5 MB')
    name = (filename or '').lower()
    suffix = name.rsplit('.', 1)[-1] if '.' in name else ''
    if suffix not in {'txt','pdf','png','jpg','jpeg'}:
        raise ValueError('Only TXT, PDF, PNG, JPG and JPEG files are accepted')
    method = 'text'; pages = 1
    if suffix == 'txt':
        value = data.decode('utf-8-sig', errors='replace')
    elif suffix == 'pdf':
        import fitz
        try:
            doc = fitz.open(stream=data, filetype='pdf')
            if doc.needs_pass: raise ValueError('Password-protected PDFs are not supported')
            if len(doc) > 10: raise ValueError('Maximum 10 PDF pages')
            pages = len(doc)
            chunks = []
            for page in doc:
                text = page.get_text(sort=True)
                if len(text.strip()) < 24:
                    import pytesseract
                    from PIL import Image
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    if pix.width * pix.height > 14_000_000: raise ValueError('Page image too large')
                    text = pytesseract.image_to_string(Image.frombytes('RGB', (pix.width, pix.height), pix.samples), timeout=12)
                    method = 'pdf-ocr-local'
                chunks.append(text)
            value = '\n'.join(chunks)
            if method != 'pdf-ocr-local': method = 'pdf-text'
            doc.close()
        except ValueError: raise
        except Exception as exc:
            raise ValueError(f'PDF extraction failed: {type(exc).__name__}') from exc
    else:
        from PIL import Image, UnidentifiedImageError
        import pytesseract
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.width * im.height > 14_000_000: raise ValueError('Image too large')
                value = pytesseract.image_to_string(im.convert('RGB'), timeout=12)
            method = 'image-ocr-local'
        except ValueError: raise
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError('Invalid image file') from exc
    if not value.strip(): raise ValueError('No text could be extracted; upload a clearer document')
    return {'text': value[:50000], 'method': method, 'pages': pages,
            'truncated': len(value)>50000, 'local_processing': True,
            'notice': 'OCR may be inaccurate. Verify all amounts, parties and payment terms manually.'}
