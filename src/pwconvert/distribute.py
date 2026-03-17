import os
import typer
import shutil
import time
import datetime
from math import ceil
from pathlib import Path
from natsort import natsorted
from .storage import Storage
from .file import File
from .util import make_filelist, filelist_to_storage


# holds the original path so it can be used in distribute function recursively
orig_path = None
# total number of files that should be processed
file_count = 0
# counting processed files
count = 0
# dry run for counting total files that should be moved
dry_run = True

app = typer.Typer(rich_markup_mode="markdown")
cwd = os.getcwd()


@app.command()
def distribute(
    path: str = typer.Argument(help="Path to folder where files should be distibuted"),
    max: int = typer.Argument(help="Max number of files in each folder"),
    db: str = typer.Option(default=None, help="Path to database file"),
    prefix: str = typer.Option(
        default='',
        help="Prefix for folder name, numbers are added"
    ),
    leading_zeros: bool = typer.Option(
        default=False,
        help="Set True if number shoud have leading zeros"
    ),
    base_path: str = typer.Option(
        default='',
        hidden=True,
        help="Relative path to destination folder, relative to --path"
    ),
    debug: bool = typer.Option(default=False, hidden=True)
):
    """Distribute files in subfolders"""

    global orig_path, file_count, count, dry_run
    if path[0] != '/':
        path = os.path.join(cwd, path)
    num_files = len(os.listdir(path))
    orig_path = orig_path or path
    db = db or path.rstrip('/') + '.db'

    if base_path == '':
        t1 = time.time()
        if dry_run:
            print('counting files to move ...')

    with Storage(db) as store:
        # Create database if it doesn't exist
        first_run = store.get_row_count() == 0
        if first_run:
            make_filelist(path)
            filelist_to_storage(path, store)

        dest_path = os.path.join(orig_path, base_path).rstrip('/')

        # Hold the number of processed files in directory
        i = 0
        # If the distribution is stopped and started again, we need to find
        # existing distribution folders
        prev_dist_count = 0
        dist_folders = []
        if os.path.isdir(dest_path):
            dirlist = [f.name for f in os.scandir(dest_path) if f.is_dir()]
            dirlist = natsorted(dirlist)
            for fname in dirlist:
                # Only count as distribution folder when number is incremented by 1
                if not (
                    fname.startswith(prefix) and
                    fname[len(prefix):].isdigit() and
                    int(fname[len(prefix):]) == prev_dist_count + 1
                ):
                    continue
                dist_folders.append(fname)
                # We must add all files moved to distribution folders
                # when the script is restarted, to know which distribution
                # folder the rest of the files should be placed in
                folderpath = os.path.join(dest_path, fname)
                i += len(os.listdir(folderpath))
                prev_dist_count += 1

        # Get all files in path, but exclude eventual existing distribution folders
        dirlist = [f.name for f in os.scandir(path) if f.is_dir()
                   if path != dest_path or f.name not in dist_folders]
        filelist = [f.name for f in os.scandir(path)
                    if f.is_file()]
        # filelist = sorted(filelist, key=lambda x: (os.path.isfile(os.path.join(path, x)), x))
        filelist = dirlist + filelist
        num_files += i
        # Find precision for handling leading zeros
        precision = len(str(ceil(num_files/max)))

        continued = False
        if i > 0:
            continued = True
        prev_dist_count = 0

        n = 0
        for filename in filelist:
            i += 1
            n += 1
            count += 1
            if not dry_run:
                print(end='\x1b[2K')  # clear line
                print(f"\r{count}/{file_count} | "
                      f"{filename}", end=" ", flush=True)
            # We don't distribute files in folders that just have a little
            # more files than we put in distribution folders
            if num_files > 2 * max:
                folder_name = prefix + str(ceil(i/max)).zfill(precision)
                parent_path = os.path.join(base_path, folder_name)
            else:
                parent_path = base_path
            file_path = os.path.join(path, filename)
            relative_path = os.path.relpath(file_path, start=orig_path)

            if os.path.isdir(file_path):
                # folders shouldn't be counted
                count -= 1
                # If the script is restarted, with some files already moved
                if continued:
                    folder_path = os.path.join(orig_path, dist_folders[-1])
                    # If some of the files in this folder is already moved
                    # to distribution folders, then we must adjust the counter
                    # to get the right distribution folder
                    if filename in os.listdir(folder_path):
                        i -= 1
                        folder_name = prefix + str(ceil(i/max)).zfill(precision)
                        parent_path = os.path.join(base_path, folder_name)
                    continued = False
                new_base_path = os.path.join(parent_path, filename)
                distribute(file_path, max, db=db, prefix=prefix,
                           leading_zeros=leading_zeros,
                           base_path=new_base_path, debug=debug)
                if parent_path != os.path.dirname(relative_path):
                    # Remove folder after all its files are distributed
                    if not dry_run:
                        os.rmdir(file_path)
            elif parent_path != os.path.dirname(relative_path):
                if dry_run:
                    count += len(filelist) - n 
                    print(end='\x1b[2K')  # clear line
                    print(f"\r{count}", end=" ", flush=True)
                    break
                dest_path = os.path.join(orig_path, parent_path, filename)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                rec = store.get_kept_rec(relative_path.replace('\n', ' '))
                if rec is None:
                    print('File not in database: ', relative_path)
                    continue
                if rec['source_id'] is None:
                    # If existing record in database refers to original file,
                    # we must change the status to 'renamed' and create a new
                    # record with the path to the distributed file
                    status = rec['status']
                    kept = rec['kept']
                    if rec['status'] != 'new' and not kept:
                        # This generates a new rec if it's missing by a mistake
                        print('only original file found in db', relative_path)
                        print('generates record in db for converted file')
                        file = File(rec, True)
                        file.set_metadata(file_path, orig_path)
                        file.ext = Path(file_path).suffix
                        status = 'accepted'
                        kept = 1
                        file.status_ts = datetime.datetime.now()
                        rec = file.__dict__
                    elif rec['status'] == 'new':
                        file = File(rec, True)
                        file.set_metadata(file_path, orig_path)
                        file.status = 'renamed'
                        file.kept = 0
                        file.log(db)
                        rec = file.__dict__
                    else:
                        rec['status'] = 'renamed'
                        rec['kept'] = 0
                        store.update_row(rec)
                    rec['path'] = os.path.join(parent_path, filename)
                    rec['status'] = status
                    rec['kept'] = kept
                    rec['source_id'] = rec['id']
                    rec['id'] = None
                    store.add_row(rec)
                else:
                    # If the record does not refer to original file, we can just
                    # update the path
                    rec['path'] = os.path.join(parent_path, filename)
                    store.update_row(rec)
                shutil.move(file_path, dest_path.replace('\n', ' '))

    if base_path == '':
        if dry_run:
            dry_run = False
            file_count = count
            count = 0
            distribute(path, max, db=db, base_path='', prefix=prefix, leading_zeros=leading_zeros,
                       debug=debug)
        else:
            duration = str(datetime.timedelta(seconds=round(time.time() - t1)))
            print('\nDistribution finished in ' + duration)

    return count
