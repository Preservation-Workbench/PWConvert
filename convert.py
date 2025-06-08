# Copyright(C) 2022 Morten Eek

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations
import os
import shutil
import datetime
import time
import textwrap
from pathlib import Path
from multiprocessing import Pool, Manager
import typer

from rich.console import Console
import petl as etl

from storage import Storage
from file import File
from util import make_filelist, remove_file, start_uno_server
from config import cfg, converters

console = Console()
pwconv_path = Path(__file__).parent.resolve()
os.chdir(pwconv_path)
app = typer.Typer(rich_markup_mode="markdown")


def remove_fields(table, *args):
    """Remove fields from petl table"""
    for field in args:
        if field in etl.fieldnames(table):
            table = etl.cutout(table, field)
    return table


def add_fields(table, *args):
    """Add fields to petl table"""
    for field in args:
        if field not in etl.fieldnames(table):
            table = etl.addfield(table, field, None)
    return table


# handle raised errors
def handle_error(error):
    print(error, flush=True)


@app.command()
def convert(
    source: str,
    dest: str = typer.Option(default=None, help="Path to destination folder"),
    orig_ext: bool = typer.Option(default=cfg['keep-original-ext'],
                                  help="Keep original extension"),
    debug: bool = typer.Option(default=cfg['debug'], help="Turn on debug"),
    mime: str = typer.Option(default=None, help="Filter on mime-type"),
    puid: str = typer.Option(default=None,
                             help="Filter on PRONOM Unique Identifier"),
    ext: str = typer.Option(default=None, help="Filter on file extension"),
    status: str = typer.Option(
        default=None,
        help="Filter on conversion status"
    ),
    db: str = typer.Option(default=None, help="Name of MySQL base"),
    reconvert: bool = typer.Option(default=False, help="Reconvert files"),
    identify_only: bool = typer.Option(
        default=False, help="Don't convert, only identify files"
    ),
    filecheck: bool = typer.Option(
        default=False, help="Check if files in source match files in database"
    ),
    set_source_ext: bool = typer.Option(
        default=False, help="Check if files in source match files in database"
    ),
    from_path: str = typer.Option(
        default=None,
        help="Convert files where path ≥ this value"
    ),
    to_path: str = typer.Option(
        default=None,
        help="Convert files where path < this value"
    ),
    multi: bool = typer.Option(
        default=False,
        help="Use multiprocessing to convert each subfolder in its own process"
    ),
    retry: bool = typer.Option(
        default=False,
        help="Try to convert files where conversion previously failed"
    ),
    keep_originals: bool = typer.Option(
        default=cfg['keep-original-files'],
        help="Keep original files"
    )
) -> None:
    """
    Convert all files in SOURCE folder

    If `--dest` is not set, then the conversion is done inside the `source`
    folder (`dest=source`).
    If `--db` is not set, it uses a SQLite base with path like `dest` and
    .db extension.
    `--status` can be one of: accepted, converted, deleted, failed, protected,
    skipped, timeout, new.
    """

    if dest is None:
        dest = source

    Path(dest).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now()

    if os.path.isdir('/tmp/convert'):
        shutil.rmtree('/tmp/convert')

    if not db:
        db = dest.rstrip('/') + '.db'

    with Storage(db) as store:
        filelist_path = dest.rstrip('/') + '-filelist.txt'
        is_new_batch = os.path.isfile(filelist_path)
        first_run = store.get_row_count() == 0
        if first_run:
            make_filelist(source, filelist_path)

        if first_run or is_new_batch:
            write_id_file_to_storage(filelist_path, source, store, '')
            status = 'new'

        conds, params = store.get_conds(mime=mime, puid=puid, status=status,
                                        reconvert=(reconvert or identify_only),
                                        from_path=from_path, to_path=to_path,
                                        timestamp=timestamp, ext=ext, retry=retry)

        count_remains = store.get_row_count(conds, params)
        m = Manager()
        count = {
            'remains': m.Value('i', count_remains),
            'finished': m.Value('i', 0)
        }

        start_uno_server()
        if identify_only:
            msg = f"Identifies {count_remains} files. "
        else:
            msg = f"Converts {count_remains} files. "
        if dest == source and keep_originals is False and not identify_only:
            msg += ("You have chosen to convert files within source folder "
                    "and not keep original files. This deletes original files "
                    "that are converted. Consider backing up folder before "
                    "proceeding to safeguard agains data loss.")
        elif dest == source and not identify_only:
            msg += "Files marked with `kept: false` will be deleted. "

        msg += "Continue? [y/n] "

        if input(textwrap.dedent(msg)) != 'y':
            return False

        warning = ""
        for converter in converters.values():
            if converter.get('command') and 'unoconv2x' in converter['command']:
                warning += "unoconv2x is deprecated and will be removed in a "
                warning += "coming update. Use unoconvert instead. "
                warning += "Continue? [y/n]"
        if warning:
            if input(warning) != 'y':
                return False

        if filecheck:
            res = check_files(source, store)
            if res == 'cancelled':
                return False

        console.print("Converting files..", style="bold cyan")

        pool = Pool()
        t0 = time.time()

        if multi:
            dirs = store.get_subfolders(conds, params)
            for dir in dirs:
                dir = Path(dir).name
                args = (source, dest, debug, orig_ext, db, dir, True,
                        mime, puid, ext, status, reconvert, retry,
                        identify_only, filecheck, timestamp, set_source_ext,
                        from_path, to_path, count, keep_originals)
                pool.apply_async(convert_folder, args=args, error_callback=handle_error)
        else:
            convert_folder(source, dest, debug, orig_ext, db, '', True,
                           mime, puid, ext, status, reconvert, retry,
                           identify_only, filecheck, timestamp, set_source_ext,
                           from_path, to_path, count, keep_originals)

        pool.close()
        pool.join()

        duration = str(datetime.timedelta(seconds=round(time.time() - t0)))
        if identify_only:
            console.print('\nIdentification finished in ' + duration)
        else:
            console.print('\nConversion finished in ' + duration)
        conds, params = store.get_conds(finished=True, status='accepted',
                                        timestamp=timestamp)
        count_accepted = store.get_row_count(conds, params)
        if count_accepted:
            console.print(f"{count_accepted} files accepted",
                          style="bold green")
        conds, params = store.get_conds(finished=True, status='skipped',
                                        timestamp=timestamp)
        count_skipped = store.get_row_count(conds, params)
        if count_skipped:
            console.print(f"{count_skipped} files skipped",
                          style="bold orange1")
        conds, params = store.get_conds(finished=True, status='removed',
                                        timestamp=timestamp)
        count_removed = store.get_row_count(conds, params)
        if count_removed:
            console.print(f"{count_removed} files removed",
                          style="bold orange1")

        conds, params = store.get_conds(finished=True, status='failed',
                                        timestamp=timestamp)
        count_failed = store.get_row_count(conds, params)
        if count_failed:
            console.print(f"{count_failed} files failed",
                          style="bold red")
        console.print(f"See database {db} for details")


def convert_folder(
    source_dir: str,
    dest_dir: str,
    debug: bool,
    orig_ext: bool,
    db: str,
    subpath: str,
    multi: bool,
    mime: str,
    puid: str,
    ext: str,
    status: str,
    reconvert: bool,
    retry: bool,
    identify_only: bool,
    filecheck: bool,
    timestamp: datetime.datetime,
    set_source_ext: bool,
    from_path: str,
    to_path: str,
    count: dict,
    keep_originals: bool
) -> tuple[str, str]:
    """Convert all files in folder"""

    with Storage(db) as store:
        if reconvert:
            conds, params = store.get_conds(
                mime=mime, puid=puid, status=status, subpath=subpath,
                reconvert=(reconvert or identify_only), ext=ext,
                from_path=from_path, to_path=to_path, timestamp=timestamp,
                retry=retry
            )
            store.update_status(conds, params, 'new')

        else:
            conds, params = store.get_conds(
                mime=mime, puid=puid, status=status, subpath=subpath, ext=ext,
                from_path=from_path, to_path=to_path, timestamp=timestamp,
                reconvert=identify_only, retry=retry
            )
        table = store.get_rows(conds, params, limit=1)

        # loop through all files and run conversion:
        # unpacked files are added to and converted in main loop
        table.row_count = 0
        i = 0
        percent = 0
        while tbl := etl.dicts(table):
            i += 1
            count['finished'].value += 1
            row = tbl[0]
            if row['source_id'] is None:
                table.row_count += 1

            n = count['remains'].value
            new_percent = round((1 - n/(n + count['finished'].value)) * 100)
            percent = percent if percent > new_percent else new_percent

            if reconvert and row['source_id'] is None:
                # Remove any copied original files
                remove_file(Path(dest_dir, row['path']))

                rows = store.get_descendants(row['id'])
                for file_row in rows:
                    remove_file(Path(dest_dir, file_row[1]))

                store.delete_descendants(row['id'])

            print(end='\x1b[2K')  # clear line
            print(f"\r{percent}% | "
                  f"{row['path'][0:100]}", end=" ", flush=True)

            unidentify = reconvert or identify_only
            src_file = File(row, pwconv_path, unidentify)
            norm = src_file.convert(source_dir, dest_dir, orig_ext,
                                    debug, set_source_ext, identify_only,
                                    keep_originals)

            if norm is None:  # --identify-only
                pass
            elif norm is False:  # conversion failed
                if src_file.status != 'accepted':
                    console.print('  ' + src_file.status, style="bold red")
            elif type(norm) is str:
                dest_path = Path(dest_dir, norm)
                unpacked_count = sum([len(files) for r, d, files
                                      in os.walk(dest_path)])
                console.print(f'Unpacked {unpacked_count} files',
                              style="bold cyan", end=' ')

                # Write new files to database
                filelist_dir = os.path.join(dest_dir, norm)
                filelist_path = filelist_dir.rstrip('/') + '-filelist.txt'
                make_filelist(os.path.join(dest_dir, norm),
                              filelist_path)
                n = write_id_file_to_storage(filelist_path, dest_dir, store,
                                             norm, source_id=src_file.id)

                count['remains'].value += n

            else:
                if norm.status == 'failed' and norm.kept is True:
                    console.print('converted file kept', style="bold orange1")
                if norm.status != 'new':
                    norm.status_ts = datetime.datetime.now()
                store.add_row(norm.__dict__)

            src_file.status_ts = datetime.datetime.now()
            store.update_row(src_file.__dict__)
            count['remains'].value -= 1


def write_id_file_to_storage(tsv_source_path: str, source_dir: str,
                             store: Storage, unpacked_path: str,
                             source_id: int = None) -> int:

    table = etl.fromtext(tsv_source_path, header=['filename'], strip="\n")
    table = etl.rename(
        table,
        {
            'filename': 'path',
            'filesize': 'size',
            'Content_Type': 'mime',
            'Version': 'version',
        },
        strict=False,
    )
    table = etl.select(table, lambda rec: rec.path != "")
    table = add_fields(table, 'mime', 'version', 'status', 'puid', 'source_id')
    # Remove Siegfried generated columns
    table = remove_fields(table, "namespace", "basis", "warning")

    table = etl.update(table, 'status', "new")
    table = etl.update(table, 'source_id', source_id)

    # Treat csv (detected from extension only) as plain text:
    table = etl.convert(table, "mime", lambda v,
                        _row: "text/plain" if _row.id == "x-fmt/18" else v,
                        pass_row=True)

    # Update for missing mime types where id is known:
    table = etl.convert(table, "mime", lambda v,
                        _row: "application/xml" if _row.id == "fmt/979" else v,
                        pass_row=True)

    if unpacked_path:
        table = etl.convert(table, 'path',
                            lambda v: os.path.join(unpacked_path, v))

    store.append_rows(table)
    row_count = etl.nrows(table)
    remove_file(tsv_source_path)
    return row_count


def check_files(source_dir, store):
    """ Check if files in database match files on disk """

    files_count = sum([len(files) for r, d, files in os.walk(source_dir)])
    conds, params = store.get_conds(original=True)
    total_row_count = store.get_row_count(conds, params)

    if files_count != total_row_count:
        console.print(f"Row count: {str(total_row_count)}", style="red")
        console.print(f"File count: {str(files_count)}", style="red")
        db_files = []
        table = store.get_all_rows('')
        for row in etl.dicts(table):
            db_files.append(row['path'])
        print("Following files don't exist in database:")
        extra_files = []
        for r, d, files in os.walk(source_dir):
            for file_ in files:
                path = Path(r, file_)
                commonprefix = os.path.commonprefix([source_dir, path])
                relpath = os.path.relpath(path, commonprefix)
                if relpath not in db_files:
                    extra_files.append({'path': relpath, 'status': 'new'})
                    print('- ' + relpath)

        answ = input(f"Files listed in database doesn't match "
                     "files on disk. Continue? [y]es, [n]o, [a]dd, [d]elete ")
        if answ == 'd':
            for file_ in extra_files:
                Path(source_dir, file_['source_path']).unlink()
            return 'deleted'
        elif answ == 'a':
            table = etl.fromdicts(extra_files)
            store.append_rows(table)
            return 'added'
        elif answ != 'y':
            return 'cancelled'


if __name__ == "__main__":
    app()
