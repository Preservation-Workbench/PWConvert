# Python conversion project

![PWConvert](https://i.imgur.com/hDoBZuk.png)

contains scripts to convert files of different formats to archivable
formats that can be viewed in a browser.

This software is Alpha, and bugfixes are committed on the fly.
Use at own risk.

While this software can convert files within the source folder, it is
recommended to convert to a destination folder, to avoid risk of loosing
original files. 

# Install

1. Clone repo to desired location
   ```sh
   git clone https://github.com/Preservation-Workbench/PWConvert
   ```
2. cd into cloned repo
3. Make sure Python is installed, with pip package installer.
   ```sh
   python3 --version  # Check Python version
   pip3 --version     # Check pip version
   ```
4. Install packages listet in requirements.txt
   ```sh
   pip install -r requirements.txt
   ```
5. Run install-script
   ```sh
   sudo ./install.sh
   ```
6. Start program
   ```sh
   python3 convert.py
   ```

# How to use

* Add your desired configuration to `application.local.yml`, overriding `application.yml`
* Edit or add conversion commands in `converters.local.yml`, overriding `converters.yml`
* Make sure you have sqlite installed and the required python libraries
* Run convert.py
  * A SQLite database will now have been created in the direcory above the destination directory
    * The file table contains an entry per file in the source directory and the conversion result
  * The converted files will now be located in the destination directory
* The result will be printed to the console
  * More detailed results can be found in the file table

