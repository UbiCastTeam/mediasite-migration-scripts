import requests
import logging
from mediasite_migration_scripts.utils.common import get_age_days
import json
from copy import copy

logger = logging.getLogger(__name__)


class DataAnalyzer():
    def __init__(self, data, config=None):
        self.config = config
        self.folders = self._filter_data(data)
        self.catalogs = self._set_catalogs()
        self.presentations = self._set_presentations()
        self.mp4_urls = self.set_mp4_urls()

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
        if self.presentations:
            for stat, count in layout_stats.items():
                layout_stats[stat] = round((count / len(self.presentations) * 100))

        return layout_stats

    def count_downloadable_mp4s(self):
        downloadable_mp4 = list()
        status_codes = dict()
        logger.info(f'Counting downloadable mp4s (among {len(self.mp4_urls)} urls)')
        with requests.Session() as session:
            for index, url in enumerate(self.mp4_urls):
                print(f'[{index + 1}]/[{len(self.mp4_urls)}] -- {int(100 * (index + 1) / len(self.mp4_urls))}%', end='\r')
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

    def get_preferred_file(self, files):
        for format_name in ['video/mp4', 'video/x-ms-wmv']:
            for f in files:
                if f.get('format') == format_name and f.get('size_bytes') != 0:
                    return f

    def get_best_video_file(self, files):
        video_file = {}
        max_width = 0

        preferred_file = self.get_preferred_file(files)
        if preferred_file:
            info = preferred_file.get('encoding_infos', {})
            width = int(info.get('width', 0))
            if width >= max_width:
                video_file = preferred_file
        return video_file

    def get_video_format_str(self, encoding_infos=None):
        format_str = 'unknown'
        if encoding_infos:
            if not encoding_infos.get('video_codec'):
                format_str = encoding_infos['audio_codec']
            else:
                encoding_infos.setdefault('audio_codec', 'NOAUDIO')
                format_str = '{video_codec} {audio_codec} {width}x{height}'.format(**encoding_infos)
        return format_str

    def analyze_encoding_infos(self, dump=False):
        encoding_infos = {}

        GB = 1000 * 1000 * 1000

        total_video_count = 0
        video_stats = dict()
        videotypes_dict = dict()

        videotypes = [
            'audio_only',
            'audio_slides',
            'video_only',
            'video_slides',
            'computervideo_only',
            'computervideo_slides',
            'composite_videos',
            'composite_slides',
            'unsupported_videos',
            'empty_videos',
        ]

        class VideoType:
            def __init__(self, name):
                self.name = name
                self.count = 0
                self.duration_hours = 0
                self.size_gbytes = 0
                self.items = list()

            def add(self, pres_id, duration_hours, size_gbytes):
                if pres_id not in self.items:
                    self.items.append(pres_id)
                self.count += 1
                self.duration_hours += duration_hours
                self.size_gbytes += size_gbytes

        for t in videotypes:
            videotypes_dict[t] = VideoType(t)

        stat_template = {
            'count': 0,
            'duration_hours': 0,
            'size_gbytes': 0,
            'less_than_one_year_old': 0,
            'pixels': 0,
        }

        total_duration_h = 0
        total_size_gb = 0
        for folder in self.folders:
            for presentation in folder['presentations']:
                total_video_count += 1

                format_str = ''
                dur_h = size_gb = 0
                videotype = 'unsupported_videos'

                videos = presentation['videos']
                pres_id = presentation['id']
                age_days = get_age_days(presentation['creation_date'])

                slides_stream_type = None
                has_slides = False
                slides_are_synced = False
                if presentation.get('slides'):
                    if len(presentation['slides'].get('urls')) > 0:
                        has_slides = True
                        if presentation['slides'].get('details'):
                            slides_are_synced = True
                        slides_stream_type = presentation['slides']['stream_type']

                if len(videos) > 0:
                    dur_h = videos[0]['files'][0].get('duration_ms', 0) / (3600 * 1000)
                    if dur_h == 0:
                        videotype = 'empty_videos'
                    else:
                        if len(videos) == 1 or (len(videos) == 2 and has_slides):
                            video = presentation['videos'][0]
                            video_stream_type = video['stream_type']
                            video_file = self.get_best_video_file(video['files'])
                            encoding_infos = video_file.get('encoding_infos')
                            format_str = self.get_video_format_str(encoding_infos)
                            size_gb = video_file.get('size_bytes', 0) / GB
                            if format_str == 'AAC':
                                if has_slides and slides_are_synced:
                                    format_str = 'AAC with slides'
                                    videotype = 'audio_slides'
                                else:
                                    videotype = 'audio_only'
                            elif format_str != 'unknown':
                                if len(videos) == 1:
                                    if has_slides:
                                        if video_stream_type == slides_stream_type:
                                            if not slides_are_synced:
                                                videotype = 'computervideo_only'
                                            else:
                                                videotype = 'computervideo_slides'
                                        elif slides_are_synced:
                                            videotype = 'video_slides'
                                        else:
                                            # there are slides but they are not synced
                                            videotype = 'video_only'
                                    else:
                                        videotype = 'video_only'
                                else:
                                    if slides_are_synced:
                                        videotype = 'composite_slides'
                                    else:
                                        videotype = 'composite_videos'
                        elif len(videos) == 2:
                            videotype = 'composite_videos'
                            composite_info = {
                                'width': 0,
                                'height': 0,
                                'video_codec': 'H264',
                                'audio_codec': 'AAC',
                            }
                            for v in videos:
                                size_gb += video_file.get('size_bytes', 0) / GB
                                encoding_infos = self.get_best_video_file(v['files']).get('encoding_infos')
                                # skip audio-only resources
                                if encoding_infos and encoding_infos.get('video_codec'):
                                    composite_info['width'] += encoding_infos['width']
                                    composite_info['height'] = max(composite_info['height'], encoding_infos['height'])
                            format_str = self.get_video_format_str(composite_info) + ' (composite)'

                    videotypes_dict[videotype].add(pres_id, dur_h, size_gb)

                    if video_stats.get(format_str) is None:
                        video_stats[format_str] = dict(stat_template)
                        if encoding_infos:
                            video_stats[format_str]['pixels'] = encoding_infos.get('width', 0) * encoding_infos.get('height', 0)

                    video_stats[format_str]['count'] += 1
                    video_stats[format_str]['duration_hours'] += dur_h
                    video_stats[format_str]['size_gbytes'] += size_gb
                    if age_days < 365:
                        video_stats[format_str]['less_than_one_year_old'] += 1

                    total_duration_h += dur_h
                    total_size_gb += size_gb

        # generate a test library with one sample of each type
        test_data = []

        types_table_string = 'Type\tCount\tDuration_h\tSize_GB\tSample\n'
        for videotype in videotypes:
            data = videotypes_dict[videotype]
            sample_pres_id = data.items[0] if data.count > 0 else None
            # clone it so that we can anonymize it
            sample_folder = self.copy_folder_by_presentation_id(sample_pres_id, new_name=videotype)
            test_data.append(sample_folder)
            types_table_string += f'{videotype}\t{data.count}\t{int(data.duration_hours)}\t{int(data.size_gbytes)}\t{sample_pres_id}\n'

        encoding_infos = {
            'total_video_count': total_video_count,
            'total_importable': total_video_count - videotypes_dict['unsupported_videos'].count,
            'total_duration_h': int(total_duration_h),
            'total_size_tb': int(total_size_gb / 1000),
            'video_stats': video_stats,
            'video_types_stats': types_table_string,
        }

        def get_var(my_var):
            my_var_name = [k for k, v in locals().iteritems() if v == my_var][0]
            return my_var_name

        if dump:
            for videolist in videotypes:
                fname = 'presentations_' + videolist + '.txt'
                logger.info(f'Dumping {fname}')
                with open(fname, 'w') as f:
                    f.write('\n'.join(videotypes_dict[videolist].items))

            fname = 'samples.json'
            with open(fname, 'w') as f:
                logger.info(f'Creating sample test data into {fname}')
                json.dump(test_data, f, indent=2, sort_keys=True)

        return encoding_infos

    def _filter_data(self, data):
        folders = list()
        whitelist = []
        skipped_folders = set()
        skipped_presentations = set()
        if self.config:
            whitelist = ['/' + x for x in self.config['whitelist']]
            logger.info(f'Restricting to whitelisted paths {whitelist}')

        for folder in data:
            skip = False
            if whitelist:
                skip = True
                for w in whitelist:
                    if w in folder['path']:
                        skip = False
            for p in folder['presentations']:
                if not skip:
                    if folder not in folders:
                        folders.append(folder)
                else:
                    skipped_folders.add(folder['id'])
                    skipped_presentations.add(p['id'])
        if whitelist:
            logger.info(f'Skipped {len(skipped_folders)} folders and {len(skipped_presentations)} presentations not matching the path whitelist')
        return folders

    def copy_folder_by_presentation_id(self, pres_id, new_name=None):
        for folder in self.folders:
            for presentation in folder['presentations']:
                if presentation['id'] == pres_id:
                    folder_copy = self.anonymize_data(folder)
                    presentation_copy = self.anonymize_data(presentation)
                    folder_copy['presentations'] = [presentation_copy]
                    if new_name is not None:
                        presentation_copy['name'] = new_name + ' sample (name)'
                        presentation_copy['title'] = new_name + ' sample (title)'
                    return folder_copy

    def anonymize_data(self, data):
        anon_data = copy(data)
        fields = [
            'description',
            'id',
            'name',
            'owner_username',
            'parent_id',
            'path',
            'creator',
            'title',
            'display_name',
            'owner_display_name',
            'owner_mail',
            'presenter_display_name',
            'OcrText',
            'url'
        ]
        if isinstance(anon_data, dict):
            for key, val in anon_data.items():
                new_val = None
                if isinstance(val, dict):
                    new_val = self.anonymize_data(val)
                elif isinstance(val, list):
                    new_val = [self.anonymize_data(i) for i in val]
                else:
                    if key in fields:
                        if 'url' in key:
                            new_val = f'https://anon.com/{key}'
                        elif 'mail' in key:
                            new_val = 'john.doe@server.com'
                        else:
                            new_val = f'anonymized {key}'
                if new_val is not None:
                    anon_data[key] = new_val
        elif isinstance(anon_data, list):
            for i in anon_data:
                i = self.anonymize_data(i)
        elif isinstance(anon_data, str):
            if 'http' and '://' in anon_data:
                anon_data = 'https://anon.com/fake'
            else:
                anon_data = 'anon text'

        return anon_data

    def _set_presentations(self):
        presentations = []
        for folder in self.folders:
            for p in folder['presentations']:
                presentations.append(p)
        return presentations

    def set_mp4_urls(self):
        mp4_urls = list()
        for presentation in self.presentations:
            if not DataAnalyzer.has_multiple_videos(presentation):
                for video_file in presentation['videos'][0]['files']:
                    if video_file['format'] == 'video/mp4':
                        mp4_urls.append(video_file['url'])
                        break
        return mp4_urls

    def _set_catalogs(self):
        catalogs = list()
        for folder in self.folders:
            catalogs.extend(folder.get('catalogs'))
        return catalogs

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
