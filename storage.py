import os
import sqlite3
import pymysql
from sqlite3 import Connection
from typing import Optional

import petl
from petl import appenddb, fromdb, todb
from config import cfg


class Storage:
    _create_table_str = """
    CREATE TABLE file(
        id integer auto_increment primary key,
        path varchar(1000) not null,
        size integer,
        puid varchar(10),
        format varchar(100),
        version varchar(32),
        mime varchar(100),
        encoding varchar(30),
        ext varchar(10),
        status varchar(10),
        status_ts datetime,
        kept boolean,
        source_id int
    );
    """

    _create_view_file_root = """
    create view file_root as
    with recursive cte as (
        select id, path, source_id, id as root_id
        from file
        where source_id is null
        union
        select f.id, f.path, f.source_id, h.root_id as root_id
        from file f
        join cte h
        on h.id = f.source_id
        where f.id != f.source_id
    )
    select * from cte
    order by path;
    """

    def __init__(self, path: str):
        self._conn = Optional[Connection]
        self.path = path
        self.system = 'sqlite' if '.' in path else 'mysql'

    def __enter__(self):
        self.load_data_source()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_data_source()

    def load_data_source(self):
        storage_dir = os.path.dirname(self.path)
        if '.' in self.path:
            if not os.path.isdir(storage_dir):
                os.makedirs(storage_dir)

            self._conn = sqlite3.connect(self.path)

            query = """
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='file'        
            """

            cursor = self._conn.cursor()

            cursor.execute(query)

        else:
            self._conn = pymysql.connect(host=cfg['db']['host'],
                                         user=cfg['db']['user'],
                                         password=cfg['db']['pass'])

            query = f"""
                create database if not exists {self.path}
            """

            cursor = self._conn.cursor()
            cursor.execute(query)
            cursor.execute(f'use {self.path}')
            cursor.execute('SET SQL_MODE=ANSI_QUOTES')

            query = f"""
            SELECT *
            FROM information_schema.tables
            WHERE table_schema = '{self.path}'
            AND table_name = 'file'
            """

        cursor.execute(query)
        rows = cursor.fetchall()
        if len(rows) == 0:
            sql = self._create_table_str
            if self.system == 'sqlite':
                sql = sql.replace('auto_increment', '')
            cursor.execute(sql)
            cursor.execute("CREATE INDEX file_status on file(status)")
            cursor.execute("CREATE INDEX file_status_ts on file(status_ts)")
            cursor.execute(self._create_view_file_root)
        self._conn.commit()

    def close_data_source(self):
        if self._conn:
            self._conn.close()

    def import_rows(self, table):
        todb(table, self._conn, "file")

    def append_rows(self, table):
        # select the first row (primary key) and filter away rows that already exist

        cursor = self._conn.cursor()

        cursor.execute("SELECT path FROM file")
        rows = cursor.fetchall()
        file_names = [row[0] for row in rows]
        table = petl.select(
            table,
            lambda rec: (rec.path not in file_names)
        )
        # append new rows
        appenddb(table, self._conn, "file")

    def update_row(self, data: dict):
        del data['norm']
        id = data['id']
        sql = 'UPDATE file SET {}'.format(', '.join('{}=?'.format(k) for k in data
                                                    if k != 'id' and not k.startswith('_')))
        if self.system == 'mysql':
            sql = sql.replace('?', '%s')
        sql += ' WHERE id = ' + str(id)
        cursor = self._conn.cursor()
        if self.system == 'sqlite':
            cursor.execute('PRAGMA journal_mode=wal')
        cursor.execute(sql, tuple(v for k, v in data.items()
                                  if k != 'id' and not k.startswith('_')))
        self._conn.commit()

    def add_row(self, data: dict):
        sql = "insert into file ({})".format(', '.join('{}'.format(k) for k in data
                                                       if k != 'id' and not k.startswith('_')))
        sql += " values ({})".format(', '.join('?'.format(k) for k in data
                                               if k != 'id' and not k.startswith('_')))
        if self.system == 'mysql':
            sql = sql.replace('?', '%s')

        cursor = self._conn.cursor()
        if self.system == 'sqlite':
            cursor.execute('PRAGMA journal_mode=wal')
        cursor.execute(sql, tuple(v for k, v in data.items()
                                  if k != 'id' and not k.startswith('_')))
        self._conn.commit()

    def delete_row(self, data: dict):
        sql = "delete from file where id = ?"
        if self.system == 'mysql':
            sql = sql.replace('?', '%s')
        cursor = self._conn.cursor()
        cursor.execute(sql, (data['id'],))
        self._conn.commit()

    def get_subfolders(self, conds, params):
        cursor = self._conn.cursor()
        if self.system == 'sqlite':
            query = """
            SELECT DISTINCT substr(path, 0, instr(path, '/')) as dir
            FROM   file
            """
        else:
            query = """
            SELECT DISTINCT substr(path, 1, instr(path, '/')-1) as dir
            FROM   file
            """

        if len(conds):
            query += "\nwhere " + ' AND '.join(conds)

            if self.system == 'mysql':
                query = query.replace('?', '%s')

        cursor.execute(query, params)

        rows = cursor.fetchall()
        folders = []
        for row in rows:
            folders.append(row[0])

        return folders

    def get_row_count(self, conds=[], params=[]):
        cursor = self._conn.cursor()
        if self.system == 'sqlite':
            cursor.execute('PRAGMA journal_mode=wal')
        query = "SELECT COUNT(*) FROM file"

        if len(conds):
            query += " where " + ' AND '.join(conds)

        if self.system == 'mysql':
            query = query.replace('?', '%s')

        cursor.execute(query, params)
        count = cursor.fetchone()[0]

        return count

    def get_all_rows(self, unpacked_path):

        if unpacked_path:
            unpacked_path = os.path.join(unpacked_path, '')
            unpacked_path = unpacked_path.replace("'", "''")

        sql = f"""
        SELECT * FROM file
        where path like '{str(unpacked_path)}%'
          and source_id IS NULL
        """
        params = []

        return fromdb(
            self._conn,
            sql,
            params
        )

    def get_new_rows(self):

        sql = """
        SELECT * FROM file
        WHERE  status IS NULL
        """

        return fromdb(
            self._conn,
            sql,
        )

    def get_conds(self, mime=None, puid=None, status=None, reconvert=False,
                  finished=False, subpath=None, from_path=None, to_path=None,
                  timestamp=None, original=False, ext=None, retry=False):

        conds = []
        params = []

        if original:
            conds.append("source_id IS NULL")

        if not finished and not reconvert:
            conds.append('(status is null or status not in (?, ?, ?, ?))')
            params.append('converted')
            params.append('accepted')
            params.append('removed')
            params.append('renamed')
        elif finished:
            conds.append('status_ts is not null')

        if reconvert:
            conds.append('source_id is null')

        if not retry and not reconvert and not finished:
            conds.append('status_ts is null')

        if mime:
            conds.append("mime = ?")
            params.append(mime)

        if puid:
            conds.append("puid = ?")
            params.append(puid)

        if status:
            conds.append("status = ?")
            params.append(status)

        if subpath:
            conds.append("path like ?")
            params.append(subpath + '%')

        if from_path:
            conds.append("path >= ?")
            params.append(from_path)

        if to_path:
            conds.append("path < ?")
            params.append(to_path)

        if ext:
            conds.append("ext = ?")
            params.append(ext)
        elif ext == '':
            conds.append("ext = ?")
            params.append('')

        if timestamp:
            if not finished:
                conds.append("(status_ts is null or status_ts < ?)")
            else:
                conds.append("status_ts > ?")
            params.append(timestamp)

        return conds, params

    def get_rows(self, conds, params, limit=None):

        select = "SELECT * from file"

        if len(conds):
            select += " WHERE " + ' AND '.join(conds)

        select += 'ORDER BY path'

        # Since the selection is run for every file, limit the result.
        # If not the query takes too long on MySQL for large number of files
        if limit:
            select += " LIMIT " + str(limit)

        if self.system == 'mysql':
            select = select.replace('?', '%s')

        return fromdb(self._conn, select, params)

    def get_all(self, conds, params):
        select = "SELECT * from file"

        if len(conds):
            select += " WHERE " + ' AND '.join(conds)

        if self.system == 'mysql':
            select = select.replace('?', '%s')

        cursor = self._conn.cursor()
        rows = cursor.execute(select, params).fetchall()

        recs = []
        for row in rows:
            cols = [col[0] for col in cursor.description]
            rec = dict(zip(cols, row))
            recs.append(rec)

        return recs

    def get_failed_rows(self, mime: str = None):
        select = """
            SELECT path FROM file
            WHERE  status IS NOT NULL AND status IN(?, ?, ?)
        """
        params = ['timeout', 'failed', 'protected']

        if mime:
            select += " AND mime = ?"
            params.append(mime)

        if self.system == 'mysql':
            select = select.replace('?', '%s')

        return fromdb(self._conn, select, params)

    def get_skipped_rows(self, mime: str = None):
        select = """
            SELECT path FROM file
            WHERE  status IS NOT NULL AND status IN(?)
        """
        params = ['skipped']

        if mime:
            select += " AND mime = ?"
            params.append(mime)

        if self.system == 'mysql':
            select = select.replace('?', '%s')

        return fromdb(self._conn, select, params)

    def get_new_mime_types(self):
        return fromdb(
            self._conn,
            """
            SELECT count(*) as no, mime FROM file
            WHERE status is NULL
            GROUP BY mime
            ORDER BY count(*) desc
            """
        )

    def get_unconv_mime_types(self):
        return fromdb(
            self._conn,
            """
            SELECT count(*) as no, mime FROM file
            WHERE status is NULL OR status NOT IN(?)
            GROUP BY mime
            ORDER BY count(*) desc
            """,
            ['converted']
        )

    def update_status(self, conds, params, status):
        sql = """
        update file set status = ?
        """

        if len(conds):
            sql += " WHERE " + ' AND '.join(conds)

        params.insert(0, status)

        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        self._conn.commit()
        params.pop(0)

    def get_children(self, id):
        sql = """
        select * from file where source_id = ?
        """

        if self.system == 'mysql':
            sql = sql.replace('?', '%s')

        cursor = self._conn.cursor()
        if self.system == 'sqlite':
            cursor.execute('PRAGMA journal_mode=wal')
        params = [id]
        cursor.execute(sql, params)
        return cursor.fetchall()

    def get_descendants(self, id):
        sql = """
        with recursive descendant as (
        select a.id, a.id as orig, a.source_id from file a
        where a.id = ?
        union all
        select b.id, c.orig as orig, b.source_id from file b
        inner join descendant c on c.id = b.source_id
        )
        select * from file
        where id in (select id from descendant where source_id is not null)
        """

        if self.system == 'mysql':
            sql = sql.replace('?', '%s')

        cursor = self._conn.cursor()
        params = [id]
        cursor.execute(sql, params)
        return cursor.fetchall()

    def delete_children(self, id):
        sql = """
        delete from file where source_id = ?
        """

        if self.system == 'mysql':
            sql = sql.replace('?', '%s')

        params = [id]
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        self._conn.commit()

    def delete_descendants(self, id):
        sql = """
        with recursive descendant as (
        select a.id, a.id as orig, a.source_id from file a
        where a.id = ?
        union all
        select b.id, c.orig as orig, b.source_id from file b
        inner join descendant c on c.id = b.source_id
        )
        delete from file
        where id in (select id from descendant where source_id is not null)
        """

        if self.system == 'mysql':
            sql = sql.replace('?', '%s')

        params = [id]
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        self._conn.commit()

    def set_status_new_on_overwritten(self):
        """
        Set status 'new' on source files where converted
        files are overwritten by other converted files, because
        original file extension wasn't kept
        """

        sql = """
        update file
        set status = 'new'
        where id in (select file2.source_id from file
                     join file file2 on file2.path = file.path and file2.id > file.id
                     where file.source_id is not null and file2.source_id is not null)
        """

        cursor = self._conn.cursor()
        cursor.execute(sql)
        self._conn.commit()

    def get_converted_files(self):

        sql = """
        select file.id, file.path, file.size, source.path as source_path,
               source.id as source_id, source.status as source_status
        from   file
        join   file source on source.id = file.source_id
        """

        # cursor = self._conn.cursor()
        # rows = cursor.execute(sql)

        # return rows
        return fromdb(self._conn, sql)

