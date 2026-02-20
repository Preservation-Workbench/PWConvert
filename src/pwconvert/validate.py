from pathlib import Path
import glob
import os
import time
import datetime
from multiprocessing import Pool, Manager

import typer
from .util import run_shell_cmd

app = typer.Typer(rich_markup_mode="rich")
cwd = os.getcwd()


# handle raised errors
def handle_error(error):
    print(error, flush=True)


def listener(q, fn):
    '''listens for messages on the q, writes to file. '''

    with open(fn, 'w') as f:
        while 1:
            m = q.get()
            if m == 'kill':
                break
            if m.strip():
                f.write(m.strip() + '\n')
                f.flush()


@app.command()
def validate_pdfs(dir: str, validator: str = 'pdfcpu', multi: bool = False,
                  mode: str = 'relaxed'):
    """ Validate pdf files in directory and list invalid files

    --validator pdfcpu|qpdf|gs\n
                NOTE: qpdf must be installed before being used

    --multi     convert subfolders with multiprocessing
    """

    if dir[0] != '/':
        dir = os.path.join(cwd, dir)

    fn = dir + '/invalid-pdfs.txt'

    t0 = time.time()

    if multi:
        manager = Manager()
        q = manager.Queue()
        pool = Pool()
        jobs = []

        # put listener to work first
        pool.apply_async(listener, (q, fn))

        args = (dir, q, validator, mode, False)
        job = pool.apply_async(validate_folder, args,
                               error_callback=handle_error)

        subdirs = [name for name in os.listdir(dir)
                   if os.path.isdir(os.path.join(dir, name))]

        for subdir in subdirs:
            path = str(Path(dir, subdir))
            args = (path, q, validator, mode, True)
            job = pool.apply_async(validate_folder, args,
                                   error_callback=handle_error)
            jobs.append(job)

        # collect results from the workers through the pool result queue
        for job in jobs:
            job.get()

        q.put('kill')
        pool.close()
        pool.join()
    else:
        error_files = validate_folder(dir, None, validator, mode, True)
        if len(error_files):
            with open(fn, 'w') as f:
                f.write(error_files)
                f.flush()

    duration = str(datetime.timedelta(seconds=round(time.time() - t0)))
    print('\nValidation finished in ' + duration)
    line_count = 0
    if os.path.exists(fn):
        with open(fn, 'r') as file:
            line_count = sum(1 for line in file)

    if line_count:
        print(str(line_count) + ' invalid files written to ', fn)
    else:
        print('All files are valid pdfs')

    return


def validate_folder(dir, q, validator, mode, recursive):
    if recursive:
        files = glob.glob(dir + '/**/*.pdf', recursive=True)
        files.extend(glob.glob(dir + '/**/*.PDF', recursive=True))
    else:
        files = glob.glob(dir + '/*.pdf')
        files.extend(glob.glob(dir + '/*.PDF'))
    error_files = ''
    count = len(files)
    i = 0
    for f in files:
        i += 1

        if validator == 'gs':
            cmd = 'gs -o /dev/null -sDEVICE=nullpage -dBATCH -dNOPAUSE "' + f + '"'
        elif validator == 'qpdf':
            cmd = 'qpdf --check "' + f + '"'
            cmd += ' --warning-exit-0' if mode == 'relaxed' else ''
        else:
            cmd = 'pdfcpu validate "' + f + '"'
            cmd += ' -m srict' if mode == 'strict' else ''
        result, out, err = run_shell_cmd(cmd, shell=True, timeout=300)
        print(end='\x1b[2K')  # clear line
        print(f"\r{i}/{count} | "
              f"{f}", end=" ", flush=True)

        if (
            result or
            'The file has been damaged' in out or
            'file had errors that were repaired' in out
        ):
            if (
                'file requires a password for access' in out or
                'please provide the correct password' in err
            ):
                error_files += "password\t"
                print('password')
            elif 'file has been damaged' in out:
                error_files += "damaged\t"
                print('damaged')
            elif 'file had errors that were repaired' in out:
                error_files += "repaired\t"
                print('repaired')
            elif 'Unrecoverable error' in str(err):
                error_files += "unrecoverable\t"
                print('unrecoverable')
            else:
                error_files += "invalid\t"
                print('invalid')
            error_files += f

            error_files += "\n"

    if q:
        q.put(error_files)

    return error_files
