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
import time
from os.path import relpath
from pathlib import Path
from typing import Dict
import typer

from rich.console import Console
import petl as etl
from petl.io.db import DbView

from storage import ConvertStorage, StorageSqliteImpl
from util import make_filelist, remove_file, File, Result
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


def convert(
    source: str,
    target: str,
    orig_ext: bool = cfg['keep-original-ext'],
    debug: bool = cfg['debug'],
    mime_type: str = None,
    result: str = None,
    db_path: str = None
) -> None:
    """
    Convert all files in SOURCE folder

    If --db-path is not set, it uses default `TARGET + '.db'`
    """

   
    Path(target).mkdir(parents=True, exist_ok=True)

    first_run = False

    if db_path and os.path.dirname(db_path) == '':
        console.print("Error: --db-path must refer to an absolute path", style='red')
        return
    if not db_path:
        db_path = target + '.db'
    if not os.path.isfile(db_path):
        first_run = True

    with StorageSqliteImpl(db_path) as file_storage:
        result, color = convert_folder(source, target, debug, orig_ext,
                                       mime_type, result, file_storage, False,
                                       first_run)
        console.print(result, style=color)


def convert_folder(
    source_dir: str,
    target_dir: str,
    debug: bool,
    orig_ext: bool,
    mime_type: str,
    result: str,
    file_storage: ConvertStorage,
    zipped: bool,
    first_run: bool
) -> tuple[str, str]:
    """Convert all files in folder"""

    t0 = time.time()
    filelist_path = os.path.join(target_dir, "filelist.txt")
    is_new_batch = os.path.isfile(filelist_path)
    if first_run or is_new_batch:
        if not is_new_batch:
            make_filelist(source_dir, filelist_path)
        tsv_source_path = filelist_path
        write_id_file_to_storage(tsv_source_path, source_dir, file_storage)

    written_row_count = file_storage.get_row_count(mime_type, result)
    total_row_count = file_storage.get_row_count(None)

    files_count = sum([len(files) for r, d, files in os.walk(source_dir)])
    if files_count == 0:
        return "No files to convert. Exiting.", "bold red"
    if files_count != total_row_count:
        console.print(f"Row count: {str(total_row_count)}", style="red")
        console.print(f"File count: {str(files_count)}", style="red")
        if input(f"Files listed in {file_storage.path} doesn't match "
                 "files on disk. Continue? [y/n] ") != 'y':
            return "User terminated", "bold red"

    if not zipped:
        console.print("Converting files..", style="bold cyan")

    if first_run:
        files_to_convert_count = written_row_count
        files_converted_count = 0
        table = file_storage.get_all_rows()
    elif is_new_batch:
        table = file_storage.get_new_rows()
        files_converted_count = 0
        files_to_convert_count = etl.nrows(table)
    else:
        # print the files in this directory that have already been converted
        files_to_convert_count, files_converted_count = print_converted_files(
            written_row_count, file_storage, mime_type, result
        )
        if files_to_convert_count == 0:
            return "All files converted previously.", "bold cyan"

        table = file_storage.get_unconverted_rows(mime_type, result)

    if input(f"Konverterer {etl.nrows(table)} filer. "
             "Vil du fortsette? [y/n] ") != 'y':
        return "User terminated", "bold red"

    # run conversion:
    table.row_count = 0
    for row in etl.dicts(table):
        table.row_count += 1
        convert_file(files_to_convert_count, file_storage, row, source_dir,
                     table, target_dir, zipped, debug, orig_ext)

    print(str(round(time.time() - t0, 2)) + ' sek')

    # check conversion result
    converted_count = etl.nrows(file_storage.get_converted_rows(mime_type))
    msg, color = get_conversion_result(files_converted_count,
                                       files_to_convert_count,
                                       converted_count)

    return msg, color


def convert_file(
    file_count: int,
    file_storage: ConvertStorage,
    row: Dict[str, any],
    source_dir: str,
    table: DbView,
    target_dir: str,
    zipped: bool,
    debug: bool,
    orig_ext: bool,
) -> None:
    if row['source_mime_type']:
        # TODO: Why is this necessary?
        row["source_mime_type"] = row["source_mime_type"].split(";")[0]
    if not zipped:
        print(end='\x1b[2K')  # clear line
        print(f"\r({str(table.row_count)}/{str(file_count)}): "
              f"{row['source_path']}", end=" ", flush=True)

    source_file = File(row, pwconv_path, file_storage, convert_folder)
    moved_to_target_path = Path(target_dir, row['source_path'])
    Path(moved_to_target_path.parent).mkdir(parents=True, exist_ok=True)
    normalized = source_file.convert(source_dir, target_dir, orig_ext, debug)
    row['result'] = normalized['result']
    row['source_mime_type'] = source_file.mime_type
    row['format'] = source_file.format
    row['source_file_size'] = source_file.file_size
    row['version'] = source_file.version
    row['puid'] = source_file.puid

    if normalized["dest_path"]:
        if str(normalized["dest_path"]) != str(moved_to_target_path):
            if moved_to_target_path.is_file():
                moved_to_target_path.unlink()

        row["moved_to_target"] = 0
        row["dest_path"] = relpath(normalized["dest_path"], start=target_dir)
        row["dest_mime_type"] = normalized['mime_type']
    else:
        console.print('  ' + row["result"], style="bold red")
        try:
            shutil.copyfile(Path(source_dir, row["source_path"]),
                            moved_to_target_path)
        except Exception as e:
            print(e)
        if moved_to_target_path.is_file():
            row["dest_path"] = source_file.path
            row["moved_to_target"] = 1
            row["dest_mime_type"] = source_file.mime_type

    file_storage.update_row(row["source_path"], list(row.values()))


def write_id_file_to_storage(tsv_source_path: str, source_dir: str,
                             file_storage: ConvertStorage) -> int:
    ext = os.path.splitext(tsv_source_path)[1]
    if ext == '.tsv':
        table = etl.fromtsv(tsv_source_path)
    else:
        table = etl.fromtext(tsv_source_path, header=['filename'])
    table = etl.rename(
        table,
        {
            "filename": "source_path",
            "filesize": "source_file_size",
            "mime": "source_mime_type",
            "Content_Type": "source_mime_type",
            "Version": "version",
        },
        strict=False,
    )
    table = etl.select(table, lambda rec: rec.source_path != "")
    # Remove listing of files in zip
    table = etl.select(table, lambda rec: "#" not in rec.source_path)
    table = add_fields(table, "source_mime_type", "version", "dest_path", "result",
                       "dest_mime_type", "puid")
    # Remove Siegfried generated columns
    table = remove_fields(table, "namespace", "basis", "warning")
    # TODO: Ikke fullgod sjekk på embedded dokument i linje over da # faktisk
    # kan forekomme i filnavn

    # Treat csv (detected from extension only) as plain text:
    table = etl.convert(table, "source_mime_type", lambda v,
                        _row: "text/plain" if _row.id == "x-fmt/18" else v,
                        pass_row=True)

    # Update for missing mime types where id is known:
    table = etl.convert(table, "source_mime_type", lambda v,
                        _row: "application/xml" if _row.id == "fmt/979" else v,
                        pass_row=True)

    file_storage.append_rows(table)
    row_count = etl.nrows(table)
    remove_file(tsv_source_path)
    return row_count


def print_converted_files(row_count: int,
                          file_storage: ConvertStorage,
                          mime_type: str,
                          result: str) -> tuple[int, int]:
    if result and result != Result.SUCCESSFUL:
        converted_files = []
    else:
        converted_files = file_storage.get_converted_rows(mime_type)
    already_converted = etl.nrows(converted_files)

    before = row_count
    row_count -= already_converted
    if already_converted > 0:
        console.print(f"({already_converted}/{before}) files have already "
                      "been converted", style="bold cyan")

    return row_count, already_converted


def get_conversion_result(before: int, to_convert: int,
                          total: int) -> tuple[str, str]:
    if total - before == to_convert:
        return "All files converted successfully.", "bold green"
    else:
        return ("Not all files were converted. See the db table for details.",
                "bold cyan")


if __name__ == "__main__":
    typer.run(convert)
