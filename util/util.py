from __future__ import annotations
import re
import shutil
import subprocess
import os
import signal
import zipfile
import psutil
import time
from pathlib import Path
import petl as etl
from config import cfg
from storage import Storage


pwconv_path = Path(__file__).parent.parent.resolve()


def run_shell_cmd(command, cwd=None, timeout=None,
                  shell=False) -> tuple[int, str, str]:
    """
    Run the given command as a subprocess

    Args:
        command: The child process that should be executed
        cwd: Sets the current directory before the child is executed
        timeout: The number of seconds to wait before timing out the subprocess
        shell: If true, the command will be executed through the shell.
    Returns:
        exit code
    """
    os.environ["PYTHONUNBUFFERED"] = "1"

    # Make calls from subprocess timeout before main subprocess
    if not timeout:
        timeout = cfg['timeout'] - 1

    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ,
            universal_newlines=True,
            start_new_session=True,
        )
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        return 1, 'timeout', None
    except Exception as e:
        return 1, '', e

    return proc.returncode, out, err


def make_filelist(dir: str) -> None:
    os.chdir(dir)
    path = dir.rstrip('/') + '-filelist.txt'
    cmd = 'find -type f -not -path "./.*" | cut -c 3- > "' + path + '"'
    subprocess.run(cmd,
                   stderr=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL,
                   shell=True)


def filelist_to_storage(dir: str,  store: Storage) -> int:

    path = dir.rstrip('/') + '-filelist.txt'
    table = etl.fromtext(path, header=['filename'], strip="\n")
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

    # Treat csv (detected from extension only) as plain text:
    table = etl.convert(table, "mime", lambda v,
                        _row: "text/plain" if _row.id == "x-fmt/18" else v,
                        pass_row=True)

    # Update for missing mime types where id is known:
    table = etl.convert(table, "mime", lambda v,
                        _row: "application/xml" if _row.id == "fmt/979" else v,
                        pass_row=True)

    store.append_rows(table)
    row_count = etl.nrows(table)
    os.remove(path)
    return row_count


def remove_file(src_path: str) -> None:
    if os.path.exists(src_path):
        os.remove(src_path)


def delete_file_or_dir(path: str) -> None:
    """Delete file or directory tree"""
    if os.path.isfile(path):
        os.remove(path)

    if os.path.isdir(path):
        shutil.rmtree(path)


def extract_nested_zip(zipped_file: str, to_folder: str) -> None:
    """Extract nested zipped files to specified folder"""
    with zipfile.ZipFile(zipped_file, "r") as zfile:
        zfile.extractall(path=to_folder)

    for root, dirs, files in os.walk(to_folder):
        for filename in files:
            if re.search(r"\.zip$", filename):
                filespec = os.path.join(root, filename)
                extract_nested_zip(filespec, root)


def start_uno_server():
    if uno_server_running():
        return

    cmd = [cfg['libreoffice_python'], '-m', 'unoserver.server']
    started = False
    subprocess.Popen(
        cmd,
        start_new_session=True,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    print('starting unoserver ...')
    while not started:
        time.sleep(1)
        if uno_server_running():
            started = True

    return


def uno_server_running():
    for process in psutil.process_iter():
        if process.name() in ['soffice', 'soffice.bin']:
            return True

    return False


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

