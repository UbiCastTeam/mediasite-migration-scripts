import requests


class DataAnalyzer():
    def __init__(self, data):
        self.format_stats = {}
        self.layout_stats = {}
        self.folders = data
        self.presentations = self.order_videos_by_presentations(data)
        self.mp4_urls = []

    def order_videos_by_presentations(self, data):
        presentations = []
        for folder in data:
            for p in folder['presentations']:
                presentations.append(p)
        return presentations

    def set_mp4_urls(self):
        for presentation in self.presentations:
            if not DataAnalyzer.has_multiple_videos(presentation):
                for file in presentation['videos'][0]['files']:
                    if file['format'] == 'video/mp4':
                        self.mp4_urls.append(file['url'])
                        break
        return self.mp4_urls

    def compute_videos_stats(self):
        if not self.format_stats:
            count = {}
            for video in self.presentations:
                video_format = DataAnalyzer.find_best_format(video)
                if video_format in count:
                    count[video_format] += 1
                else:
                    count[video_format] = 1

            for v_format, v_count in count.items():
                self.format_stats[v_format] = round((v_count / len(self.presentations)) * 100)

        return self.format_stats

    def compute_layout_stats(self):
        if not self.layout_stats:
            self.layout_stats = {'mono': 0, 'mono + slides': 0, 'multiple': 0}
            for presentation in self.presentations:
                if self.has_multiple_videos(presentation):
                    self.layout_stats['multiple'] += 1
                elif len(presentation['slides']) > 0:
                    self.layout_stats['mono + slides'] += 1
                else:
                    self.layout_stats['mono'] += 1
            for stat, count in self.layout_stats.items():
                self.layout_stats[stat] = round((count / len(self.presentations) * 100))

        return self.layout_stats

    def analyse_downloadable_mp4(self):
        self.set_mp4_urls()
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
