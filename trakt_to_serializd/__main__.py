import logging

import click

from trakt_to_serializd.credentials import CredentialHelper
from trakt_to_serializd.migrator import Migrator, MigrationCache


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option('--no-credentials-store', is_flag=True, help='Disables storage of user credentials')
@click.option('--debug', is_flag=True, help='Enables debug logging')
@click.option(
    '--with-dates',
    is_flag=True,
    help='Import watch dates to Serializd diary (logs each episode individually with original watch date)'
)
def migrate(no_credentials_store: bool, debug: bool, with_dates: bool) -> None:
    """Runs Trakt to Serializd migrator"""
    migrator = Migrator(not no_credentials_store, with_dates=with_dates)
    if debug:
        migrator.logger.setLevel(logging.DEBUG)

    migrator.main()


@cli.command()
def populate_cache() -> None:
    """Populates migration cache from existing Serializd diary entries.
    
    Use this before running migrate --with-dates if you've already migrated
    some episodes, to prevent duplicate diary entries.
    """
    from rich.console import Console
    from serializd import SerializdClient
    from serializd.exceptions import LoginError
    from rich.prompt import Prompt

    console = Console()
    
    # Initialize and login to Serializd
    serializd_auth = CredentialHelper('serializd')
    serializd_auth.load()
    serializd = SerializdClient()
    
    if token := serializd_auth.get('token'):
        result = serializd.check_token(token)
        if result.isValid:
            serializd.load_token(token, check=False)
            username = result.username
        else:
            token = None
    
    if not serializd.access_token:
        console.print('[yellow]Please log in to Serializd[/yellow]')
        email = Prompt.ask('Enter Serializd email')
        password = Prompt.ask('Enter Serializd password (will not be echoed)', password=True)
        
        try:
            login_result = serializd.login(email=email, password=password)
            username = login_result.username
            serializd_auth['token'] = serializd.access_token
            serializd_auth.save()
        except LoginError as e:
            console.print(f'[red]Failed to log in: {e}[/red]')
            return
    
    console.print(f'[green]Logged in as {username}[/green]')
    console.print('[blue]Fetching all diary entries (this may take a while)...[/blue]')
    
    # Fetch all diary entries
    try:
        entries = serializd.get_all_diary_entries(username)
    except Exception as e:
        console.print(f'[red]Failed to fetch diary: {e}[/red]')
        return
    
    console.print(f'[green]Found {len(entries)} diary entries[/green]')
    
    # Populate cache
    cache = MigrationCache()
    existing = cache.count()
    added = cache.populate_from_diary(entries)
    cache.save()
    
    console.print(f'[green]Cache updated: {added} new entries added[/green]')
    console.print(f'[blue]Total cache size: {cache.count()} episodes[/blue]')
    if existing > 0:
        console.print(f'[dim](Previously had {existing} entries)[/dim]')


@cli.command()
def clean() -> None:
    """Removes saved Trakt/Serializd credentials"""
    for service in ('trakt', 'serializd'):
        CredentialHelper(service).remove()

    CredentialHelper.remove_folder()
    print('Credential files have been removed.')


if __name__ == '__main__':
    cli()
