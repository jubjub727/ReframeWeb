import unittest

from reframe_agent_host.speech.chunking import speech_chunks


class SpeechChunkTests(unittest.TestCase):
    def test_short_text_stays_single_chunk(self):
        self.assertEqual(speech_chunks("  Hello   there.  "), ("Hello there.",))

    def test_long_text_splits_before_tts_inference(self):
        text = (
            "This is a deliberately long spoken response without much punctuation "
            "so the text to speech system can begin generating audio from a small "
            "first chunk instead of waiting for the entire paragraph to synthesize."
        )

        chunks = speech_chunks(text, max_chars=64, first_chunk_chars=64)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 64 for chunk in chunks))
        self.assertEqual(" ".join(chunks), text)

    def test_joke_first_chunk_is_full_setup_sentence(self):
        chunks = speech_chunks(
            "A man walks into a library and asks for books about paranoia. "
            "The librarian whispers, 'They're right behind you.'"
        )

        self.assertEqual(
            chunks[0],
            "A man walks into a library and asks for books about paranoia.",
        )
        self.assertGreater(len(chunks[0]), 42)


if __name__ == "__main__":
    unittest.main()
