# Python conversion project

![PWConvert](https://i.imgur.com/NRKiULq.png)

contains scripts to convert files of different formats to archivable
formats that can be viewed in a browser.

While this software can convert files within the source folder, it is
recommended to convert to a destination folder, to avoid risk of loosing
original files. Use at own risk.

# Installation

1. Clone repo to desired location
   ```sh
   git clone https://github.com/Preservation-Workbench/PWConvert
   ```
2. cd into cloned repo
3. Make sure [uv](https://docs.astral.sh/uv/getting-started/installation/) is installed
4. Create virtual environment and install dependencies
   ```sh
   uv sync
   ```
5. Install scripts globally
   ```sh
   uv tool install .
   ```

   You will see which scripts are installed by uv. See also [scripts.yml](./scripts.yml).
6. Run install-script to install other command line tools to make conversions
   ```sh
   sudo ./install.sh
   ```

# How to use

- Add your desired configuration to `application.local.yml`, overriding `application.yml`
- Edit or add conversion commands in `converters.local.yml`, overriding `converters.yml`
- Run `pw --help` to see which commands are available
- Run `pw convert --help` to se how to run a conversion on a folder

Example:
```sh
pw convert /path/to/source/folder --dest /path/to/dest/folder
```

The files will be konverted and placed in the destination folder, and a sqlite
database with a `file` table with metadata and conversion results will be created in
`/path/to/dest/folder.db`. There will also be a table `file_content` with the content
of text files.
