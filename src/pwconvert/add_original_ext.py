import os
import time
import datetime
from pathlib import Path
import typer
import petl as etl
from pwconvert.storage import Storage

app = typer.Typer(rich_markup_mode="markdown")
cwd = os.getcwd()


@app.command()
def add_ext(dest: str, db: str = None):
    """
    Add origininal file extension to converted files

    This works only if files were converted to a destination folder

    --db:        Name of MySQL base
                 If not set, it uses a SQLite base with path `dest + .db`
    """

    if dest and dest[0] != '/':
        dest = os.path.join(cwd, dest)

    if not db:
        db = dest.rstrip('/') + '.db'

    with Storage(db) as store:
        store.set_status_new_on_overwritten()

        files = store.get_converted_files()
        count = len(files)
        t0 = time.time()
        i = 0
        n = 0
        for file in etl.dicts(files):
            i += 1
            print(str(i) + '/' + str(count), end="\r")
            abs_path = Path(dest, file['path'])
            stem = Path(file['path']).stem
            parent = Path(file['path']).parent
            path_without_ext = str(Path(parent, stem))

            # If the file has another extension than the source file
            if stem in file['source_path'] and file['path'] != file['source_path']:
                # Path with original extension added
                new_path = file['path'].replace(path_without_ext, file['source_path'])
                new_abs_path = Path(dest, new_path)
                # Since we have duplicate files, the file may have been renamed before
                # if os.path.isfile(abs_path):
                if file['source_status'] != 'new' and os.path.isfile(abs_path):
                    os.rename(abs_path, new_abs_path)
                    store.update_row({'id': file['id'], 'path': new_path})
                else:
                    n += 1
                    store.delete_descendants(file['source_id'])

        duration = str(datetime.timedelta(seconds=round(time.time() - t0)))
        print('Finished in ' + duration)
        if n:
            print(f'Run `pw convert` again to reconvert {n} overwritten files')


if __name__ == "__main__":
    typer.run(add_ext)
