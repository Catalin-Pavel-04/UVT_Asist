from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from evaluation.qa_compare import phrase_present

QUESTIONS_FILE = BACKEND_DIR / "evaluation" / "eval_questions.json"
QA_100_FILE = BACKEND_DIR / "evaluation" / "eval_qa_100.json"
REQUIRED_FIELDS = {
    "id",
    "category",
    "faculty_id",
    "question",
    "expected_url_contains",
    "expected_title_contains",
    "should_have_answer",
    "notes",
}
REQUIRED_QA_FIELDS = REQUIRED_FIELDS | {
    "ideal_answer",
    "answer_must_include",
    "answer_should_not_include",
    "expected_confidence",
}
REQUIRED_CATEGORIES = {
    "orar",
    "contact/secretariat",
    "admitere",
    "burse",
    "regulamente/metodologii",
    "cazare/cămine",
    "calendar academic",
    "voluntariat/credite",
}


def load_questions() -> list[dict]:
    with QUESTIONS_FILE.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    questions = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(questions, list):
        raise AssertionError("Evaluation dataset must be a JSON list or an object with a questions list.")
    return questions


def load_json_questions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    questions = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(questions, list):
        raise AssertionError(f"{path} must be a JSON list or an object with a questions list.")
    return questions


class EvalQuestionsDatasetTests(unittest.TestCase):
    def test_eval_questions_file_exists_and_is_valid(self) -> None:
        self.assertTrue(QUESTIONS_FILE.exists())
        questions = load_questions()
        self.assertGreater(len(questions), 0)

    def test_each_question_has_required_shape(self) -> None:
        questions = load_questions()
        ids = set()

        for item in questions:
            self.assertIsInstance(item, dict)
            self.assertTrue(REQUIRED_FIELDS.issubset(item), item.get("id", "<missing id>"))
            self.assertNotIn(item["id"], ids)
            ids.add(item["id"])

            self.assertIsInstance(item["expected_url_contains"], list, item["id"])
            self.assertIsInstance(item["expected_title_contains"], list, item["id"])
            self.assertIsInstance(item["should_have_answer"], bool, item["id"])
            self.assertTrue(str(item["question"]).strip(), item["id"])
            self.assertTrue(str(item["category"]).strip(), item["id"])
            self.assertTrue(str(item["faculty_id"]).strip(), item["id"])

    def test_dataset_covers_required_categories_and_unanswerable_cases(self) -> None:
        questions = load_questions()
        categories = {str(item.get("category", "")).strip() for item in questions}

        self.assertTrue(REQUIRED_CATEGORIES.issubset(categories))
        self.assertTrue(any(item.get("should_have_answer") is False for item in questions))

    def test_qa_100_dataset_has_exactly_100_valid_items(self) -> None:
        self.assertTrue(QA_100_FILE.exists())
        questions = load_json_questions(QA_100_FILE)
        self.assertEqual(len(questions), 100)
        ids = set()

        for item in questions:
            self.assertIsInstance(item, dict)
            self.assertTrue(REQUIRED_QA_FIELDS.issubset(item), item.get("id", "<missing id>"))
            self.assertNotIn(item["id"], ids)
            ids.add(item["id"])
            self.assertIsInstance(item["expected_url_contains"], list, item["id"])
            self.assertIsInstance(item["expected_title_contains"], list, item["id"])
            self.assertIsInstance(item["answer_must_include"], list, item["id"])
            self.assertIsInstance(item["answer_should_not_include"], list, item["id"])
            self.assertIsInstance(item["should_have_answer"], bool, item["id"])
            self.assertTrue(str(item["question"]).strip(), item["id"])
            self.assertTrue(str(item["ideal_answer"]).strip(), item["id"])

        self.assertTrue(any(item.get("should_have_answer") is False for item in questions))

    def test_qa_phrase_alternatives_are_supported(self) -> None:
        self.assertTrue(phrase_present("Structura anului universitar este publicata oficial.", "calendar|structura"))
        self.assertFalse(phrase_present("Sursa oficiala este pagina de burse.", "calendar|structura"))


if __name__ == "__main__":
    unittest.main()
