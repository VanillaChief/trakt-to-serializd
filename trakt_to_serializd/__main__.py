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
@click.option('--dry-run', is_flag=True, help='Only show what would be deleted, do not actually delete')
def cleanup_duplicates(dry_run: bool) -> None:
    """Finds and removes duplicate diary entries in Serializd.
    
    Identifies entries where the same episode was logged multiple times
    on the same date, keeping only the oldest entry and removing the rest.
    """
    from collections import defaultdict
    from rich.console import Console
    from rich.progress import track
    from serializd import SerializdClient
    from serializd.exceptions import LoginError
    from rich.prompt import Prompt, Confirm

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
    console.print('[blue]Fetching all diary entries...[/blue]')
    
    # Fetch all diary entries
    try:
        entries = serializd.get_all_diary_entries(username)
    except Exception as e:
        console.print(f'[red]Failed to fetch diary: {e}[/red]')
        return
    
    console.print(f'[green]Found {len(entries)} diary entries[/green]')
    
    # Group by (show, season, episode, date)
    groups = defaultdict(list)
    for e in entries:
        backdate = e.get('backdate') or e.get('createdAt', '')
        date_part = backdate[:10] if backdate else 'unknown'
        key = (e.get('showId'), e.get('seasonId'), e.get('episodeNumber'), date_part)
        groups[key].append(e)
    
    # Find duplicates
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    
    if not duplicates:
        console.print('[green]No duplicate entries found![/green]')
        return
    
    # Get IDs to delete (keep oldest by dateAdded)
    entries_to_delete = []
    for key, entries_list in duplicates.items():
        sorted_entries = sorted(entries_list, key=lambda x: x.get('dateAdded', ''))
        # Keep the oldest, delete the rest
        for e in sorted_entries[1:]:
            entries_to_delete.append(e)
    
    console.print(f'[yellow]Found {len(duplicates)} duplicate groups[/yellow]')
    console.print(f'[yellow]Total entries to delete: {len(entries_to_delete)}[/yellow]')
    
    # Show sample of what will be deleted
    console.print('\n[bold]Sample of entries to delete:[/bold]')
    for e in entries_to_delete[:10]:
        console.print(
            f"  - {e.get('showName', 'Unknown')} S{e.get('seasonId')} E{e.get('episodeNumber')} "
            f"(added {e.get('dateAdded', 'unknown')[:10]})"
        )
    if len(entries_to_delete) > 10:
        console.print(f'  ... and {len(entries_to_delete) - 10} more')
    
    if dry_run:
        console.print('\n[yellow]Dry run - no entries were deleted[/yellow]')
        return
    
    # Confirm before deletion
    if not Confirm.ask(f'\nDelete {len(entries_to_delete)} duplicate entries?'):
        console.print('[yellow]Cancelled[/yellow]')
        return
    
    # Delete duplicates
    deleted = 0
    failed = 0
    for entry in track(entries_to_delete, description='Deleting duplicates...'):
        try:
            if serializd.delete_diary_entry(entry['id']):
                deleted += 1
            else:
                failed += 1
        except Exception as e:
            console.print(f'[red]Failed to delete {entry["id"]}: {e}[/red]')
            failed += 1
    
    console.print(f'\n[green]Successfully deleted {deleted} duplicate entries[/green]')
    if failed > 0:
        console.print(f'[red]Failed to delete {failed} entries[/red]')


@cli.command()
def clean() -> None:
    """Removes saved Trakt/Serializd credentials"""
    for service in ('trakt', 'serializd'):
        CredentialHelper(service).remove()

    CredentialHelper.remove_folder()
    print('Credential files have been removed.')


if __name__ == '__main__':
    cli()
