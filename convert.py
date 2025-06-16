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
import psutil
from pathlib import Path
from multiprocessing import Pool, Manager
import typer

from rich.console import Console
import petl as etl

from storage import Storage
from file import File
from util import (remove_file, start_uno_server, pwconv_path, make_filelist,
                  filelist_to_storage)
from config import cfg, converters

console = Console()
os.chdir(pwconv_path)
app = typer.Typer(rich_markup_mode="markdown")


# handle raised errors
def handle_error(error):
    print(error, flush=True)


def limit_cpu():
    "is called at every process start"
    p = psutil.Process(os.getpid())
    # set to lowest priority
    p.nice(19)


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
        default=False,
        help="Add or change extension on source files based on mimetype"
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
    ts = datetime.datetime.now()

    if os.path.isdir('/tmp/convert'):
        shutil.rmtree('/tmp/convert')

    if not db:
        db = dest.rstrip('/') + '.db'

    with Storage(db) as store:
        first_run = store.get_row_count() == 0
        if first_run:
            make_filelist(source)

        if first_run:
            filelist_to_storage(source, store)
            status = 'new'

        if filecheck:
            res = check_files(source, store)
            if res == 'cancelled':
                return False

        conds, params = store.get_conds(mime=mime, puid=puid, status=status,
                                        reconvert=reconvert, timestamp=ts,
                                        ext=ext, retry=retry)

        count_remains = store.get_row_count(conds, params)

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

        console.print("Converting files..", style="bold cyan")

        table = store.get_rows(conds, params)
        total_count = len(table) - 1

        manager = Manager()
        q = manager.Queue()
        pool = Pool(None, limit_cpu)
        jobs = []
        t0 = time.time()
        count = {
            'finished': manager.Value('i', 0),
            'total': manager.Value('i', total_count),
            'failed': manager.Value('i', 0),
            'skipped': manager.Value('i', 0)
        }

        # put listener to work first
        pool.apply_async(listener, (q, db))

        n = 0
        for row in etl.dicts(table):
            n += 1
            file = File(row, identify_only)
            file.set_progress(f"{n}/{total_count}")

            if reconvert and row['source_id'] is None:
                # Remove any copied original files
                remove_file(Path(dest, row['path']))

                rows = store.get_children(row['id'])
                for file_row in rows:
                    remove_file(Path(dest, file_row[1]))
                q.put(row['id'])

            args = (source, dest, orig_ext, debug, set_source_ext,
                    identify_only, keep_originals, q, count)
            job = pool.apply_async(file.convert, args=args,
                                   error_callback=handle_error)
            jobs.append(job)

        # collect results from the workers through the pool result queue
        for job in jobs:
            job.get()

        q.put('kill')

        pool.close()
        pool.join()

        duration = str(datetime.timedelta(seconds=round(time.time() - t0)))
        if identify_only:
            console.print('\nIdentification finished in ' + duration)
        else:
            console.print('\nConversion finished in ' + duration)
        conds, params = store.get_conds(finished=True, status='accepted',
                                        timestamp=ts)
        count_accepted = store.get_row_count(conds, params)
        if count_accepted:
            console.print(f"{count_accepted} files accepted",
                          style="bold green")
        conds, params = store.get_conds(finished=True, status='skipped',
                                        timestamp=ts)
        count_skipped = store.get_row_count(conds, params)
        if count_skipped:
            console.print(f"{count_skipped} files skipped",
                          style="bold orange1")
        conds, params = store.get_conds(finished=True, status='removed',
                                        timestamp=ts)
        count_removed = store.get_row_count(conds, params)
        if count_removed:
            console.print(f"{count_removed} files removed",
                          style="bold orange1")

        conds, params = store.get_conds(finished=True, status='failed',
                                        timestamp=ts)
        count_failed = store.get_row_count(conds, params)
        if count_failed:
            console.print(f"{count_failed} files failed",
                          style="bold red")
        console.print(f"See database {db} for details")


def listener(q, db):
    '''listens for messages on the q, writes to database '''

    while 1:
        file = q.get()
        if type(file) is int:
            with Storage(db) as store:
                store.delete_children(file)
        elif file == 'kill':
            break
        else:
            file.log(db)


def check_files(source_dir, store):
    """ Check if files in database match files on disk """

    files_count = sum([len(files) for r, d, files in os.walk(source_dir)])
    conds, params = store.get_conds(original=True, finished=True)
    total_row_count = store.get_row_count(conds, params)
    count_diff = files_count - total_row_count

    if files_count != total_row_count:
        console.print(f"Row count: {str(total_row_count)}", style="red")
        console.print(f"File count: {str(files_count)}", style="red")
        db_files = []
        table = store.get_all_rows('')
        for row in etl.dicts(table):
            db_files.append(row['path'])
        if count_diff < 10:
            print("The following files don't exist in database:")
        extra_files = []
        for r, d, files in os.walk(source_dir):
            for file_ in files:
                path = Path(r, file_)
                commonprefix = os.path.commonprefix([source_dir, path])
                relpath = os.path.relpath(path, commonprefix)
                if relpath not in db_files:
                    extra_files.append({'path': relpath, 'status': 'new'})
                    if count_diff < 10:
                        print('- ' + relpath)

        answ = input("Files listed in database doesn't match "
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
