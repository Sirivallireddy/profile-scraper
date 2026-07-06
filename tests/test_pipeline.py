import unittest

from pipeline import canonicalize_video_url, extract_timestamp


class PipelineTests(unittest.TestCase):
    def test_canonicalize_youtube_watch_url(self):
        self.assertEqual(
            canonicalize_video_url("https://www.youtube.com/watch?v=abc123&feature=share"),
            "https://www.youtube.com/watch?v=abc123",
        )

    def test_extract_timestamp(self):
        self.assertEqual(extract_timestamp("12:43 Kunal Shah explains it"), "12:43")
        self.assertEqual(extract_timestamp("1:02:15 Kunal Shah explains it"), "1:02:15")
        self.assertIsNone(extract_timestamp("This mentions Kunal Shah but no timestamp"))


if __name__ == "__main__":
    unittest.main()
