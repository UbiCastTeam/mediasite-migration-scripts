class StatsMaker():
    def __init__(self):
        self.format_stats = {}
        self.layout_stats = {}

    def compute_videos_stats(self, presentations):
        count = {}
        for video in presentations:
            video_format = self.find_best_format(video)
            if video_format in count:
                count[video_format] += 1
            else:
                count[video_format] = 1

        for v_format, v_count in count.items():
            self.format_stats[v_format] = str(round((v_count / len(presentations)) * 100)) + '%'
        return self.format_stats

    def compute_layout_stats(self, presentations):
        self.layout_stats = {'mono': 0, 'mono + slides': 0, 'multiple': 0}
        for presentation in presentations:
            if self.is_video_composition(presentation):
                self.layout_stats['multiple'] += 1
            elif len(presentation['slides']) > 0:
                self.layout_stats['mono + slides'] += 1
            else:
                self.layout_stats['mono'] += 1
        for stat, count in self.layout_stats.items():
            self.layout_stats[stat] = str(round((count / len(presentations) * 100))) + '%'

        return self.layout_stats

    def find_best_format(self, video):
        formats_priority = ['video/mp4', 'video/x-ms-wmv', 'video/x-mp4-fragmented']
        for priority in formats_priority:
            for file in video['videos'][0]['files']:
                if file['format'] == priority:
                    return file['format']

    def is_only_ism(self, presentation_videos):
        for video in presentation_videos['videos']:
            for file in video['files']:
                if file['format'] != 'video/x-mp4-fragmented':
                    return False
        return True

    def is_video_composition(self, presentation_videos):
        return len(presentation_videos['videos']) > 1
