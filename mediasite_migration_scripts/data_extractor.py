import os
import logging
import xml.dom.minidom as xml

from mediasite_migration_scripts.lib.utils import MediasiteSetup


class DataExtractor():

    def __init__(self, config_file=None):
        self.setup = MediasiteSetup(config_file)
        self.mediasite = self.setup.mediasite
        self.folders = self.mediasite.folder.get_all_folders()

    def order_presentations_by_folder(self, parent_id=None):
        """
        Create a list of all folders in association with their presentations

        returns:
            list ot items containing folder ID, parent folder ID, name, and
                list of his presentations containing ID, title and owner
        """
        logging.info('Gathering and ordering all presentations infos ')
        if not parent_id:
            parent_id = self.mediasite.folder.root_folder_id

        i = 0
        presentations_folders = []
        for folder in self.folders:
            if i < 1:
                print('Connecting...', end='\r')
            else:
                print('Requesting: ', f'[{i}/{len(self.folders)}] --', round(i / len(self.folders) * 100, 1), '%', end='\r', flush=True)

            path = self.find_folder_path(folder['id'], self.folders)
            if self.is_folder_to_add(path):
                logging.debug('Found folder : ' + path)
                presentations = self.mediasite.folder.get_folder_presentations(folder['id'])
                for presentation in presentations:
                    presentation['videos'] = self.get_videos_infos(presentation)
                    presentation['slides'] = self.get_slides_infos(presentation)
                presentations_folders.append({**folder,
                                              'path': path,
                                              'presentations': presentations})
            if i > 10:
                break
            i += 1
        return presentations_folders

    def is_folder_to_add(self, path):
        if self.setup.config['mediasite_folders_whitelist']:
            for fw in self.setup.config['mediasite_folders_whitelist']:
                if path.find(fw):
                    return True
            return False
        return True

    def get_videos_infos(self, presentation):
        logging.debug(f"Gathering video info for presentation : {presentation['id']}")

        videos_infos = []
        video = self.mediasite.presentation.get_presentation_content(presentation['id'], 'OnDemandContent')
        videos_infos = self.get_video_detail(video)
        return videos_infos

    def get_video_detail(self, video):
        video_list = []
        if video:
            for file in video['value']:
                content_server = self.mediasite.presentation.get_content_server(file['ContentServerId'])
                if 'DistributionUrl' in content_server:
                    # popping odata query params, we just need the route
                    splitted_url = content_server['DistributionUrl'].split('/')
                    splitted_url.pop()
                    storage_url = '/'.join(splitted_url)
                else:
                    storage_url = None
                file_name = file['FileNameWithExtension']
                video_url = os.path.join(storage_url, file_name) if file_name and storage_url else None

                file_infos = {
                    'url': video_url,
                    'format': file['ContentMimeType'],
                    'size_bytes': int(file['FileLength']),
                    'duration_s': int(file['Length']) * 1000,
                    'is_transcode_source': file['IsTranscodeSource'],
                    'encoding_infos': {}
                }
                if file_infos['format'] == 'video/mp4':
                    file_infos['encoding_infos'] = self.get_encoding_infos(file['ContentEncodingSettingsId'])

                stream = file['StreamType']
                in_list = False
                for v in video_list:
                    if stream == v.get('stream_type'):
                        in_list = True
                        v['files'].append(file_infos)
                if not in_list:
                    video_list.append({'stream_type': stream,
                                       'files': [file_infos]})
        return video_list

    def get_encoding_infos(self, settings_id):
        encoding_infos = {}
        encoding_settings = self.mediasite.presentation.get_content_encoding_settings(settings_id)
        if encoding_settings:
            serialized_settings = encoding_settings['SerializedSettings']
            settings_data = xml.parseString(serialized_settings).documentElement
            # Tag 'Settings' is a XML string to be parsed again...
            settings_node = settings_data.getElementsByTagName('Settings')[0]
            settings = xml.parseString(settings_node.firstChild.nodeValue)

            codecs_settings = settings.getElementsByTagName('StreamProfiles')[0]
            audio_codec = str()
            video_codec = str()
            for element in codecs_settings.childNodes:
                if element.getAttribute('i:type') == 'AudioEncoderProfile':
                    audio_codec = element.getElementsByTagName('FourCC')[0].firstChild.nodeValue
                elif element.getAttribute('i:type') == 'VideoEncoderProfile':
                    video_codec = element.getElementsByTagName('FourCC')[0].firstChild.nodeValue

            encoding_infos = {
                'video_codec': video_codec,
                'audio_codec': audio_codec,
                'width': settings.getElementsByTagName('PresentationAspectY')[0].firstChild.nodeValue,
                'height': settings.getElementsByTagName('PresentationAspectX')[0].firstChild.nodeValue,
            }
        return encoding_infos

    def get_slides_infos(self, presentation, details=False):
        logging.debug(f"Gathering slides infos for presentation: {presentation['id']}")

        slides_infos = {}
        option = 'SlideDetailsContent' if details else 'SlideContent'
        slides_result = self.mediasite.presentation.get_presentation_content(presentation['id'], option)
        if slides_result:
            for slides in slides_result['value']:
                content_server_id = slides['ContentServerId']
                content_server = self.mediasite.presentation.get_content_server(content_server_id, slide=True)
                content_server_url = content_server['Url']
                presentation_id = slides['ParentResourceId']

                slides_base_url = f"{content_server_url}/{content_server_id}/Presentation/{presentation_id}"
                slides_urls = []
                slides_files_names = slides['FileNameWithExtension']
                for i in range(int(slides['Length'])):
                    # Transform string format (from C# to Python syntax) -> slides_{0:04}.jpg
                    file_name = slides_files_names.replace('{0:D4}', f'{i+1:04}')
                    link = f'{slides_base_url}/{file_name}'
                    slides_urls.append(link)

                slides_infos['urls'] = slides_urls
                slides_infos['details'] = slides['SlideDetails'] if details else None

        return slides_infos

    def find_folder_path(self, folder_id, folders, path=''):
        """
        Provide the folder's path delimited by '/'
        by parsing the folders list structure

        params:
            folder_id: id of the folder for which we are looking for the path
        returns:
            string of the folder's path
        """

        for folder in folders:
            if folder['id'] == folder_id:
                path += self.find_folder_path(folder['parent_id'], folders, path)
                path += '/' + folder['name']
                return path
        return ''
