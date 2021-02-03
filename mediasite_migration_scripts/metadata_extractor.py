import os
import logging
from lib.utils import MediasiteSetup


class MetadataExtractor():

    def __init__(self, config_file=None):
        self.setup = MediasiteSetup(config_file)
        self.mediasite = self.setup.mediasite

    def order_presentations_by_folder(self, folders, parent_id=None):
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
        for folder in folders:
            print('Requesting: ', round(i / len(folders) * 100, 1), '%', end='\r', flush=True)

            path = self.find_folder_path(folder['id'], folders)
            if self.is_folder_to_add(path):
                logging.debug('Found folder : ' + path)
                presentations = self.mediasite.folder.get_folder_presentations(folder['id'])
                for presentation in presentations:
                    presentation['videos'] = self.get_videos_infos(presentation)
                    presentation['slides'] = self.get_slides_infos(presentation)
                presentations_folders.append({**folder,
                                              'path': path,
                                              'presentations': presentations})
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
                file_infos = {'format': file['ContentMimeType'], 'url': video_url}
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

    def get_all_folders(self):
        return self.mediasite.folder.get_all_folders()

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

    def find_presentations_not_in_folder(self, presentations, presentations_folders):
        presentations_not_in_folders = list()
        for prez in presentations:
            found = False
            i = 0
            while not found and i < len(presentations_folders):
                if prez['id'] == presentations_folders[i]['id']:
                    found = True
                i += 1
            if not found:
                presentations_not_in_folders.append(prez)

        return presentations_not_in_folders
