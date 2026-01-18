import logging
import sys
import time

from rich.logging import RichHandler
from rich.progress import track
from rich.prompt import Prompt
from serializd import SerializdClient
from serializd.exceptions import EmptySeasonError, LoginError

from trakt_to_serializd.credentials import CredentialHelper
from trakt_to_serializd.exceptions import TraktError
from trakt_to_serializd.trakt import TraktAPI


class Migrator:
    def __init__(self, use_credentials_store: bool = True, with_dates: bool = False):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO,
            format='%(message)s',
            datefmt='[%X]',
            handlers=[RichHandler(rich_tracebacks=True)]
        )
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)

        self.use_credentials_store = use_credentials_store
        self.with_dates = with_dates
        self.trakt_auth = CredentialHelper('trakt')
        self.serializd_auth = CredentialHelper('serializd')
        if use_credentials_store:
            self.trakt_auth.load()
            self.serializd_auth.load()

        self.trakt = TraktAPI()
        self.serializd = SerializdClient()

    def main(self):
        try:
            self.trakt_login()
        except TraktError:
            self.logger.error('Failed to log in to Trakt, quitting')
            sys.exit(1)

        try:
            self.serializd_login()
        except LoginError:
            self.logger.error('Failed to log in to Serializd, quitting')
            sys.exit(1)

        self.logger.debug('Fetching user info from Trakt')
        username = self.trakt.get_user_info()['user']['username']
        self.logger.info('Fetching watched show data from Trakt')
        watched_data = self.trakt.get_watched_shows(username)

        if self.with_dates:
            self._migrate_with_dates(watched_data)
        else:
            self._migrate_without_dates(watched_data)

    def _migrate_without_dates(self, watched_data: list) -> None:
        """Original migration method - logs episodes without dates."""
        for watched_show in track(
            watched_data,
            description=f'Updating {len(watched_data)} shows...',
            total=len(watched_data)
        ):
            complete_seasons = []
            for watched_season in watched_show['seasons']:
                self.logger.info(
                    'Updating season %d of show "%s"',
                    watched_season['number'],
                    watched_show['show']['title']
                )
                self.logger.debug(
                    'Fetching season info for season %d',
                    watched_season['number']
                )
                mark_full_season = False
                try:
                    season_info = self.serializd.get_season(
                        show_id=watched_show['show']['ids']['tmdb'],
                        season_number=watched_season['number']
                    )
                    mark_full_season = len(season_info.episodes) == len(watched_season['episodes'])
                except EmptySeasonError:
                    self.logger.warning(
                        'Serializd returned no episodes, marking entire season as watched'
                    )
                    mark_full_season = True

                if mark_full_season:
                    complete_seasons.append(season_info.seasonId)
                    continue

                self.serializd.log_episodes(
                    show_id=watched_show['show']['ids']['tmdb'],
                    season_id=season_info.seasonId,
                    episode_numbers=[ep['number'] for ep in watched_season['episodes']]
                )

            if complete_seasons:
                self.serializd.log_seasons(
                    show_id=watched_show['show']['ids']['tmdb'],
                    season_ids=complete_seasons
                )

    def _migrate_with_dates(self, watched_data: list) -> None:
        """Migration with diary dates - logs each episode individually with watch date."""
        total_episodes = sum(
            len(ep)
            for show in watched_data
            for season in show['seasons']
            for ep in [season['episodes']]
        )
        self.logger.info(
            'Migrating %d episodes from %d shows with watch dates',
            total_episodes, len(watched_data)
        )

        episode_count = 0
        for watched_show in watched_data:
            show_title = watched_show['show']['title']
            show_id = watched_show['show']['ids']['tmdb']

            for watched_season in watched_show['seasons']:
                season_number = watched_season['number']
                self.logger.info(
                    'Processing season %d of "%s"',
                    season_number, show_title
                )

                try:
                    season_info = self.serializd.get_season(
                        show_id=show_id,
                        season_number=season_number
                    )
                except EmptySeasonError:
                    self.logger.warning(
                        'Serializd returned no episodes for season %d of "%s", skipping',
                        season_number, show_title
                    )
                    continue

                for episode in track(
                    watched_season['episodes'],
                    description=f'  S{season_number:02d}...',
                    total=len(watched_season['episodes'])
                ):
                    episode_number = episode['number']
                    # Trakt provides last_watched_at in ISO 8601 format
                    watched_at = episode.get('last_watched_at')

                    if not watched_at:
                        self.logger.warning(
                            'No watch date for S%02dE%02d of "%s", using current time',
                            season_number, episode_number, show_title
                        )
                        from datetime import datetime, timezone
                        watched_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

                    self.serializd.log_episode_to_diary(
                        show_id=show_id,
                        season_id=season_info.seasonId,
                        episode_number=episode_number,
                        watched_at=watched_at
                    )
                    episode_count += 1

        self.logger.info('Successfully migrated %d episodes with watch dates', episode_count)

    def trakt_login(self):
        if self.use_credentials_store:
            self.logger.debug('Loading Trakt credentials from file')
            self.trakt_auth.load()

        if not self.trakt_auth:
            self.logger.debug('Logging in to Trakt')
            self.trakt_auth.update(self.trakt.login())

        if int(time.time()) >= self.trakt_auth['created_at'] + self.trakt_auth['expires_in']:
            self.logger.debug('Refreshing saved Trakt tokens')
            self.trakt_auth.update(self.trakt.refresh_token(self.trakt_auth['refresh_token']))

        self.trakt.load_token(self.trakt_auth['access_token'])

        if self.use_credentials_store and self.trakt_auth.modified:
            self.logger.debug('Saving Trakt credentials to file')
            self.trakt_auth.save()

    def serializd_login(self):
        if self.use_credentials_store:
            self.logger.debug('Loading Serializd credentials from file')
            self.serializd_auth.load()

        if token := self.serializd_auth.get('token'):
            self.logger.debug('Checking Serializd token')
            if self.serializd.check_token(token).isValid:
                self.serializd.load_token(token, check=False)

        if not self.serializd.access_token:
            self.logger.debug('Prompting user for Serializd credentials')
            email = Prompt.ask('Enter Serializd email')
            password = Prompt.ask('Enter Serializd password (will not be echoed)', password=True)

            self.logger.debug('Logging in to Serializd')
            self.serializd.login(email=email, password=password)
            self.serializd_auth['token'] = self.serializd.access_token

        if self.use_credentials_store and self.serializd_auth.modified:
            self.logger.debug('Saving Serializd credentials to file')
            self.serializd_auth.save()
