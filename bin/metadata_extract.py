from argparse import RawTextHelpFormatter
import argparse
from mediasite_migration_scripts.metadata_extractor import MetadataExtractor

if __name__ == '__main__':

    # --------------------------- Setup
    # args
    def usage(message=''):
        return 'This script is used to extract metadata from mediasite platform'

    def manage_opts():
        parser = argparse.ArgumentParser(description=usage(), formatter_class=RawTextHelpFormatter)
        parser.add_argument('-i', '--info', action='store_true',
                            dest='info', default=False,
                            help='print more status messages to stdout.')
        parser.add_argument('-inv', '--investigate', action='store_true',
                            dest='investigate', default=False,
                            help='check what presentations have not been acounted')
        parser.add_argument('-v', '--verbose', action='store_true',
                            dest='verbose', default=False,
                            help='print all status messages to stdout.')
        parser.add_argument('-d', '--dry-run', action='store_true',
                            dest='dryrun', default=False,
                            help='not really import medias.')

        return parser.parse_args()

    options = manage_opts()

    #--------------------------- Script

    extractor = Metad
    # Listing folders with their presentations
    try:
        with open('data.json') as f:
            data = json.load(f)
            logging.info('data.json already found, not fetching catalog data')
    except Exception as e:
        logging.debug(e)
        folders = mediasite.folder.get_all_folders()
        with open('data.json', 'w') as f:
            data = order_presentations_by_folder(folders)
            json.dump(data, f)

    if options.investigate:
        # Listing all presentations
        try:
            with open('presentations.json') as f:
                presentations = json.load(f)
        except Exception as e:
            logging.debug(e)
            with open('presentations.json', 'w') as f:
                presentations = mediasite.presentation.get_all_presentations()
                json.dump(presentations, f)

        # Listing presentations that are not referenced in folders
        presentations_not_in_folders = list()
        try:
            with open('presentations_not_in_folders.json') as f:
                presentations_not_in_folders = json.load(f)
        except Exception as e:
            logging.debug(e)
            with open('presentations_not_in_folders.json', 'w') as f:
                presentations_in_folders = []
                for folder in data:
                    for prez in folder['presentations']:
                        presentations_in_folders.append(prez)

                presentations_not_in_folders = find_presentations_not_in_folder(presentations, presentations_in_folders)
                json.dump(presentations_not_in_folders, f)

        print(f'Presentations not accounted : {len(presentations_not_in_folders)}. Check on presentations_not_in_folder.json for more infos.')
