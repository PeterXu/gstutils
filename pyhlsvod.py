import os
import sys
import io
import re
import copy
import time
import select
import shutil
import mimetypes
import posixpath
import logging
from multiprocessing import Process,Pipe
import threading

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


def get_now():
    return int(time.time()*1000)


#======== gstreamer service
Gst.init(None)

def gst_make_elem(name, props={}, alias=None):
    #print(name, props, alias)
    if not name: return None
    elem = Gst.ElementFactory.make(name, alias)
    if elem and props:
        for k,v in props.items(): elem.set_property(k, v)
    return elem
def gst_add_elems(pipeline, elems=[]):
    for e in elems:
        if e: pipeline.add(e)
def gst_link_elems(elems, dst=None):
    last = None
    for e in elems:
        if last: last.link(e)
        last = e
    if last and dst: last.link(dst)
def gst_set_playing(elems=[]):
    for e in elems:
        e.set_state(Gst.State.PLAYING)
def gst_make_filter(fmt): # "video/x-raw", "audio/x-raw"
    caps = Gst.Caps.from_string(fmt)
    return gst_make_elem("capsfilter", {"caps": caps})
def gst_check_elem(name):
    if gst_make_elem(name): return name
    else: return None
def gst_make_mux_profile(caps):
    if caps == "video/mpegts":
        return "video/mpegts,systemstream=true,packetsize=188"
    elif caps == "video/quicktime":
        return "video/quicktime"
    return "matroskamux"
def gst_make_h264_enc_profile(kbps):
    bps = kbps * 1024
    props1 = {"rc-mode":"vbr", "bps":bps, "profile":"main",}
    props2 = {"pass":"pass1", "bitrate":bps, "profile":"main",}
    props = {"mppvideoenc": props1, "avenc_h264_videotoolbox": props2, "avenc_h264": props2}
    enc = gst_check_elem("mppvideoenc")
    if not enc:
        enc = gst_check_elem("avenc_h264_videotoolbox")
    if not enc:
        enc = gst_check_elem("avenc_h264")
    if not enc: return "video/x-h264"
    profile = enc
    for k, v in props[enc].items():
        profile = "%s,%s=%s" % (profile, k, v)
    return profile
def gst_make_aac_enc_profile(kbps):
    bps = kbps * 1024
    enc = gst_check_elem("avenc_aac")
    if not enc: return "audio/mpeg"
    return "%s,bitrate=%s" % (enc, bps)

def gst_parse_props(line, key):
    if line.find(key) == -1: return {}
    ret = re.search("%s ([\w/-]+)[,]*(.*)" % key, line)
    if not ret or len(ret.groups()) == 0: return {}
    #print(ret.groups())
    props = {}
    props["type"] = ret.groups()[0]
    props["more"] = {}
    if len(ret.groups()) >= 2:
        for item in ret.groups()[1].split(", "):
            pair = item.strip().split("=")
            if len(pair) == 2: props["more"][pair[0]] = pair[1]
    #print(props)
    return props
def gst_discover_info(fname):
    info = {}
    shbin = "gst-discoverer-1.0 -v %s" % fname
    lines = os.popen(shbin)
    for line in lines:
        if line.find("Duration: ") >= 0:
            pos = line.find("Duration: ")
            items = line[pos+10:].split(".")[0].split(":")
            if len(items) == 3:
                info["duration"] = int(items[0])*3600 + int(items[1])*60 + int(items[2])
        elif line.find("container:") >= 0:
            info["mux"] = gst_parse_props(line, "container:")
        elif line.find("unknown:") >= 0: 
            info["mux"] = gst_parse_props(line, "unknown:")
        elif line.find("audio:") >= 0:
            info["audio"] = gst_parse_props(line, "audio:")
        elif line.find("video:") >= 0:
            info["video"] = gst_parse_props(line, "video:")
    #print(info)
    return info
def gst_parse_value(item):
    if not item: return None
    ret = re.search("\((.*)\)(.*)", item)
    if not ret or len(ret.groups()) <= 1: return None
    stype, sval = ret.groups()[0:2]
    if stype == "fraction":
        ival = 0
        for ch in sval:
            if ch >= '0' and ch <= '9': ival = ival * 10 + int(ch)
            else: break
        return ival
    elif stype == "int":
        return int(sval)
    elif stype == "boolean":
        return sval == "true"
    return sval

class MediaExtm3u(object):
    def __init__(self):
        self.fp = None
        self.last_seq = 0
        self.is_begin = False
        self.is_end = False
        pass
    def open(self, fname, is_parse=False):
        if is_parse: mode = "rb"
        else: mode = "wb+";
        self.fname = fname
        self.fp = open(fname, mode)
        if not self.fp:
            return False
        last_inf = False
        for line in self.fp.readlines():
            if line.find("#EXTM3U") == 0:
                self.is_begin = True
            elif line.find("#EXT-X-ENDLIST") == 0:
                self.is_end = True
            elif line.find("#EXTINF:") == 0:
                last_inf = True
                continue
            if last_inf:
                last_inf = False
                try:
                    result = re.search(".*segment_(\d+).ts", line)
                    self.last_seq = int(result.groups()[0])
                except:
                    return False
        if not self.is_begin and self.is_end:
            return False
        return True
    def next_name(self):
        self.last_seq += 1
        return "hls_segment_%06d.ts" % self.last_seq
    def begin(self, fname, second):
        if self.is_begin: return False
        fp = self.fp
        fp.write("#EXTM3U\n")
        fp.write("#EXT-X-VERSION:3\n")
        fp.write("#EXT-X-ALLOW-CACHE:NO\n")
        fp.write("#EXT-X-MEDIA-SEQUENCE:0\n")
        fp.write("#EXT-X-TARGETDURATION:%d\n" % second)
        fp.write("\n")
        return True
    def add(self, second, segment):
        if self.is_end: return False
        self.fp.write("#EXTINF:%d,\n" % second)
        self.fp.write("%s\n" % segment)
        return True
    def end(self):
        if self.is_end: return False
        self.fp.write("#EXT-X-ENDLIST")
        return True
    def close(self):
        self.fp.close()


class MediaInfo(object):
    def __init__(self):
        self.infile = ''
        self.info = {}

    def duration(self):
        try: return self.info.get("duration")
        except: return 0

    def mediaType(self, kind): #mux/audio/video
        try: return self.info.get(kind).get("type")
        except: return None

    def hasAudio(self):
        return self.mediaType("audio") != None

    def hasVideo(self):
        return self.mediaType("video") != None

    def frameRate(self):
        try: value = self.info.get("video").get("more").get("framerate")
        except: return 0
        return gst_parse_value(value)

    def width(self):
        try: value = self.info.get("video").get("more").get("width")
        except: return 0
        return gst_parse_value(value)

    def height(self):
        try: value = self.info.get("video").get("more").get("height")
        except: return 0
        return gst_parse_value(value)

    def isWebDirectSupport(self):
        mux = self.mediaType("mux")
        if mux == "video/quicktime" or mux == "application/x-3gp" or mux == "audio/x-m4a":
            audio = self.mediaType("audio")
            video = self.mediaType("video")
            if audio != None and audio != "audio/mpeg": return False
            if video != None and video != "video/x-h264": return False 
            return True
        return False

    def parse(self, infile):
        info = gst_discover_info(infile)
        if not info: return False
        self.infile = infile
        self.info = info
        if self.duration() == 0:
            return False
        logging.info(["coder media:", "\n", info])
        if self.hasVideo():
            fps = self.frameRate()
            width = self.width()
            height = self.height()
            if fps == 0 or width == 0 or height == 0:
                return False
            logging.info(["coder video:", fps, width, height])
        return True


class Transcoder(object):
    def __init__(self):
        self.loop = None
        self.pipeline = None
        self.duration = 0
        self.video_fps = 0
        self.video_width = 0
        self.video_height = 0
        pass

    def do_work(self, infile, outfile, outcaps, akbps, vkbps):
        mux = gst_make_mux_profile(outcaps)
        aac = gst_make_aac_enc_profile(akbps)
        avc = gst_make_h264_enc_profile(vkbps)
        profile = "%s:%s:%s" % (mux, avc, aac)
        logging.info(["coder profile:", profile])

        source = gst_make_elem("filesrc", {"location": infile})
        transcode = gst_make_elem("transcodebin")
        Gst.util_set_object_arg(transcode, "profile", profile);
        sink = gst_make_elem("filesink", {"location": outfile})
        elems = [source, transcode, sink]

        self.pipeline = Gst.Pipeline()
        gst_add_elems(self.pipeline, elems)
        gst_link_elems(elems)
        self.elems = elems

        self.check_run()

    def do_stop(self):
        if self.loop and self.pipeline:
            self.loop.quit()

    def get_state(self):
        if self.loop and self.pipeline:
            return self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        return -1

    def check_run(self):
        GLib.timeout_add(200, self.do_position)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

        self.loop = GLib.MainLoop()
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        logging.info(["coder run begin:", ret])
        try: self.loop.run()
        except: pass
        logging.info("coder run end");
        self.pipeline.set_state(Gst.State.NULL)
        pass

    def do_position(self):
        ok, pos = self.pipeline.query_position(Gst.Format.TIME)
        if ok:
            value = float(pos) / Gst.SECOND
            logging.info(["coder position:", pos, value])

    def do_seek_steps(self, sink, steps):
        self.pipeline.set_state(Gst.State.PAUSED)
        event = Gst.Event.new_step(Gst.Format.BUFFERS, steps, 2.0, True, False)
        sink.send_event(event)
        pass

    def on_message(self, bus, msg):
        if msg.type == Gst.MessageType.EOS:
            logging.info("coder message: EOS and quit")
            self.pipeline.set_state(Gst.State.NULL)
            self.loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            self.pipeline.set_state(Gst.State.NULL)
            err, debug = msg.parse_error()
            logging.info("coder message: Error: %s", err)
            self.loop.quit()
        pass


#======= sub-process hls-service(backend)
class HlsService:
    def __init__(self, conn):
        self.mutex = threading.Lock()
        self.conn = conn
        self.last_time = 0
        self.coder = None
        pass

    def _loop(self, coder):
        coder.do_work()

    def is_alive(self):
        if self.coder:
            return self.coder.get_state() != -1
        return False

    def stop_coder(self):
        if self.coder:
            self.coder.do_stop()
            self.coder = None

    def start_coder(self):
        self.last_time = get_now()
        self.coder = Transcoder()
        thread.start_new_thread(self._loop, (coder))

    def on_message(self, msg):
        logging.info(msg)
        mtype = msg["type"]
        if mtype == "status":
            self.conn.send({"type": "status", "data": self.is_alive()})
        elif mtype == "update":
            self.last_time = get_now()
        elif mtype == "source":
            pass
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
            if self.is_alive():
                if get_now() >= self.last_time + 10*1000:
                    self.stop_coder()
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
    def __init__(self, conn, child):
        self.mutex = threading.Lock()
        self.alive = True
        self.conn = conn
        self.child = child
        self.source = None

    def set_alive(self, state):
        self.mutex.acquire()
        self.alive = state
        self.mutex.release()

    def is_alive(self):
        self.mutex.acquire()
        state = self.alive
        self.mutex.release()
        return state

    def is_timeout(self):
        return False

    def post_message(self, msg):
        self.conn.send(msg)

    def on_message(self, msg):
        pass

    def start(self):
        self.set_alive(True)
        thread.start_new_thread(self._service, ())
        thread.start_new_thread(self._listen, ())

    def stop(self):
        self.set_alive(False)
        self.child.kill()

    def _service(self):
        logging.info("hls-cli run begin")
        self.child.join()
        self.set_alive(False)
        logging.info("hls-cli run end")

    def _listen(self, msg):
        while self.alive:
            try:
                ret = self.conn.poll(1)
                if ret:
                    msg = self.conn.recv()
                    self.on_message(msg)
            except:
                break
        pass

def createHls():
    p1, p2 = Pipe(True)
    srv = Process(target=run_hls_service, args=(p1,))
    srv.start()
    cli = HlsClient(p2, srv)
    cli.start()
    return cli



#======== parent-process web
class MyHTTPRequestHandler:
    server_version = "pyhls/1.0"
    support_exts = {
        '.m38u': True,
        '.ts':   True,
        '.mp4':  True,
    }
    extensions_map = {
        '.gz': 'application/gzip',
        '.Z': 'application/octet-stream',
        '.bz2': 'application/x-bzip2',
        '.xz': 'application/x-xz',
        '.md': 'text/markdown',
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
        #'.ts': 'video/mpegts',
        '.ts': 'video/MP2T',
        #'.m38u': 'application/x-hls',
        '.m38u': 'application/x-mpegURL',
        '.sh': "text/html",
    }

    def __init__(self, directory=None):
        if directory is None:
             directory = os.getcwd()
        self.workdir = os.fspath(directory)
        self.hlsdir = "/tmp/cached"
        self.hlskey = "hlsvod"
        self.hlsindex = "index.m38u"
        self.services = []

    def check_service(self):
        items = []
        for item in self.services:
            if item.is_alive() and item.is_timeout():
                item.stop()
            if item.is_alive():
                items.append(item)
            else:
                items.append(createHls())
        self.services = items
    def init_services(self):
        #items.append(createHls())
        items.append(createHls())
        self.services = items
    def get_service(self, name):
        for item in self.services:
            if item.source == name:
                return item
        for item in self.services:
            if not item.source:
                item.source = name
                return item
        return None
    def notify_service(self, name, data):
        cli = self.get_service(name)
        if cli:
            cli.post_message({"type":"source", "source":name, "data": data})
            return True
        return False

    # hls-play step: origin is "http://../source.mkv", source.mkv(file) is in self.directory
    # step0: access "http://../source.mkv/index.m38u", this is tempory url.
    # step1: redirect to "http://../hlsvod/source.mkv/index.m38u",
    # step2: access "http://../hlsvod/source.mkv/index.m38u", self.hlsdir + source.mkv(dir) + index.m38u
    # step3: access "http://../hlsvod/source.mkv/segment.ts", self.hlsdir + source.mkv(dir) + segement.ts
    async def check_hls(self, uri, headers):
        path = self.translate_path(uri)
        logging.info("check_hls begin: %s", path)

        ## check workdir default
        fpath = os.path.join(self.workdir, path)
        if os.path.isdir(fpath):
            for index in "index.html", "index.htm":
                index = os.path.join(fpath, index)
                if os.path.exists(index):
                    fpath = index
                    break
            else:
                return self.list_directory(path, fpath)
        if fpath.endswith("/"):
            return web.HTTPNotFound(reason="File not found")
        if os.path.isfile(fpath):
            return self.send_static(fpath, headers)

        ## check hls extensions
        parts = os.path.splitext(fpath)
        if not self.support_exts.get(parts[1]):
            return web.HTTPNotFound(reason="File not found")

        ## check m38u file(step1/step2)
        ## wait m38u update if not modified
        if os.path.basename(path) == self.hlsindex:
            #-- parse source
            pos = path.rfind("/")
            if pos == -1:
                return web.HTTPBadRequest()
            source = path[:pos]
            src_fpath = os.path.join(self.workdir, source)
            dst_fpath = os.path.join(self.hlsdir, source)

            pos = path.find("%s/" % self.hlskey)
            if pos != 0: # no hlskey
                logging.info("check_hls m38u source: %s", source)
                #-- check source info
                if not os.path.exists(src_fpath) or not os.path.isfile(src_fpath):
                    return web.HTTPNotFound(reason="File not found")
                minfo = MediaInfo()
                if not minfo.parse(src_fpath):
                    return web.HTTPUnsupportedMediaType()
                if minfo.isWebDirectSupport():
                    source = os.path.join("/", source)
                    logging.info("check_hls m38u to source: %s", source)
                    return web.HTTPTemporaryRedirect(location=source)

                #TODO:
                bret = self.notify_service(source, {"src": src_fpath, "dst": dst_fpath})
                if not bret:
                    logging.info("check_hls m38u notify failed: %s", source)
                    #if not bret: return web.HTTPTooManyRequests()

                #-- redirect
                path2 = os.path.join(self.hlskey, path)
                path2 = os.path.join("/", path2)
                logging.info("check_hls m38u to redirect: %s", path2)
                return web.HTTPTemporaryRedirect(location=path2)

            m38u = path[len(self.hlskey)+1:]
            m38u_fpath = os.path.join(self.hlsdir, m38u)
            err, mtime = self.read_mtime(m38u_fpath)
            if err != None or not self.check_modified(mtime, headers):
                #TODO:
                bret = self.notify_service(source, {"src": src_fpath, "dst": dst_fpath})
                #if not bret: return web.HTTPTooManyRequests()
                pass
            logging.info("check_hls updated m38u: %s", m38u_fpath)
            return self.send_static(m38u_fpath, headers)

        ## check segement file
        ## wait segment update if not exist
        if path.find("%s/" % self.hlskey) == 0:
            segment = path[len(self.hlskey)+1:]
            seg_fpath = os.path.join(self.hlsdir, segment)

            #-- parse source
            pos = segment.rfind("/")
            source = segment[:pos]
            src_fpath = os.path.join(self.workdir, source)
            dst_fpath = os.path.join(self.hlsdir, source)

            if not os.path.exists(seg_fpath):
                if not os.path.exists(src_fpath) or not os.path.isfile(src_fpath):
                    return web.HTTPNotFound(reason="File not found")
                #TODO:
                bret = self.notify_service(source, {"src": src_fpath, "dst": dst_fpath})
                #if not bret: return web.HTTPTooManyRequests()
                pass
            #logging.info("check_hls ts file:%s", seg_fpath)
            return self.send_static(seg_fpath, headers)
        return web.HTTPBadRequest()

    async def do_File(self, request):
        #logging.info("do_File begin")
        try:
            headers = request.headers
            uri = request.match_info["uri"]
        except:
            uri = ""
        resp = await self.check_hls(uri, headers)
        #print(uri, resp)
        return resp

    def send_static(self, fpath, headers):
        err, mtime = self.read_mtime(fpath)
        if err: return err
        if not self.check_modified(mtime, headers):
            return web.HTTPNotModified()
        headers2 = {}
        headers2["Content-type"] = self.guess_type(fpath)
        headers2["Last-Modified"] = self.date_time_string(mtime)
        return web.FileResponse(path=fpath, headers=headers2, status=200)

    def read_mtime(self, fpath):
        if not os.path.isfile(fpath):
            return web.HTTPNotFound(reason="File not found"), None
        try:
            f = open(fpath, 'rb')
        except OSError:
            return web.HTTPNotFound(reason="File not found"), None
        try:
            rets = [None, None]
            fs = os.fstat(f.fileno())
            rets[1] = fs.st_mtime
        except:
            rets[0] = web.HTTPInternalServerError()
        f.close()
        return rets[0], rets[1]

    def check_modified(self, mtime, headers):
        if not ("If-Modified-Since" in headers and "If-None-Match" not in headers):
            return True
        try:
            ims = email.utils.parsedate_to_datetime(headers["If-Modified-Since"])
        except (TypeError, IndexError, OverflowError, ValueError):
            pass
        else:
            if ims.tzinfo is None:
                ims = ims.replace(tzinfo=datetime.timezone.utc)
            if ims.tzinfo is datetime.timezone.utc:
                last_modif = datetime.datetime.fromtimestamp(mtime, datetime.timezone.utc)
                last_modif = last_modif.replace(microsecond=0)
                return last_modif > ims
        return True

    def parse_dirname(self, path):
        if path.endswith('/'):
            return os.path.dirname(path[:len(path)-1])
        else:
            return os.path.dirname(path)

    def list_directory(self, path, fpath):
        try:
            list = os.listdir(fpath)
        except OSError:
            return web.HTTPNotFound(reason="No permission to list directory")
        list.sort(key=lambda a: a.lower())
        r = []
        try:
            displaypath = urllib.parse.unquote(path, errors='surrogatepass')
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

        if len(path) > 0:
            displayname = ".."
            linkname = self.parse_dirname(path)
            linkname = os.path.join("/", linkname)
            r.append('<li><a href="%s">%s</a></li>'
                    % (urllib.parse.quote(linkname, errors='surrogatepass'),
                       html.escape(displayname, quote=False)))
        for name in list:
            displayname = name
            linkname = name
            if not path.endswith('/'):
                linkname = os.path.join(path, name)
                linkname = os.path.join("/", linkname)
            # Append / for directories or @ for symbolic links
            fullname = os.path.join(fpath, name)
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = linkname + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            r.append('<li><a href="%s">%s</a></li>'
                    % (urllib.parse.quote(linkname, errors='surrogatepass'),
                       html.escape(displayname, quote=False)))
        r.append('</ul>\n<hr>\n</body>\n</html>\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        headers = {}
        headers["Content-type"] = "text/html; charset=%s" % enc
        return web.Response(body=encoded, headers=headers)

    def translate_path(self, uri):
        # abandon query parameters
        uri = uri.split('?',1)[0]
        uri = uri.split('#',1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = uri.rstrip().endswith('/')
        try:
            uri = urllib.parse.unquote(uri, errors='surrogatepass')
        except UnicodeDecodeError:
            uri = urllib.parse.unquote(uri)
        path = posixpath.normpath(uri)
        words = path.split('/')
        words = filter(None, words)
        path = ""
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

    def guess_type(self, fpath):
        base, ext = posixpath.splitext(fpath)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        guess, _ = mimetypes.guess_type(fpath)
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
        web.get(r'/{uri:.*}', handler.do_File),
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
