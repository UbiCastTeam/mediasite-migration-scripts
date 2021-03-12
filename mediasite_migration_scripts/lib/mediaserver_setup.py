from mediasite_migration_scripts.ms_client.client import MediaServerClient
from decouple import config


class MediaServerSetup():
    def __init__(self, log_level='INFO'):
        self.log_level = log_level
        self.config = self.setup()
        self.ms_client = MediaServerClient(local_conf=self.config, setup_logging=False)

    def setup(self):
        config_data = {"API_KEY": config('MEDIASERVER_API_KEY'),
                       "CLIENT_ID": "mediasite-migration-client",
                       "PROXIES": {"http": "",
                                   "https": ""},
                       "SERVER_URL": "https://beta.ubicast.net",
                       "UPLOAD_CHUNK_SIZE": 5242880,
                       "VERIFY_SSL": False,
                       "LOG_LEVEL": self.log_level}
        return config_data
