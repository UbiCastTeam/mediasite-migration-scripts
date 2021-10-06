#!/usr/bin/env python3
import time
import sys
import signal
import gi
import json
import logging
from pathlib import Path
import argparse
import math
from fractions import Fraction

import mediasite_migration_scripts.utils.common as utils

gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
from gi.repository import GLib # noqa
from gi.repository import Gst  # noqa
from gi.repository import GstPbutils  # noqa

Gst.init([])


def is_media_folder(path):
    return len(list(path.glob('*.mp4'))) != 0


TIMEOUT_MS = 60000


class Merger:
    def __init__(self, mainloop, options):
        self.mainloop = mainloop
        self.options = options
        self.timeout_id = None
        self.force_eos_id = None

    def get_layout_preset(self, width, height, layers_data):
        layout_preset = {
            'composition_area': {
                'w': width,
                'h': height,
            },
            'layers': layers_data,
        }
        return layout_preset

    def get_layout_layer(self, label, x, y, w, h, index, orig_w, orig_h, change_detection=False, autocam_enabled=False):
        return {
            'label': label,
            'id': index,
            'source': {
                'type': 'video',
                'roi': {
                    'x': x,
                    'y': y,
                    'w': w,
                    'h': h
                },
                'native_resolution': {
                    'w': orig_w,
                    'h': orig_h,
                },
                'change_detection_enabled': change_detection,
                'autocam_enabled': autocam_enabled,
            }
        }

    def convert(self, media_folder):
        self.folder = folder = Path(media_folder)
        self.output_file = output_file = folder / 'composite.mp4'
        videomixer_width = self.options.width
        videomixer_height = self.options.height
        framerate = 0

        self.duration_s = 0
        total_native_width = 0
        max_height = 0
        input_videos = {}
        for video in folder.glob('*.mp4'):
            if video != output_file:
                info = self.get_media_info(video)
                total_native_width += info['width']
                max_height = max(max_height, info['height'])
                self.duration_s = max(self.duration_s, info['duration_s'])
                input_videos[video.name] = info

        reduction_factor = 1
        if total_native_width < videomixer_width:
            print(f'Warning, native files summed size {total_native_width}x{max_height} is smaller than target resolution {videomixer_width}x{videomixer_height}')
            videomixer_width, videomixer_height = self.find_optimal_rendering_size(total_native_width, max_height)
            reduction_factor = videomixer_width / total_native_width
            print(f'Falling back to {videomixer_width}x{videomixer_height}')
        elif total_native_width > videomixer_width:
            print(f'Native files summed size {total_native_width}x{max_height} is larger than target resolution, will reduce to match target resolution')
            reduction_factor = videomixer_width / total_native_width

        print(f'Reduction factor: {reduction_factor:.2f}')

        layers_data = list()
        pipeline_desc = ''
        index = 0
        has_audio = False
        x_offset = 0
        compositor_options = ''
        for video_name, video_info in input_videos.items():
            # take highest framerate
            framerate = max(framerate, Fraction(video_info['avg_frame_rate']))
            ratio = video_info['width'] / video_info['height']
            adjusted_width = int(video_info['width'] * reduction_factor)
            adjusted_heigth = int(adjusted_width / ratio)
            print(f'{video_name}: {video_info["width"]}x{video_info["height"]} --> {adjusted_width}x{adjusted_heigth}')
            y = int((videomixer_height - adjusted_heigth) / 2)
            pad_data = {
                'pad': f'sink_{index}',
                'x': x_offset,
                'y': y,
                'width': adjusted_width,
                'height': adjusted_heigth,
            }
            layers_data.append(self.get_layout_layer(
                video_name.split('.mp4')[0],
                x_offset,
                y,
                adjusted_width,
                adjusted_heigth,
                index + 1,
                videomixer_width,
                videomixer_height,
                video_name == 'Slides.mp4',
                False,
            ))
            compositor_options += '{pad}::xpos={x} {pad}::ypos={y} '.format(**pad_data)
            pad_caps = 'video/x-raw, format=(string)I420, width=(int){width}, height=(int){height}, pixel-aspect-ratio=(fraction)1/1'.format(**pad_data)
            pipeline_desc += f' filesrc location={video_info["path"]} ! qtdemux name=demux_{index} ! queue name=qh264dec_{index} ! avdec_h264 ! queue name=vscale{index} ! videoscale ! {pad_caps} ! queue ! vmix. '
            if video_name != 'Slides.mp4' and not has_audio:
                pipeline_desc += f' demux_{index}. ! queue name=qaparse ! aacparse ! queue name=amux max-size-time={60 * Gst.SECOND} max-size-bytes=0 max-size-buffers=0 ! mux. '
                has_audio = True
            index += 1
            x_offset = adjusted_width

        bitrate = int(math.sqrt(videomixer_width * videomixer_height) * 2)
        print(f'Encoding {self.duration_s}s file at {videomixer_width}x{videomixer_height} {framerate} fps at {bitrate} kbits/s')
        x264enc_options = f'speed-preset=faster tune=zerolatency bitrate={bitrate}'

        pipeline_desc += f'compositor name=vmix background=black {compositor_options} ! video/x-raw, format=(string)I420, width=(int){videomixer_width}, height=(int){videomixer_height}, framerate=(fraction){framerate}, colorimetry=(string)bt709 ! tee name=tee ! queue name=qvenc ! x264enc {x264enc_options} ! progressreport update-freq=1 silent=true ! queue name=qmux ! mp4mux name=mux ! filesink location={output_file.resolve()}'

        if self.options.preview:
            pipeline_desc += ' tee. ! queue name=qvsink ! autovideosink sync=false'

        print(pipeline_desc)
        self.pipeline = Gst.parse_launch(pipeline_desc)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::eos', self._on_eos)
        bus.connect('message::error', self._on_error)
        bus.connect('message', self._on_message)

        self.layout_preset = self.get_layout_preset(videomixer_width, videomixer_height, layers_data)

        GLib.idle_add(self.pipeline.set_state, Gst.State.PLAYING)
        self.start_time = time.time()
        self.timeout_id = GLib.timeout_add(TIMEOUT_MS, self._on_timeout)
        if self.options.max_duration:
            logging.info(f'--max-duration option passed, will stop after {self.options.max_duration}s')
            self.force_eos_id = GLib.timeout_add_seconds(self.options.max_duration, self.send_eos)

    def find_optimal_rendering_size(self, width, height):
        # select the first resolution supported by mediaserver that can fit all pixels
        resolutions = [
            (1280, 720),
            (1920, 1080),
            (2560, 1440),
            (3840, 2160)
        ]
        for w, h in resolutions:
            if w >= width and h >= height:
                return w, h

    def dump_layout(self):
        layout_file = self.folder / 'mediaserver_layout.json'
        with open(layout_file, 'w') as f:
            print(f'Wrote {layout_file}')
            json.dump(self.layout_preset, f, sort_keys=True, indent=4)

    def send_eos(self):
        logging.info('Forcing EOS')
        event = Gst.Event.new_eos()
        Gst.Element.send_event(self.pipeline, event)

    def _on_timeout(self):
        self.timeout_id = None
        logging.error(f'No progress after {TIMEOUT_MS}ms, aborting with error')
        self.abort()
        return False

    def _on_error(self, bus, message):
        error, debug = message.parse_error()
        logging.error(f'{error}: {debug}')
        self.pipeline.set_state(Gst.State.NULL)
        self.abort()

    def _on_eos(self, bus, message):
        took = time.time() - self.start_time
        processing_speed = round(self.duration_s / took, 2)
        logging.info(f'Finished in {int(took)}s: {self.output_file} with processing speed: {processing_speed}x')
        self.dump_layout()
        GLib.idle_add(self.cancel_timeout)
        GLib.idle_add(self.cancel_force_eos)
        self.mainloop.quit()

    def cancel_force_eos(self):
        if self.force_eos_id:
            GLib.source_remove(self.force_eos_id)
            self.force_eos_id = None

    def cancel_timeout(self):
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None

    def abort(self):
        logging.info(f'Aborting and removing {self.output_file.name}')
        self.output_file.unlink()
        self.cancel_timeout()
        self.cancel_force_eos()
        self.mainloop.quit()
        sys.exit(1)

    def _on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.ELEMENT:
            struct = message.get_structure()
            sname = struct.get_name()
            #source = message.src.get_name()
            if sname == 'progress':
                percent = int(struct.get_value('percent'))
                if sys.stdout.isatty():
                    print(f'Processing: {percent}%', end='\r')
                self.cancel_timeout()
                self.timeout_id = GLib.timeout_add(TIMEOUT_MS, self._on_timeout)

    def get_media_info(self, media_file):
        path = str(Path(media_file).resolve())
        uri = Gst.filename_to_uri(path)
        try:
            info = GstPbutils.Discoverer.new(10 * Gst.SECOND).discover_uri(uri)
        except gi.repository.GLib.Error as e:
            logging.error(f'Could not discover file {media_file}: {e}')

        try:
            vinfo = info.get_video_streams()[0]
        except IndexError:
            logging.error(f'File {media_file} contains no video stream')
            sys.exit(1)

        result = {
            'width': vinfo.get_width(),
            'height': vinfo.get_height(),
            'avg_frame_rate': '%s/%s' % (vinfo.get_framerate_num(), vinfo.get_framerate_denom()),
            'duration_s': int(info.get_duration() / Gst.SECOND),
            'uri': uri,
            'path': path,
        }

        try:
            ainfo = info.get_audio_streams()[0]
            result['sample_rate'] = ainfo.get_sample_rate()
            result['a_codec'] = GstPbutils.pb_utils_get_codec_description(ainfo.get_caps())
        except IndexError:
            logging.warning(f'File {media_file} contains no audio stream')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-v',
        '--verbose',
        help='set verbosity to DEBUG',
        action='store_true'
    )

    parser.add_argument(
        '--preview',
        help='Enable realtime video preview',
        action='store_true'
    )

    parser.add_argument(
        'folder',
        type=str,
        help='Folder name in which to look for media (single media)',
    )

    parser.add_argument(
        '--width',
        type=int,
        help='Rendering width',
        default=2560,
    )

    parser.add_argument(
        '--max-duration',
        type=int,
        help='Stop after this amount of seconds (disabled by default). Can be useful for looking at results quicker.',
        default=0,
    )

    parser.add_argument(
        '--height',
        type=int,
        help='Rendering height',
        default=1440,
    )

    args = parser.parse_args()
    utils.set_logger(verbose=args.verbose)

    mainloop = GLib.MainLoop()

    c = Merger(mainloop, args)

    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, c.abort)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, c.abort)

    media_folder = Path(args.folder)
    if is_media_folder(media_folder):
        c.convert(media_folder)
        mainloop.run()
    else:
        logging.error(f'No media found at {media_folder}')
        sys.exit(1)
