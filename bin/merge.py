#!/usr/bin/env python3
import time
import sys
import signal
import gi
import json
import logging
from pathlib import Path
import argparse
from fractions import Fraction

gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
from gi.repository import GLib # noqa
from gi.repository import Gst  # noqa
from gi.repository import GstPbutils  # noqa

Gst.init([])


def setup_logging(verbose=False):
    logging.addLevelName(logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
    logging.addLevelName(logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
    level = getattr(logging, 'DEBUG' if verbose else 'INFO')
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )


def is_media_folder(path):
    return len(list(path.glob('*.mp4'))) != 0


class Merger:
    def __init__(self, mainloop, options):
        self.mainloop = mainloop
        self.options = options

    def get_layout_preset(self, layers_data):
        layout_preset = {
            'composition_area': {
                'w': self.options.width,
                'h': self.options.height,
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
        folder = Path(media_folder)
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
        if total_native_width > videomixer_width:
            reduction_factor = videomixer_width / total_native_width

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
            compositor_options += '{pad}::xpos={x} {pad}::ypos={y} {pad}::width={width} {pad}::height={height} '.format(**pad_data)
            pipeline_desc += f' filesrc location={video_info["path"]} ! qtdemux name=demux_{index} ! queue name=qh264dec_{index} ! avdec_h264 ! vmix. '
            if video_name != 'Slides.mp4' and not has_audio:
                pipeline_desc += f' demux_{index}. ! queue name=qaparse ! aacparse ! queue name=amux ! mux. '
                has_audio = True
            index += 1
            x_offset = adjusted_width

        x264enc_options = 'speed-preset=faster'
        if self.options.preview:
            x264enc_options += ' tune=zerolatency'

        pipeline_desc += f'compositor name=vmix background=black {compositor_options} ! video/x-raw, format=(string)I420, width=(int){videomixer_width}, height=(int){videomixer_height}, framerate=(fraction){framerate}, colorimetry=(string)bt709 ! tee name=tee ! queue name=qvenc ! x264enc {x264enc_options} ! progressreport update-freq=1 silent=true ! queue name=qmux ! mp4mux name=mux ! filesink location={output_file.resolve()}'

        if self.options.preview:
            pipeline_desc += ' tee. ! queue name=qvsink ! autovideosink sync=false'

        print(pipeline_desc)
        self.pipeline = Gst.parse_launch(pipeline_desc)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_eos)
        bus.connect('message::error', self._on_error)
        bus.connect("message", self._on_message)

        layout_preset = self.get_layout_preset(layers_data)
        layout_file = folder / 'mediaserver_layout.json'
        with open(layout_file, 'w') as f:
            print(f'Wrote {layout_file}')
            json.dump(layout_preset, f, sort_keys=True, indent=4)

        GLib.idle_add(self.pipeline.set_state, Gst.State.PLAYING)
        self.start_time = time.time()

    def _on_error(self, bus, message):
        error, debug = message.parse_error()
        logging.error(f"{error}: {debug}")

    def _on_eos(self, bus, message):
        took = time.time() - self.start_time
        processing_speed = round(took / self.duration_s, 2)
        logging.info(f'Finished: {self.output_file}, processing speed: {processing_speed}x')
        self.mainloop.quit()

    def abort(self):
        logging.info(f'User interrupted, aborting and removing {self.output_file.name}')
        self.output_file.unlink()
        self.mainloop.quit()

    def _on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.ELEMENT:
            struct = message.get_structure()
            sname = struct.get_name()
            #source = message.src.get_name()
            if sname == 'progress':
                percent = int(struct.get_value('percent'))
                print(f'Processing: {percent}%', end='\r')

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
            logging.warning('File {media_file} contains no audio stream')
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        "-v",
        "--verbose",
        help="set verbosity to DEBUG",
        action="store_true"
    )

    parser.add_argument(
        "--preview",
        help="Enable realtime video preview",
        action="store_true"
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
        '--height',
        type=int,
        help='Rendering height',
        default=1440,
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

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
