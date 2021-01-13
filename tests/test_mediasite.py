import os
import logging
from decouple import config
from unittest import TestCase
from .. import mediasite_script


class MediaSiteTest(TestCase):
    def setUp(self):
        self.script = mediasite_script
        self.videos_formats = [
            {
                "presentation_id": "05546464sg4s6egsfg64s6egr4",
                "video_formats": [
                    "video/x-mp4-fragmented",
                    "video/mp4",
                    "video/x-ms-wmv"
                ]
            },
            {
                "presentation_id": "05546464sg4s6egsfg64s786egr4",
                "video_formats": [
                    "video/x-mp4-fragmented",
                    "video/mp4"
                ]
            },
            {
                "presentation_id": "05546464sg4s6egsfg764s6egr4",
                "video_formats": [
                    "video/mp4"
                ]
            },
            {
                "presentation_id": "60d46baaf41b49eda50b12b6bcd673751d",
                "video_formats": [
                    "video/mp4",
                    "video/mp4"
                ]
            },
            {
                "presentation_id": "0d9201b22797454081762edb0e55ae681d",
                "video_formats": [
                    "video/x-mp4-fragmented"
                ]
            },
            {
                "presentation_id": "57ccb18df4a5427cb95e161d27d843f61d",
                "video_formats": [
                    "video/x-mp4-fragmented",
                    "video/mp4"
                ]
            },
        ]

    def test_get_video_stats(self):
        stats = {
            'video/mp4': '0%',
            '': '0%',
            '': '0%'
        }
        self.assertEqual(self.script.get_video_stats(self.videos_formats, len(self.videos_formats)),
                         stats)
