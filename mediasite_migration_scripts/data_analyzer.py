import requests
import logging


class DataAnalyzer():
    def __init__(self, data):
        self.folders = data
        self.presentations = self._order_videos_by_presentations(data)
        self.mp4_urls = self._set_mp4_urls()

    def analyze_videos_infos(self):
        format_stats = self._get_video_format_stats()
        layout_stats = self._get_layout_stats()

        return format_stats, layout_stats

    def _get_video_format_stats(self):
        format_stats = {}
        count = {}
        for video in self.presentations:
            video_format = DataAnalyzer.find_best_format(video)
            if video_format in count:
                count[video_format] += 1
            else:
                count[video_format] = 1

        for v_format, v_count in count.items():
            format_stats[v_format] = round((v_count / len(self.presentations)) * 100)

        return format_stats

    def _get_layout_stats(self):
        layout_stats = {'mono': 0, 'mono + slides': 0, 'multiple': 0}
        for presentation in self.presentations:
            if self.has_multiple_videos(presentation):
                layout_stats['multiple'] += 1
            elif len(presentation['slides']) > 0:
                layout_stats['mono + slides'] += 1
            else:
                layout_stats['mono'] += 1
        for stat, count in layout_stats.items():
            layout_stats[stat] = round((count / len(self.presentations) * 100))

        return layout_stats

    def count_downloadable_mp4s(self):
        self._set_mp4_urls()
        downloadable_mp4 = list()
        status_codes = dict()
        print(f'Counting downloadable mp4s (among {len(self.mp4_urls)} urls)')
        with requests.Session() as session:
            for index, url in enumerate(self.mp4_urls):
                print(f'[{index + 1}]/[{len(self.mp4_urls)}]', end='\r')
                ok = False
                # IIS returns 401 when trying head(), so let us just test the smallest GET possible
                with session.get(url, stream=True) as r:
                    code = str(r.status_code)
                    if not status_codes.get(code):
                        status_codes[code] = 0
                    status_codes[code] += 1
                    ok = r.ok

                if ok:
                    downloadable_mp4.append(url)

        return {'downloadable_mp4': downloadable_mp4, 'status_codes': status_codes}

    def analyse_folders(self):
        empty_folders = list()
        empty_user_folders = list()
        more_than_one_presentation = list()
        exactly_one_presentation = list()

        for folder in self.folders:
            if folder['presentations']:
                if len(folder['presentations']) > 1:
                    more_than_one_presentation.append(folder)
                else:
                    exactly_one_presentation.append(folder)
            else:
                if 'Mediasite Users' in folder['path']:
                    empty_user_folders.append(folder)
                empty_folders.append(folder)

        infos = {
            'empty_folders': empty_folders,
            'empty_user_folders': empty_user_folders,
            'more_than_one_presentation': more_than_one_presentation,
            'exactly_one_presentation': exactly_one_presentation
        }
        return infos

    def analyze_encoding_infos(self):
        encoding_infos = {}

        total_videos = 0
        videos_with_encoding_info = 0
        videos_with_no_encoding_infos = list()
        video_stats = dict()
        video_durations = dict()
        total_duration_h = 0
        total_size_bytes = 0
        for folder in self.folders:
            for presentation in folder['presentations']:
                for video in presentation['videos']:
                    got_encoding_infos = False
                    for file in video['files']:
                        total_videos += 1
                        if file.get('encoding_infos'):
                            try:
                                format_str = '{video_codec} {audio_codec} {width}x{height}'.format(**file['encoding_infos'])
                            except KeyError:
                                logging.debug(f'Not all encoding infos for this file. Maybe the file is not a video: {file["url"]}')
                                logging.debug(f'In presentation: {presentation["id"]}')
                            if not video_stats.get(format_str):
                                video_stats[format_str] = 0
                            video_stats[format_str] += 1

                            if not video_durations.get(format_str):
                                video_durations[format_str] = 0
                            video_durations[format_str] += int(file.get('duration_ms', 0) / (3600 * 1000))

                            videos_with_encoding_info += 1
                            got_encoding_infos = True
                            break
                    if not got_encoding_infos:
                        videos_with_no_encoding_infos.append(presentation)
                    total_duration_h += int(file.get('duration_ms', 0) / (3600 * 1000))
                    total_size_bytes += file.get('size_bytes', 0)

        encoding_infos = {
            'total_duration_h': total_duration_h,
            'total_size_bytes': total_size_bytes,
            'videos_with_encoding_info': videos_with_encoding_info,
            'videos_with_no_encoding_infos': videos_with_no_encoding_infos,
            'total_videos': total_videos,
            'video_stats': video_stats,
            'video_durations': video_durations,
        }
        return encoding_infos

    def _order_videos_by_presentations(self, data):
        presentations = []
        for folder in data:
            for p in folder['presentations']:
                presentations.append(p)
        return presentations

    def _set_mp4_urls(self):
        mp4_urls = list()
        for presentation in self.presentations:
            if not DataAnalyzer.has_multiple_videos(presentation):
                for file in presentation['videos'][0]['files']:
                    if file['format'] == 'video/mp4':
                        mp4_urls.append(file['url'])
                        break
        return mp4_urls

    @staticmethod
    def find_best_format(video):
        formats_priority = ['video/mp4', 'video/x-ms-wmv', 'video/x-mp4-fragmented']
        for priority in formats_priority:
            for file in video['videos'][0]['files']:
                if file['format'] == priority:
                    return file['format']

    @staticmethod
    def has_only_smooth_streaming(presentation_videos):
        for video in presentation_videos['videos']:
            for file in video['files']:
                if file['format'] != 'video/x-mp4-fragmented':
                    return False
        return True

    @staticmethod
    def has_multiple_videos(presentation_videos):
        return len(presentation_videos['videos']) > 1
