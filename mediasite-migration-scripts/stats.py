def compute_videos_stats(presentations):
    count = {}
    for video in presentations:
        video_format = find_best_format(video)
        if video_format in count:
            count[video_format] += 1
        else:
            count[video_format] = 1

    stats = {}
    for v_format, v_count in count.items():
        stats[v_format] = str(round((v_count / len(presentations)) * 100)) + '%'
    return stats

def compute_global_stats(presentations):
    stats = {'mono': 0, 'mono + slides': 0, 'multiple': 0}
    for presentation in presentations:
        if is_video_composition(presentation):
            stats['multiple'] += 1
        elif len(presentation['slides']) > 0:
            stats['mono + slides'] += 1
        else:
            stats['mono'] += 1
    for stat, count in stats.items():
        stats[stat] = str(round((count / len(presentations) * 100))) + '%'

    return stats

def find_best_format(video):
    formats_priority = ['video/mp4', 'video/x-ms-wmv', 'video/x-mp4-fragmented']
    for priority in formats_priority:
        for file in video['videos'][0]['files']:
            if file['format'] == priority:
                return file['format']

def is_only_ism(presentation_videos):
    for video in presentation_videos['videos']:
        for file in video['files']:
            if file['format'] != 'video/x-mp4-fragmented':
                return False
    return True

def is_video_composition(presentation_videos):
    return len(presentation_videos['videos']) > 1
