import os
import sys
import io
import copy
import time
import select
import shutil
import mimetypes
import posixpath
import logging
from multiprocessing import Process,Pipe

import html
import urllib.parse
import http.server
import email.utils
import socketserver
import asyncio
import _thread as thread
from aiohttp import web

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
gi.require_version('GLib', '2.0')
gi.require_version('GObject', '2.0')
from gi.repository import Gst, GObject, GLib, GstPbutils
Gst.init(None)


#======= sub-process hls-service(backend)
class HlsService:
    def __init__(self, conn):
        self.conn = conn
        pass

    def on_message(self, msg):
        logging.info(msg)
        pass

    def run_forever(self):
        while True:
            try:
                ret = self.conn.poll(1)
                if ret:
                    msg = self.conn.recv()
                    self.on_message(msg)
            except:
                break
        pass
    pass


def run_hls_service(conn):
    logf = "/tmp/hls_service.txt"
    logging.basicConfig(filename=logf, encoding='utf-8',
            format='%(asctime)s [%(levelname)s][hls-srv] %(message)s',
            datefmt='%m/%d/%Y %H:%M:%S',
            level=logging.DEBUG)
    hls = HlsService(conn)
    hls.run_forever()


#======== parent-process hls-client
class HlsClient:
    def __init__(self, conn, child, onerr):
        self.conn = conn
        self.child = child
        self.onerr = onerr
        self.sname = None

    def post_message(self, msg):
        self.conn.send(msg)

    def on_message(self, msg):
        pass

    def run_listen(self, msg):
        while not self.stopped:
            try:
                ret = self.conn.poll(1)
                if ret:
                    msg = self.conn.recv()
                    self.on_message(msg)
            except:
                break
        pass


    def start(self):
        self.stopped = False
        thread.start_new_thread(self.run_service, ())
        thread.start_new_thread(self.run_listen, ())

    def stop(self):
        self.stopped = True
        self.child.kill()

    def run_service(self):
        logging.info("hls-cli run begin")
        self.child.join()
        self.onerr(self)
        logging.info("hls-cli run end")
    pass

def createHls(on_error):
    p1, p2 = Pipe(True)
    srv = Process(target=run_hls_service, args=(p1,))
    srv.start()
    cli = HlsClient(p2, srv, on_error)
    cli.start()
    return cli



#======== parent-process web
class MyHTTPRequestHandler:
    server_version = "pyhls/1.0"
    extensions_map = {
        '.gz': 'application/gzip',
        '.Z': 'application/octet-stream',
        '.bz2': 'application/x-bzip2',
        '.xz': 'application/x-xz',
        '.md': 'text/markdown',
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
        '.ts': 'video/MP2T',
        '.m38u': 'application/x-mpegURL',
    }

    def __init__(self, directory=None):
        if directory is None:
            directory = os.getcwd()
        self.directory = os.fspath(directory)
        self.services = []

    def on_service_error(self, svr):
        items = []
        for item in self.services:
            if item != svr:
                items.append(item)
        items.append(createHls(self.on_service_error))
        self.services = items
    def init_services(self):
        items.append(createHls(self.on_service_error))
        items.append(createHls(self.on_service_error))
        self.services = items
    def get_service(self, sname):
        for item in self.services:
            if item.sname == sname:
                return item
        for item in self.services:
            if not item.sname:
                return item
        return None
    def check_service(self, sname):
        cli = self.get_service(sname)
        if cli:
            cli.post_message({"type":"sname", "data":sname})
        if cli:
            return True
        return False

    async def check_hls(self, uri, headers):
        # segement file
        pos = uri.find("hlsvod/")
        path = self.translate_path("/root", uri)
        if pos == 0:
            if not os.path.exists(path):
                #TODO: not exists and check hls service
                # waiting timeout
                return None, path
            if not os.path.isfile(path):
                return web.HTTPNotFound(reason="File not found"), None
            return None, path

        # m38u file
        parts = os.path.splitext(path)
        if parts[1] == ".m38u":
            if os.path.exists(path):
                weberr, st_mtime = self.read_st_mtime(path)
                if weberr:
                    return weberr, None
                if self.check_modified(st_mtime, headers):
                    return web.HTTPNotModified(), None
                return None, path
            #TODO: not exists and start hls service
            #waiting timeout
            return None, path

        # source files
        # redirect to m38u or access directly.
        path = self.translate_path(self.directory, uri)
        if os.path.isdir(path):
            return None, path
        weberr, st_mtime = self.read_st_mtime(path)
        if weberr:
            return weberr, None
        if self.check_modified(st_mtime, headers):
            return web.HTTPNotModified(), None
        return None, path

    async def do_File(self, request):
        logging.info("do_File begin")
        try:
            headers = request.headers
            uri = request.match_info["uri"]
        except:
            uri = ""

        err, path = await self.check_hls(uri, headers)
        if err:
            return err

        print(uri, path)
        resp = self.send_static(uri, headers, path)
        print(resp, type(resp))
        return resp

    def send_static(self, uri, headers, path):
        if os.path.isdir(path):
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_directory(uri, path)

        if path.endswith("/"):
            return web.HTTPNotFound(reason="File not found")

        weberr, st_mtime = self.read_st_mtime(path)
        if weberr:
            return weberr

        if self.check_modified(st_mtime, headers):
            return web.HTTPNotModified()

        headers2 = {}
        headers2["Content-type"] = self.guess_type(path)
        headers2["Last-Modified"] = self.date_time_string(st_mtime)
        return web.FileResponse(path=uri, headers=headers2, status=200)

    def read_st_mtime(self, path):
        if not os.path.isfile(path):
            return web.HTTPNotFound(reason="File not found"), None

        try:
            f = open(path, 'rb')
        except OSError:
            return web.HTTPNotFound(reason="File not found"), None

        rets = [None, None]
        try:
            fs = os.fstat(f.fileno())
            rets[1] = fs.st_mtime
        except:
            rets[0] = web.HTTPInternalServerError()
        f.close()
        return rets[0], rets[1]

    def check_modified(self, st_mtime, headers):
        if ("If-Modified-Since" in headers and "If-None-Match" not in headers):
            try:
                ims = email.utils.parsedate_to_datetime(headers["If-Modified-Since"])
            except (TypeError, IndexError, OverflowError, ValueError):
                pass
            else:
                if ims.tzinfo is None:
                    ims = ims.replace(tzinfo=datetime.timezone.utc)
                if ims.tzinfo is datetime.timezone.utc:
                    last_modif = datetime.datetime.fromtimestamp(st_mtime, datetime.timezone.utc)
                    last_modif = last_modif.replace(microsecond=0)
                    if last_modif <= ims:
                        return True
        return False

    def list_directory(self, uri, path):
        try:
            list = os.listdir(path)
        except OSError:
            return web.HTTPNotFound(reason="No permission to list directory")
        list.sort(key=lambda a: a.lower())
        r = []
        try:
            displaypath = urllib.parse.unquote(path,
                                               errors='surrogatepass')
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(path)
        displaypath = html.escape(displaypath, quote=False)
        enc = sys.getfilesystemencoding()
        title = 'Directory listing for %s' % displaypath
        r.append('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
                 '"http://www.w3.org/TR/html4/strict.dtd">')
        r.append('<html>\n<head>')
        r.append('<meta http-equiv="Content-Type" '
                 'content="text/html; charset=%s">' % enc)
        r.append('<title>%s</title>\n</head>' % title)
        r.append('<body>\n<h1>%s</h1>' % title)
        r.append('<hr>\n<ul>')
        for name in list:
            fullname = os.path.join(path, name)
            displayname = name
            linkname = uri + "/" + name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = linkname + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            r.append('<li><a href="%s">%s</a></li>'
                    % (urllib.parse.quote(linkname,
                                          errors='surrogatepass'),
                       html.escape(displayname, quote=False)))
        r.append('</ul>\n<hr>\n</body>\n</html>\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')

        resp_headers = {}
        resp_headers["Content-type"] = "text/html; charset=%s" % enc
        return web.Response(body=encoded, headers=resp_headers)

    def translate_path(self, directory, path):
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        path = directory
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                # Ignore components that are not a simple file/directory name
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

    def copyfile(self, source, outputfile):
        shutil.copyfileobj(source, outputfile)

    def guess_type(self, path):
        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        guess, _ = mimetypes.guess_type(path)
        if guess:
            return guess
        return 'application/octet-stream'

    def date_time_string(self, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        return email.utils.formatdate(timestamp, usegmt=True)


async def run_web_server():
    handler = MyHTTPRequestHandler()
    app = web.Application(middlewares=[])
    app.add_routes([
        web.get('/', handler.do_File),
        web.get('/{uri}', handler.do_File),
        ])
    runner = web.AppRunner(app)
    await runner.setup()
    logging.info("start server...")
    site = web.TCPSite(runner, 'localhost', 8001)
    await site.start()

async def run_other_task():
    while True:
        await asyncio.sleep(1)


def do_main():
    logging.basicConfig(
            format='%(asctime)s [%(levelname)s][hls-cli] %(message)s',
            datefmt='%m/%d/%Y %H:%M:%S',
            level=logging.INFO)
    loop = asyncio.get_event_loop()
    try:
        loop.create_task(run_web_server())
        loop.run_until_complete(run_other_task())
        loop.run_forever()
    except:
        print()
        logging.warning("interrupt and close")
        pass
    print()

if __name__ == "__main__":
    do_main()
