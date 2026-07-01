from __future__ import annotations

import unittest

from office_app.server.subject import generate_subject


class SubjectTests(unittest.TestCase):
    def test_generate_subject_uses_clean_body_text(self) -> None:
        self.assertEqual(
            generate_subject('the system isnt listing all rooms when i say "list rooms".'),
            'the system isnt listing all rooms when i say "list rooms".',
        )

    def test_generate_subject_preserves_question_text(self) -> None:
        self.assertEqual(generate_subject("what is system health?"), "what is system health?")

    def test_generate_subject_truncates_long_text_cleanly(self) -> None:
        subject = generate_subject(
            "this is a very long memo body that should be shortened without chopping the last word in the middle of the subject line for the header"
        )
        self.assertTrue(subject.endswith("..."))
        self.assertLessEqual(len(subject), 75)


if __name__ == "__main__":
    unittest.main()
