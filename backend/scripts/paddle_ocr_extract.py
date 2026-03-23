from __future__ import annotations

import argparse
import json
import sys

TEXT_KEYS = ("rec_texts", "texts", "text")


def _collect_texts(value, allow_plain_text: bool = False) -> list[str]:
    texts = []

    if isinstance(value, str):
        if allow_plain_text and value.strip():
            texts.append(value.strip())
        return texts

    if isinstance(value, dict):
        for key in TEXT_KEYS:
            if key in value:
                texts.extend(_collect_texts(value[key], allow_plain_text=True))

        for key, nested in value.items():
            if key in TEXT_KEYS:
                continue
            if isinstance(nested, (dict, list, tuple)):
                texts.extend(_collect_texts(nested, allow_plain_text=False))

        return texts

    if isinstance(value, (list, tuple)):
        for item in value:
            texts.extend(_collect_texts(item, allow_plain_text=allow_plain_text))

    return texts


def _extract_from_predict_results(results) -> str:
    text_parts = []

    for result in results:
        payload = getattr(result, "json", None)
        if callable(payload):
            payload = payload()
        elif payload is None:
            payload = result

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass

        text_parts.extend(_collect_texts(payload))

    seen = set()
    unique = []
    for text in text_parts:
        if text not in seen:
            unique.append(text)
            seen.add(text)

    return " ".join(unique).strip()


def _extract_from_legacy_results(results) -> str:
    text_parts = []

    for page in results:
        for line in page or []:
            if not isinstance(line, (list, tuple)) or len(line) < 2:
                continue

            candidate = line[1]
            if isinstance(candidate, (list, tuple)) and candidate:
                text = candidate[0]
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())

    return " ".join(text_parts).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path")
    parser.add_argument("--lang", default="ro")
    args = parser.parse_args()

    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        ocr = PaddleOCR(lang=args.lang)
        if hasattr(ocr, "predict"):
            text = _extract_from_predict_results(ocr.predict(args.input_path))
        else:
            text = _extract_from_legacy_results(ocr.ocr(args.input_path, cls=True))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps({"text": text}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
