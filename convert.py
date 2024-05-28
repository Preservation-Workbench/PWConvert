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
from pathlib import Path
import mimetypes
from multiprocessing import Pool, Manager
import typer

from rich.console import Console
import petl as etl

from storage import Storage
from file import File
from util import make_filelist, remove_file
from config import cfg

console = Console()
pwconv_path = Path(__file__).parent.resolve()
os.chdir(pwconv_path)


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


def convert(
    source: str,
    dest: str,
    orig_ext: bool = cfg['keep-original-ext'],
    debug: bool = cfg['debug'],
    mime: str = None,
    puid: str = None,
    status: str = None,
    db: str = None,
    reconvert: bool = False,
    identify_only: bool = False,
    filecheck: bool = False,
    set_source_ext: bool = False,
    from_path: str = None,
    to_path: str = None,
    multi: bool = False
) -> None:
    """
    Convert all files in SOURCE folder

    --db:        Name of MySQL base.\n
    ..           If not set, it uses a SQLite base with path `dest + .db`

    --filecheck: Check if files in source match files in database

    --status:    Filter on status: accepted, converted, deleted, failed,\n
    ..           protected, skipped, timeout

    --from-path: Convert files where path is larger than or the same as this value

    --to-path:   Convert files where path is smaller than this value

    --multi:     Use multiprocessing to convert each subfolder in its own process

    """

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

        conds, params = store.get_conditions(mime=mime, puid=puid, status=status,
                                             reconvert=(reconvert or identify_only),
                                             from_path=from_path, to_path=to_path,
                                             timestamp=timestamp)

        count_remains = store.get_row_count(conds, params)
        m = Manager()
        count = {
            'remains': m.Value('i', count_remains),
            'finished': m.Value('i', 0),
            'failed': m.Value('i', 0)
        }

        if input(f"Converts {count_remains} files. Continue? [y/n] ") != 'y':
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
                        mime, puid, status, reconvert,
                        identify_only, filecheck, timestamp, set_source_ext,
                        from_path, to_path, count)
                pool.apply_async(convert_folder, args=args, error_callback=handle_error)
        else:
            convert_folder(source, dest, debug, orig_ext, db, '', True,
                           mime, puid, status, reconvert,
                           identify_only, filecheck, timestamp, set_source_ext,
                           from_path, to_path, count)

        pool.close()
        pool.join()

        duration = str(datetime.timedelta(seconds=round(time.time() - t0)))
        console.print('\nConversion finished in ' + duration)
        conds, params = store.get_conditions(finished=True, original=True,
                                             status='converted')
        count_converted = store.get_row_count(conds, params)
        console.print(f"{count_converted} files converted",
                      style="bold green")
        conds, params = store.get_conditions(finished=True, original=True,
                                             status='accepted')
        count_accepted = store.get_row_count(conds, params)
        if count_accepted:
            console.print(f"{count_accepted} files accepted",
                          style="bold green")
        conds, params = store.get_conditions(finished=True, original=True,
                                             status='skipped')
        count_skipped = store.get_row_count(conds, params)
        if count_skipped:
            console.print(f"{count_skipped} files skipped",
                          style="bold orange1")
        conds, params = store.get_conditions(finished=True, original=True,
                                             status='removed')
        count_removed = store.get_row_count(conds, params)
        if count_removed:
            console.print(f"{count_removed} files removed",
                          style="bold orange1")
        if count['failed'].value > 0:
            console.print(f"{count['failed'].value} files failed",
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
    status: str,
    reconvert: bool,
    identify_only: bool,
    filecheck: bool,
    timestamp: datetime.datetime,
    set_source_ext: bool,
    from_path: str,
    to_path: str,
    count: dict
) -> tuple[str, str]:
    """Convert all files in folder"""

    with Storage(db) as store:
        conds, params = store.get_conditions(mime=mime, puid=puid, status=status,
                                             reconvert=(reconvert or identify_only),
                                             subpath=subpath, from_path=from_path,
                                             to_path=to_path, timestamp=timestamp)
        table = store.get_rows(conds, params)

        # loop through all files and run conversion:
        # unpacked files are added to and converted in main loop
        table.row_count = 0
        i = 0
        percent = 0
        nrows = etl.nrows(table)
        while nrows > 0:
            i += 1
            count['finished'].value += 1
            row = etl.dicts(table)[0]
            if row['source_id'] is None:
                table.row_count += 1

            n = count['remains'].value
            new_percent = round((1 - n/(n + count['finished'].value)) * 100)
            percent = percent if percent > new_percent else new_percent

            if (
                reconvert and row['dest_path'] and
                os.path.isfile(Path(dest_dir, row['dest_path']))
            ):
                store.delete_descendants(row['id'])

            print(end='\x1b[2K')  # clear line
            print(f"\r{percent}% | "
                  f"{row['path'][0:100]}", end=" ", flush=True)

            unidentify = reconvert or identify_only
            src_file = File(row, pwconv_path, unidentify)
            norm_path = src_file.convert(source_dir, dest_dir, orig_ext,
                                         debug, identify_only)

            if identify_only and set_source_ext:
                mime_ext = mimetypes.guess_extension(src_file.mime)
                new_path = str(Path(src_file._parent, src_file._stem + mime_ext))
                shutil.move(src_file.path, new_path)
                src_file.path = new_path

            # If conversion failed
            if norm_path is False:
                if src_file.status == 'accepted':
                    console.print('file accepted', style="bold orange1")
                else:
                    console.print('  ' + src_file.status, style="bold red")
                    count['failed'].value += 1
            elif norm_path:
                dest_path = Path(dest_dir, norm_path)

                if src_file.source_id is None or src_file.kept:
                    source_id = src_file.id
                else:
                    source_id = src_file.source_id

                if os.path.isdir(dest_path):
                    unpacked_count = sum([len(files) for r, d, files
                                          in os.walk(dest_path)])
                    console.print(f'Unpacked {unpacked_count} files',
                                  style="bold cyan", end=' ')

                    # Write new files to database
                    filelist_dir = os.path.join(dest_dir, norm_path)
                    filelist_path = filelist_dir.rstrip('/') + '-filelist.txt'
                    make_filelist(os.path.join(dest_dir, norm_path),
                                  filelist_path)
                    n = write_id_file_to_storage(filelist_path, dest_dir, store,
                                                 norm_path, source_id=source_id)

                    nrows += n
                    count['remains'].value += n

                else:
                    status = 'new'
                    data = {'path': norm_path, 'status': status, 'source_id': source_id}

                    # If the file is converted again with the same extension,
                    # we should accept it. This happens when a pdf can't be
                    # converted to pdf/a. Files with `status:new` and `kept:True`
                    # are accepted in `File.convert`
                    if norm_path == src_file.path and src_file.source_id is not None:
                        data['kept'] = True

                    store.add_row(data)
                    nrows += 1
                    count['remains'].value += 1

            src_file.status_ts = datetime.datetime.now()
            if src_file.source_id is None or src_file.kept:
                store.update_row(src_file.__dict__)
            else:
                store.delete_row(src_file.__dict__)
            nrows -= 1
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
    conds, params = store.get_conditions(original=True)
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
    typer.run(convert)
