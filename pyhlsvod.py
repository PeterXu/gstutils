#!/usr/bin/python
# coding=utf-8
# peterxu

## prepare gst-python
## pip3 install aiohttp watchdog

import gc
import os
import sys
import re
import time
import shutil
import datetime
import mimetypes
import posixpath
import pathlib
import logging
import multiprocessing
import threading

import html
import urllib.parse
import email.utils
import _thread as thread

import asyncio
from aiohttp import web
from watchdog.observers import Observer
from watchdog import events

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GLib', '2.0')
gi.require_version('GObject', '2.0')
from gi.repository import Gst, GObject, GLib

try:
    gi.require_version('GstPbutils', '1.0')
    from gi.repository import GstPbutils
except:
    pass
Gst.init(None)

def preload_check():
    preload = os.environ.get("LD_PRELOAD")
    deepfs = os.environ.get("DEEPFS_SO")
    try:
        items = os.listdir("/deepnas/")
    except: items = []
    logging.info(["preload-check:", preload, deepfs, items])


#===== common utils
class CUtil:
    user_agent = "hlsvod/1.0"
    log_path = "/tmp"
    support_exts = {
        '.m3u8': True,
        '.ts':   True,
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
        #'.m3u8': 'application/x-hls',
        '.m3u8': 'application/x-mpegURL',
        '.sh': "text/html",
    }

    @classmethod
    def pyver(cls):
        major = sys.version_info[0]
        minor = sys.version_info[1]
        return major * 10 + minor

    @classmethod
    def tonumber(cls, val, default=None):
        try:
            ret = default
            ret = int(val)
        except: 
            try: ret = float(val)
            except: pass
        return ret

    @classmethod
    def nowtime(cls): #ms
        return int(time.time()*1000)

    @classmethod
    def nowtime_sec(cls): #sec
        return int(time.time())

    @classmethod
    def datetime_string(cls, timestamp=None):
        if timestamp is None: timestamp = time.time()
        return email.utils.formatdate(timestamp, usegmt=True)

    @classmethod
    def touchfile(cls, path):
        tpath = pathlib.Path(path)
        tpath.touch()

    @classmethod
    def parse_dirname(cls, path):
        fpath = path
        if path.endswith('/'): fpath = path[:len(path)-1]
        return os.path.dirname(fpath)

    @classmethod
    def parse_mtime(cls, fname):
        try:
            mtime = 0
            f = open(fname, 'rb')
            try:
                fs = os.fstat(f.fileno())
                mtime = fs.st_mtime
            except:
                mtime = -2
            f.close()
        except:
            mtime = -1
        return mtime

    @classmethod
    def translate_path(cls, uri):
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
        if trailing_slash: path += '/'
        return path

    @classmethod
    def guess_type(cls, fpath):
        base, ext = posixpath.splitext(fpath)
        if ext in cls.extensions_map:
            return cls.extensions_map[ext]
        ext = ext.lower()
        if ext in cls.extensions_map:
            return cls.extensions_map[ext]
        guess, _ = mimetypes.guess_type(fpath)
        if guess: return guess
        return 'application/octet-stream'

    @classmethod
    def set_log_path(cls, path):
        if not path:
            cls.log_path = "/tmp"
            return
        try:
            dpath = os.path.dirname(path)
            if dpath and os.path.exists(dpath):
                os.makedirs(path, exist_ok=True)
                cls.touchfile(path)
                cls.log_path = path
                print("[-] set log path: ", path)
                return
        except:
            pass
        print("[-] fail to set log path:", path)

    @classmethod
    def set_log_file(cls, fname):
        if fname:
            fname = os.path.join(cls.log_path, fname)
        logfmt = '%(asctime)s - [%(levelname)s] - %(message)s'
        datefmt = '%m/%d/%Y %H:%M:%S'
        if cls.pyver() >= 39:
            logging.basicConfig(filename=fname, encoding='utf-8', format=logfmt, datefmt=datefmt, level=logging.INFO)
        else:
            logging.basicConfig(filename=fname, format=logfmt, datefmt=datefmt, level=logging.INFO)
        pass


#===== cache checking
class Cache:
    @classmethod
    def check_size(cls, cpath, maxMB):
        shbin = "M=$(du -sm \"%s\" 2>/dev/null | awk '{print $1}' 2>/dev/null); test $M -gt %s 2>/dev/null" % (cpath, maxMB)
        ret = os.system(shbin)
        return (ret == 0)

    @classmethod
    def clean_size(cls, cpath, name, tosec):
        logging.info(["cache-check", cpath, name, tosec])
        now = CUtil.nowtime_sec()
        items = sorted(pathlib.Path(cpath).glob('**/%s' % name))
        for item in items:
            stat = pathlib.Path(item).stat()
            #logging.info([stat, now, tosec])
            if now >= stat.st_atime + tosec and now >= stat.st_mtime + tosec:
                dname = os.path.dirname(item)
                logging.info(["cache-check, remove", dname])
                shutil.rmtree(dname)
            pass
        pass

    @classmethod
    def check_timeout(cls, cpath, name, maxsize_mb=1024*10, timeout_sec=3600*4):
        if cpath.find("cache") == -1: return
        while timeout_sec >= 3600:
            if not cls.check_size(cpath, maxsize_mb):
                break
            cls.clean_size(cpath, name, timeout_sec)
            timeout_sec = timeout_sec - 3600
        pass


#===== gstreamer tools
class CGst:
    @classmethod
    def set_props(cls, elem, props={}):
        if elem and props:
            for k,v in props.items(): elem.set_property(k, v)

    @classmethod
    def make_elem(cls, name, props={}, alias=None):
        if not name: return None
        elem = Gst.ElementFactory.make(name, alias)
        cls.set_props(elem, props)
        return elem

    @classmethod
    def add_elems(cls, pipeline, elems=[]):
        for e in elems:
            if e: pipeline.add(e)

    @classmethod
    def link_elems(cls, elems, dst=None):
        last = None
        for e in elems:
            if last: last.link(e)
            last = e
        if last and dst: last.link(dst)

    @classmethod
    def set_playing(cls, elems=[]):
        for e in elems:
            if e: e.set_state(Gst.State.PLAYING)

    @classmethod
    def make_filter(cls, fmt): # "video/x-raw", "audio/x-raw"
        caps = Gst.Caps.from_string(fmt)
        return cls.make_elem("capsfilter", {"caps": caps})

    @classmethod
    def check_elem_name(cls, name):
        if cls.make_elem(name): return name
        return None

    @classmethod
    def make_elem_name(cls, name, props={}):
        if len(props) == 0: return name
        items = []
        for k,v in props.items():
            if type(v) == int: items.append("%s=%s" % (k, v))
            else: items.append("%s=\"%s\"" % (k, v))
        return "%s %s" % (name, " ".join(items))

    @classmethod
    def make_queue_name(cls, sinkdelay=0, srcdelay=0):
        if sinkdelay == 0 and srcdelay == 0: return "queue"
        name = cls.check_elem_name("queuex")
        if not name: return "queue"
        props = {}
        if sinkdelay > 0:
            props["min-sink-interval"] = sinkdelay
        if srcdelay > 0:
            props["min-src-interval"] = srcdelay
        return cls.make_elem_name(name, props)

    @classmethod
    def make_vdec_name(cls, vtype, vsize):
        name = None
        if vtype == "video/x-h265" or vtype == "video/x-h264":
            name = cls.check_elem_name("mppvideodec")
            if name and vsize:
                props = {}
                props["format"] = 2
                props["width"] = vsize[0]
                props["height"] = vsize[1]
                name = cls.make_elem_name(name, props)
        if not name: name = "decodebin"
        return name

    @classmethod
    def ts_mux_profile(cls):
        return "video/mpegts,systemstream=true,packetsize=188"

    @classmethod
    def aac_enc_profile(cls, kbps):
        return "audio/mpeg,mpegversion=4,bitrate=%s" % (kbps*1024)

    @classmethod
    def h264_enc_profile(cls, kbps):
        return "video/x-h264,stream-format=byte-stream,bitrate=%s" % (kbps*1024)

    @classmethod
    def audio_props(cls, name, kbps):
        bps = kbps * 1024
        props = {
            "faac": {"bitrate": bps},
            "voaacenc": {"bitrate": bps},
            "avenc_aac": {"bitrate": bps},
        }
        for k, v in props.items():
            if name.find(k) == 0: return v
        return None

    @classmethod
    def video_props(cls, name, kbps, width=0, height=0):
        bps = kbps * 1024
        props1 = {"rc-mode":"vbr", "bps":bps, "profile":"main", "gop":120}
        if width > 0 and height > 0:
            props1["width"] = width
            props1["height"] = height
        props2 = {"pass":"pass1", "bitrate":bps, "profile":"main"}
        props3 = {"pass":"pass1", "bitrate":kbps}
        props = {
            "mpph264enc": props1,
            "avenc_h264_videotoolbox": props2,
            "avenc_h264": props2,
            "x264enc": props3
        }
        for k, v in props.items():
            if name.find(k) == 0: return v
        return None

    @classmethod
    def parse_discover_props(cls, line, key):
        if line.find(key) == -1: return {}
        ret = re.search("%s ([\w/-]+)[,]*(.*)" % key, line)
        if not ret or len(ret.groups()) == 0: return {}
        props = {}
        props["detail"] = line
        props["type"] = ret.groups()[0]
        props["more"] = {}
        if len(ret.groups()) >= 2:
            for item in ret.groups()[1].split(", "):
                pair = item.strip().split("=")
                if len(pair) == 2: props["more"][pair[0]] = pair[1]
        return props

    @classmethod
    def discover_info(cls, fname):
        media = {}
        media["container:"] = "mux"
        media["unknown:"] = "mux"
        media["audio:"] = "audio"
        media["video:"] = "video"

        info = {}
        uri = urllib.parse.urljoin("file://", os.path.abspath(fname))
        shbin = "gst-discoverer-1.0 --use-cache -v \"%s\"" % uri
        lines = os.popen(shbin)
        for line in lines:
            if line.find("Duration: ") >= 0:
                pos = line.find("Duration: ")
                items = line[pos+10:].split(".")[0].split(":")
                if len(items) == 3:
                    info["duration"] = int(items[0])*3600 + int(items[1])*60 + int(items[2])
                continue
            for k,v in media.items():
                if line.find(k) == -1: continue
                props = cls.parse_discover_props(line, k)
                if not props: continue
                v2 = "%s2" % v
                if not info.get(v):
                    info[v] = props
                    info[v2] = []
                else:
                    info[v2].append(props)
        return info

    @classmethod
    def parse_discover_value(cls, item):
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


#===== hls tools
class CHls:
    max_w = 1920
    max_h = 1080

    # @return [min_kbps, max_kbps, width, height]
    @classmethod
    def correct_video_size(cls, width, height, fps=24):
        if width > cls.max_w:
            height = int(height * cls.max_w / width / 4) * 4
            width = cls.max_w
        if height > cls.max_h:
            width = int(width * cls.max_h / height / 4) * 4
            height = cls.max_h
        if fps <= 0: fps = 20
        elif fps >= 30: fps = 30
        kbps = [300, 600]
        pixels = width * height
        if pixels >= 1920*1080: kbps = [1500, 2500]
        elif pixels >= 1280*720: kbps = [800, 1800]
        elif pixels >= 960*540: kbps = [600, 1000]
        info = []
        info.append(int(kbps[0] * fps / 24))
        info.append(int(kbps[1] * fps / 24))
        info.append(width)
        info.append(height)
        return info

    @classmethod
    def parse_prop(cls, line, default=None):
        pos1 = line.find(":")
        if pos1 < 0: return default
        pos2 = line.find(",", pos1+1)
        if pos2 >= 0:
            val = line[pos1+1:pos2]
        else:
            val = line[pos1+1:]
        return CUtil.tonumber(val, default)

    @classmethod
    def parse_segment(cls, line, default=None):
        try:
            ret = re.search("hls_segment_(\d+).ts", line)
            return int(ret.groups()[0])
        except: pass
        return default

    @classmethod
    def segment_name(cls, seq=-1):
        if seq == -1: return "hls_segment_%06d.ts"
        return "hls_segment_%06d.ts" % seq

    @classmethod
    def get_begin(cls, seconds):
        lines = []
        lines.append("#EXTM3U\n")
        lines.append("#EXT-X-VERSION:6\n")
        lines.append("#EXT-X-ALLOW-CACHE:NO\n")
        lines.append("#EXT-X-MEDIA-SEQUENCE:0\n")
        lines.append("#EXT-X-TARGETDURATION:%d\n" % (seconds+1))
        lines.append("#EXT-X-PLAYLIST-TYPE:VOD\n")
        lines.append("#EXT-X-START:TIME-OFFSET=0\n")
        lines.append("\n")
        return "".join(lines)

    @classmethod
    def get_one(cls, segment, seconds):
        lines = []
        if type(seconds) == float:
            lines.append("#EXTINF:%.2f,\n" % seconds)
        else:
            lines.append("#EXTINF:%d,\n" % int(seconds))
        lines.append("%s\n" % segment)
        return "".join(lines)

    @classmethod
    def get_end(cls):
        return "#EXT-X-ENDLIST"


#========== file monitor
class MediaMonitor(events.FileSystemEventHandler):
    def __init__(self, bname):
        self.bname = bname
        self.observer = None
        self.last_path = None
        self.last_lines = []
        self.cb_changed = None
        pass
    def on_any_event(self, evt):
        #logging.info(["mon", evt])
        pass
    def on_moved(self, evt):
        self.check_path_modified(evt.dest_path)

    def check_path_modified(self, fname):
        if not os.path.isfile(fname): return
        if os.path.basename(fname) != self.bname: return
        fp = open(fname, "r")
        if not fp: return
        new_lines = fp.readlines()
        fp.close()

        result = []
        old_number = len(self.last_lines)
        if old_number == 0 or old_number > len(new_lines):
            result = new_lines
        else:
            lines = new_lines[:old_number]
            if self.last_lines == lines:
                result = new_lines[old_number:]
            else:
                theSame = True
                for idx in range(old_number):
                    if lines[idx] != self.last_lines[idx]:
                        if lines[idx].find("#EXT-X-MEDIA-SEQUENCE") == 0:
                            continue
                        if lines[idx].find("#EXT-X-TARGETDURATION") == 0:
                            continue
                        theSame = False
                        break
                if theSame:
                    result = new_lines[old_number:]
                else:
                    logging.info(["mon different", fname, new_lines, self.last_lines])
                    result = new_lines
        #logging.info(["mon changed:", fname, len(self.last_lines), len(new_lines), result])
        self.last_lines = new_lines
        if self.cb_changed:
            self.cb_changed(self.last_path, result)
        pass
    def start(self, path, cb):
        self.last_path = path
        self.last_lines = []
        self.cb_changed = cb
        try:
            self.observer = Observer()
            self.observer.schedule(self, path, recursive=False)
            self.observer.start()
        except:
            self.stop()
    def stop(self):
        self.cb_changed = None
        if not self.observer: return
        try:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        except:
            pass


#======== processing m3u8
class MediaExtm3u8(object):
    def __init__(self):
        self.fp = None
        self.fpath = None
        self.last_seq = -1
        self.sdur = 0 #segment seconds
        self.is_begin = False
        self.is_end = False
        self.probe_pos = 0
        self.duration = 0 # total seconds
    def _init(self):
        self.last_seq = -1
        self.sdur = 0
        self.is_begin = False
        self.is_end = False
        self.probe_pos = 0
        self.duration = 0
    def parse(self, path):
        self._init()
        fname = os.path.join(path, "index.m3u8")
        if os.path.isfile(fname):
            try:
                fp = open(fname, "r")
                lines = fp.readlines()
                fp.close()
                if self._parse(lines, 0, False):
                    self.fpath = path
                    return True
            except:
                pass
            self._init()
        return False
    def open(self, path, seconds):
        if self.fp: return False
        if seconds <= 0: return False
        fp = None
        fname = os.path.join(path, "index.m3u8")
        if os.path.isfile(fname):
            try:
                self._init()
                fp = open(fname, "r+")
                lines = fp.readlines()
                if not self._parse(lines, seconds):
                    logging.warning("extm3u, discard this m3u8")
                    fp.close()
                    fp = None
            except:
                pass
        if not fp:
            try:
                self._init()
                fp = open(fname, "w")
            except:
                return False
        self.fp = fp
        self.fpath = path
        self.sdur = seconds
        return True
    def write(self, name, seconds):
        if not self.fp: return False
        if self.is_end: return False
        if not self.is_begin:
            self.fp.write(CHls.get_begin(self.sdur))
            self.is_begin = True
        self.fp.write(CHls.get_one(name, seconds))
        self.fp.flush()
    def next_name(self):
        self.last_seq += 1
        name = CHls.segment_name(self.last_seq)
        return name, os.path.join(self.fpath, name)
    def curr_seq(self):
        return self.last_seq
    def curr_dur(self):
        if self.last_seq < 0: return 0
        return (self.last_seq + 1) * self.sdur - 1
    def is_complete(self):
        return self.curr_dur() >= self.duration
    def index_path(self):
        fname = None
        if self.fpath:
            fname = os.path.join(self.fpath, "index.m3u8")
        return fname

    def close(self):
        if self.fp:
            self.fp.close()
            self.fp = None
    def closeEnd(self):
        if self.fp:
            self.fp.write(CHls.get_end())
            self.is_end = True
        self.close()

    def fakeLiveContent(self):
        try:
            fp = open(self.index_path(), "r")
            fdata = fp.read()
            fp.close()
        except:
            return None
        return fdata.replace("#EXT-X-PLAYLIST-TYPE:VOD", "#EXT-X-PLAYLIST-TYPE:EVENT")
    def fakeVlcContent(self, seconds, duration):
        maxSeq = int(duration/seconds + 0.9)
        logging.info(["fakeVlc, total-duration", duration, maxSeq])
        if maxSeq > 0:
            return self.fakeVodContent(seconds, maxSeq)
        else:
            return self.fakeLiveContent()
    def fakeVodContent(self, seconds, maxSeq=3):
        lines = []
        lines.append(CHls.get_begin(seconds))
        for i in range(maxSeq):
            name = CHls.segment_name(i)
            lines.append(CHls.get_one(name, seconds))
        return "".join(lines)

    def _parse(self, lines, seconds, strongCheck=True):
        last_pos = 0
        last_seq = -1
        isSeg = False
        for line in lines:
            if line.find("#EXTM3U") == 0:
                self.is_begin = True
            elif line.find("#EXT-X-ENDLIST") == 0:
                self.is_end = True
            elif line.find("#EXT-X-TARGETDURATION:") == 0:
                self.sdur = CHls.parse_prop(line, 0)
            elif line.find("#EXTINF:") == 0:
                isSeg = True
                last_pos += CHls.parse_prop(line, 0)
                continue
            elif len(line.strip()) == 0 or line[0] == "#":
                continue
            if isSeg:
                isSeg = False
                seq = CHls.parse_segment(line, None)
                if seq is None:
                    logging.warning("extm3u, invalid segment seq")
                    return False
                if seq != 0 and seq != last_seq + 1:
                    logging.warning("extm3u, segment seq not continous: %d", seq)
                    return False
                last_seq = seq
        if not self.is_begin:
            logging.warning("extm3u, no begin and restart")
            return False
        self.probe_pos = last_pos
        self.last_seq = last_seq
        if not strongCheck:
            return True

        if self.sdur < seconds:
            logging.warning("extm3u, different sdur")
            #return False
        if not self.is_end:
            if last_seq < 3:
                logging.warning(["extm3u, reset when few segments", last_seq])
                return False
            if last_pos > 0:
                logging.info(["extm3u, continue to last pos", last_pos, last_seq])
                return True
            return False
        logging.info("extm3u, last ended and nop again!")
        self.probe_pos = 0
        return True


#========= processing media files
class MediaInfo(object):
    def __init__(self):
        self.minfo_time = CUtil.nowtime_sec()
        self.infile = ''
        self.info = {}

    def mediaType(self, kind): #mux/audio/video
        return self.info.get(kind, {}).get("type", None)
    def muxType(self):
        return self.mediaType("mux")
    def audioType(self):
        return self.mediaType("audio")
    def videoType(self):
        return self.mediaType("video")

    def fileSize(self):
        return self.info.get("filesize", 0)
    def duration(self):
        return self.info.get("duration", 0)
    def bitrate(self):
        return self.info.get("bitrate", 0)

    def frameRate(self):
        value = self.info.get("video", {}).get("more", {}).get("framerate", 0)
        if type(value) == int: return value
        return CGst.parse_discover_value(value)
    def width(self):
        value = self.info.get("video", {}).get("more", {}).get("width", 0)
        if type(value) == int: return value
        return CGst.parse_discover_value(value)
    def height(self):
        value = self.info.get("video", {}).get("more", {}).get("height", 0)
        if type(value) == int: return value
        return CGst.parse_discover_value(value)

    def isWebDirectSupport(self):
        mux = self.muxType()
        if mux == "video/quicktime" or mux == "application/x-3gp" or mux == "audio/x-m4a":
            audio = self.audioType()
            video = self.videoType()
            if audio != None and audio != "audio/mpeg": return False
            if video != None and video != "video/x-h264": return False 
            if self.fileSize() <= 11*1024*1024:
                return True
        return False

    def parse(self, infile):
        info = CGst.discover_info(infile)
        if not info:
            logging.warning("minfo, no info")
            return False
        self.infile = infile
        self.info = info
        if self.duration() == 0:
            logging.warning("minfo, no total-duration")
            return False
        if not self.videoType() and not self.audioType():
            logging.warning("minfo, no audio and video")
            return False
        try:
            fp = open(infile, "rb")
            try:
                fs = os.fstat(fp.fileno())
                bps = fs.st_size * 8 / self.duration()
                info["filesize"] = fs.st_size
                info["bitrate"] = int(bps)
            except:
                pass
            fp.close()
        except:
            pass
        #print(info)
        #logging.info(["coder media:", info])
        if self.videoType():
            fps = self.frameRate()
            width = self.width()
            height = self.height()
            if fps == 0 or width == 0 or height == 0:
                return False
            logging.info(["minfo, have video", width, height, fps])
        else:
            logging.info("minfo, no video")
        return True


class Transcoder(object):
    def __init__(self):
        self.mutex = threading.Lock()
        self.working = 0
        self.state = -1
        self.loop = None
        self.pipeline = None
        self.pipeline2 = None
        self.start_pos = 0
        pass

    def outdated(self):
        return self.working == -1

    def do_hlsvod(self, infile, outpath, inpos, sdur):
        logging.info("gst-coder, %s - %s, start: %s, segment-time: %d", infile, outpath, inpos, sdur)
        # output
        outfile = os.path.join(outpath, "index.ts")
        playlist = os.path.join(outpath, "playlist.m3u8")
        segment = os.path.join(outpath, CHls.segment_name())
        options = {
            "max-files": 1000000,
            "target-duration": sdur,
            "playlist-length": 0,
            "playlist-location": playlist,
            "location": segment,
        }
        sink = CGst.make_elem_name("hlssink", options)

        self.start_pos = int(inpos)
        self.working = 1
        self.do_work(infile, 64, 1024, sink)
        self.working = -1

    def do_work(self, infile, akbps, vkbps, sink):
        minfo = MediaInfo()
        if not minfo.parse(infile):
            logging.warning(["gst-coder, invalid media file:", infile])
            return

        mType = minfo.muxType()
        aType = minfo.audioType()
        vType = minfo.videoType()
        vSize = None
        vDec = None
        if vType:
            vSize = CHls.correct_video_size(minfo.width(), minfo.height(), minfo.frameRate())
            if vkbps > vSize[1]: vkbps = vSize[1]
            elif vkbps < vSize[0]: vkbps = vSize[0]
            vDec = CGst.make_vdec_name(vType, vSize[2:])
        logging.info(["gst-coder, media-type:", mType, aType, vType, vkbps, vSize, vDec])

        mux = CGst.ts_mux_profile()
        aac = CGst.aac_enc_profile(akbps)
        avc = CGst.h264_enc_profile(vkbps)
        logging.info(["gst-coder, elems=", mux, avc, aac])
        profile = "%s:%s:%s" % (mux, avc, aac)

        #pipeline1
        parts1 = []
        parts1.append("filesrc location=\"%s\" name=fs" % infile)
        parts1.append("parsebin name=pb")
        if vType: parts1.append("proxysink name=psink0")
        if aType: parts1.append("proxysink name=psink1")
        parts1.append("fs. ! pb.")
        if vType: parts1.append("pb. ! %s ! queue ! psink0." % vType)
        if aType: parts1.append("pb. ! %s ! queue ! psink1." % aType)
        sstr1 = " ".join(parts1)
        logging.info(["gst-coder, pipeline1:", sstr1])
        p1 = Gst.parse_launch(sstr1)
        psink0 = p1.get_by_name("psink0")
        psink1 = p1.get_by_name("psink1")
        logging.info(["gst-coder, pipeline1 ret:", p1])

        #pipelin2
        parts2 = []
        if vType:
            parts2.append("proxysrc name=psrc0")
            parts2.append("%s name=db0" % vDec)
        if aType:
            parts2.append("proxysrc name=psrc1")
            parts2.append("decodebin name=db1")
        parts2.append("encodebin profile=\"%s\" name=eb" % profile)
        #parts2.append("filesink location=/tmp/test3.ts name=fs")
        parts2.append("%s name=fs" % sink)

        if vType:
            queue = CGst.make_queue_name(0, 0)
            parts2.append("psrc0. ! queue ! db0.")
            parts2.append("db0. ! video/x-raw ! %s ! eb.video_0" % queue)
        if aType:
            queue = CGst.make_queue_name(0, 0)
            parts2.append("psrc1. ! db1.")
            parts2.append("db1. ! audio/x-raw ! %s ! eb.audio_0" % queue)

        queue = CGst.make_queue_name(3000, 0)
        parts2.append("eb. ! %s ! fs." % queue)
        sstr2 = " ".join(parts2)
        logging.info(["gst-coder, pipeline2:", sstr2])
        p2 = Gst.parse_launch(sstr2)
        psrc0 = p2.get_by_name("psrc0")
        psrc1 = p2.get_by_name("psrc1")
        eb = p2.get_by_name("eb")
        logging.info(["gst-coder, pipeline2 ret:", p2, eb])

        # config encodebin
        if eb:
            logging.info(["gst-coder, eb count:", eb.get_children_count()])
            for i in range(eb.get_children_count()):
                e = eb.get_child_by_index(i)
                props = None
                if aType:
                    props = CGst.audio_props(e.get_name(), akbps)
                if not props and vSize:
                    props = CGst.video_props(e.get_name(), vkbps, vSize[2], vSize[3])
                if props:
                    logging.info(["gst-coder, eb set-props:", e.get_name(), props])
                    CGst.set_props(e, props)
                else:
                    logging.info(["gst-coder, eb skip set-props:", e.get_name()])

        # connect p1 and p2
        #GObject.set(psrc, "proxysink", psink, NULL);
        if psrc0 and psink0: psrc0.set_property('proxysink', psink0)
        if psrc1 and psink1: psrc1.set_property('proxysink', psink1)
    
        # set clock and time
        clock = Gst.SystemClock.obtain()
        p1.use_clock(clock)
        p2.use_clock(clock)
        clock.unref()
        p1.set_base_time(0)
        p2.set_base_time(0)

        # set p1 as default pipeline
        logging.info("gst-coder, set playing..., start: %s", self.start_pos)
        self.pipeline = p1
        self.pipeline2 = p2
        p1.set_state(Gst.State.PLAYING)
        p2.set_state(Gst.State.PLAYING)
        self.do_seek(p1, self.start_pos)
        self.check_message(p2)
        self.check_run(p1)
        p1.set_state(Gst.State.NULL)
        p2.set_state(Gst.State.NULL)

    def do_stop(self):
        if self.loop and self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline2.set_state(Gst.State.NULL)
            self.loop.quit()
        self.pipeline = None
        self.pipeline2 = None
        self.loop = None

    def do_pause(self):
        if self.loop and self.pipeline:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.state = int(Gst.State.PAUSED)

    def do_eos(self, pline):
        if not pline: pline = self.pipeline
        if pline: pline.send_event(Gst.Event.new_eos())

    def do_seek(self, pline, steps):
        if not pline: pline = self.pipeline
        if not pline: return
        steps = steps - 3
        if steps <= 0: return
        logging.info(["gst-coder, seek:", pline, steps])
        pline.set_state(Gst.State.PAUSED)
        pline.get_state(Gst.CLOCK_TIME_NONE)
        time.sleep(0.5)
        event = Gst.Event.new_seek(1.0, Gst.Format.TIME, Gst.SeekFlags.FLUSH|Gst.SeekFlags.KEY_UNIT,
                Gst.SeekType.SET, steps * Gst.SECOND, Gst.SeekType.NONE, -1)
        pline.send_event(event)
        pline.get_state(Gst.CLOCK_TIME_NONE)
        time.sleep(1)
        logging.info("gst-coder, seek end")

    # VOID_PENDING:0, NULL:1, READY:2, PAUSED:3, PLAYING:4
    def get_state(self):
        return self.state

    def check_message(self, pline=None):
        if not pline: pline = self.pipeline
        if not pline: return
        bus = pline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

    def check_run(self, pline=None):
        if not pline: pline = self.pipeline
        if not pline: return
        self.loop = GLib.MainLoop()
        ret = pline.set_state(Gst.State.PLAYING)
        self.state = int(Gst.State.PLAYING)
        logging.info("gst-coder, run begin")
        try:
            self.loop.run()
        except Exception as e:
            logging.warning("gst-coder, run error=%s", e);
        else:
            logging.info("gst-coder, run end");
        self.state = int(Gst.State.NULL)
        pass

    def on_message(self, bus, msg):
        #logging.info("message: %s", msg.type)
        pline = self.pipeline
        if msg.type == Gst.MessageType.EOS:
            logging.info("gst-coder, message EOS and quit")
            self.do_stop()
        elif msg.type == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            logging.info(["gst-coder, message Error:", err, debug])
            self.do_stop()
        elif msg.type == Gst.MessageType.STATE_CHANGED:
            pass
        elif msg.type == Gst.MessageType.DURATION_CHANGED:
            value = -1
            ok, pos = pline.query_duration(Gst.Format.TIME)
            if ok: value = int(float(pos) / Gst.SECOND)
            logging.info(["gst-coder, total-duration:", value])
        pass


#======= sub-process hls-service(backend)
class HlsMessage:
    def __init__(self, mtype, name, fsrc=None, fdst=None):
        self.mtype = mtype
        self.name = name
        self.fsrc = fsrc
        self.fdst = fdst

        self.sdur = 10 #segment seconds
        self.quality = "default" #low/medium/high
        self.result = None
    def debugStr(self):
        return "%s:%s:%s:%s" % (self.mtype, self.name, self.fsrc, self.fdst)
    def str(self):
        return "%s:%s" % (self.mtype, self.name)

class HlsService:
    def __init__(self, conn):
        self.mutex = threading.Lock()
        self.conn = conn
        self.coder = None
        self.source = None
        self.monitor = None
        self.extm3u8 = None
        self.last_coder_time = 0
        self.timeout = 21*1000
        pass

    def _reset(self):
        self.coder = None
        self.source = None
        if self.monitor:
            self.monitor.stop()
            self.monitor = None
        if self.extm3u8:
            self.extm3u8.close()
            self.extm3u8 = None
        self.last_coder_time = 0

    def _loop(self, coder, fsrc, fdst, fpos, sdur):
        try:
            logging.info("hls-srv, loop begin...")
            coder.do_hlsvod(fsrc, fdst, fpos, sdur)
        except Exception as e:
            logging.warning("hls-srv, loop error: %s", e)
        except:
            logging.warning("hls-srv, loop other error")
        else:
            logging.info("hls-srv, loop end")

    def get_coder(self):
        if self.coder and self.coder.outdated():
            self._reset()
        return self.coder

    def is_coder_alive(self):
        coder = self.get_coder()
        if coder: return True
        return False

    def is_coder_timeout(self):
        if self.last_coder_time != 0:
            return CUtil.nowtime() >= self.last_coder_time + self.timeout
        return False

    def stop_coder(self):
        coder = self.get_coder()
        if coder:
            logging.info("hls-srv, coder stop...")
            coder.do_stop()
        self._reset()
        gc.collect()

    def start_coder(self, source, fsrc, fdst, sdur):
        minfo = MediaInfo()
        if not minfo.parse(fsrc):
            return False

        # final destination
        extm = MediaExtm3u8()
        if not extm.open(fdst, sdur):
            return False
        if extm.is_end:
            logging.info("hls-srv, coder had end and nop")
            extm.close()
            return False
        extm.duration = minfo.duration()
        self.extm3u8 = extm
        self.source = source

        self.timeout = 21*1000
        if minfo.videoType() == "video/x-h265":
            self.timeout = 31*1000

        # tmp destination for transcoder
        fdst_tmp = os.path.join(fdst, "cached");
        try:
            if os.path.isdir(fdst_tmp):
                shutil.rmtree(fdst_tmp)
            os.makedirs(fdst_tmp, exist_ok=True)
        except: pass
        if not os.path.isdir(fdst_tmp):
            logging.warning(["hls-srv, create cache failed", fdst_tmp])
            return False
        mmon = MediaMonitor("playlist.m3u8")
        mmon.start(fdst_tmp, self.on_mon_changed)
        self.monitor = mmon

        self.last_coder_time = CUtil.nowtime()
        self.coder = Transcoder()
        fpos = extm.probe_pos
        logging.info("hls-srv, coder start, pos=%s", fpos)
        thread.start_new_thread(self._loop, (self.coder, fsrc, fdst_tmp, fpos, sdur))
        logging.info("hls-srv, coder end...")

    def on_mon_changed(self, path, lines):
        extm = self.extm3u8
        if not extm:
            logging.error("hls-srv, changed but invalid extm3u8")
            return

        isSeg = False
        seconds = 0
        for line in lines:
            if line.find("#EXT-X-TARGETDURATION:") == 0:
                #extm.sdur = CHls.parse_prop(line, 0)
                continue
            elif line.find("#EXT-X-ENDLIST") == 0:
                logging.info("hls-srv, changed with segment, dur: %d-%d", extm.curr_dur(), extm.duration)
                if extm.is_complete():
                    extm.closeEnd()
                break
            elif line.find("#EXTINF:") == 0:
                isSeg = True
                seconds = CHls.parse_prop(line, 0)
                if seconds > (extm.duration + 1):
                    logging.warning("hls-srv, invalid segment dur: %d-%d", seconds, extm.duration)
                    seconds = 0.1
                continue
            elif len(line.strip()) == 0 or line[0] == "#":
                continue
            if isSeg:
                isSeg = False
                srcf = os.path.join(path, line.strip())
                name, dstf = extm.next_name()
                logging.info("hls-srv, changed new-segment: <%s> from %s", name, line)
                try:
                    shutil.move(srcf, dstf)
                except: pass
                extm.write(name, seconds)
            else:
                logging.warning("hls-srv, changed invalid new-segment: %s", line)
                pass
            pass
        os.sync()
        pass

    def prepare_coder(self, source, fsrc, fdst, sdur):
        if sdur < 5: sdur = 5
        if not source or not fsrc or not fdst:
            logging.warning("hls-srv, invalid coder args")
            return False
        if not os.path.isfile(fsrc):
            logging.warning("hls-srv, src not exist: %s", fsrc)
            return False
        if not os.path.exists(fdst):
            os.makedirs(fdst, exist_ok=True)
        elif os.path.isfile(fdst):
            logging.warning("hls-srv, dst is file: %s", fdst)
            return False
        if self.is_coder_alive():
            if source != self.source:
                logging.warning("hls-srv, another working: %s", self.source)
                return False
            self.last_coder_time = CUtil.nowtime()
            return True
        ret = self.start_coder(source, fsrc, fdst, sdur)
        return ret

    def on_hls_message(self, msg):
        if not msg:
            logging.warning("hls-srv, invalid msg: %s", msg.debugStr())
            return
        logging.info("hls-srv, recv message: %s", msg.str())
        resp = HlsMessage("ack", msg.name)
        if self.prepare_coder(msg.name, msg.fsrc, msg.fdst, msg.sdur):
            resp.result = True
        else:
            resp.result = False
        self.conn.send(resp)
        pass

    def run_forever(self):
        while True:
            try:
                ret = self.conn.poll(1)
                if ret:
                    msg = self.conn.recv()
                    self.on_hls_message(msg)
            except Exception as e:
                logging.warning(["hls-srv, poll err and quit:", e])
                break
            except:
                logging.warning("hls-srv, poll other err and quit")
                break

            try:
                #logging.info("hls-srv, coder checking...")
                if self.is_coder_alive() and self.is_coder_timeout():
                    logging.warning("hls-srv, coder timeout...")
                    self.stop_coder()
                self.conn.send(HlsMessage("status", self.source))
            except:
                pass
        self.stop_coder()
        time.sleep(0.5)
        pass
    pass


def run_hls_service(conn, index):
    CUtil.set_log_path("/var/log/hlsvod")
    CUtil.set_log_file("hls_service_%d.txt" % index)
    logging.info("=====================\n\n")
    logging.info(["run_hls_service begin, pid", os.getpid(), os.getppid()])
    preload_check()
    hls = HlsService(conn)
    hls.run_forever()
    conn.close()


#======== parent-process hls-client
class HlsClient:
    def __init__(self, conn, child):
        self.mutex = threading.Lock()
        self.alive = True
        self.conn = conn
        self.child = child
        self.source = None
        self.tmp_source = None
        self.last_backend_time = CUtil.nowtime()
        self.last_up_time = CUtil.nowtime_sec()  #sec

    def no_focus(self):
        return (self.source is None) and (self.tmp_source is None)
    def in_focus(self, name):
        if name == self.source or name == self.tmp_source:
            return True
        return False
    def set_focus(self, name):
        if name != self.source:
            self.tmp_source = name

    def set_alive(self, state):
        self.mutex.acquire()
        self.alive = state
        self.mutex.release()

    def is_alive(self):
        self.mutex.acquire()
        state = self.alive
        self.mutex.release()
        return state

    def is_backend_timeout(self):
        return CUtil.nowtime() >= self.last_backend_time + 3000

    def is_up_timeout(self):
        return CUtil.nowtime_sec() >= self.last_up_time + 3600*24

    def post_message(self, msg):
        self.conn.send(msg)

    def on_backend_message(self, msg):
        self.last_backend_time = CUtil.nowtime()
        if not msg:
            logging.info(["hls-cli, invalid msg:", msg])
            return
        #logging.info(["hls-cli, recv msg:", msg])
        if msg.mtype == "status" or msg.result is True:
            #logging.info(["hls-cli, recv update:", msg.name])
            self.source = msg.name
            self.tmp_source = None
        if msg.result is False:
            #logging.info(["hls-cli, recv error:", msg.name])
            if msg.name == self.tmp_source:
                self.tmp_source = None
        pass

    def start(self):
        self.set_alive(True)
        thread.start_new_thread(self._service, ())
        thread.start_new_thread(self._listen, ())

    def stop(self):
        self.conn.close()
        self.set_alive(False)
        self.child.kill()

    def _service(self):
        logging.info("hls-cli, run backend begin")
        self.child.join()
        self.set_alive(False)
        logging.info("hls-cli, run backend end")

    def _listen(self):
        while self.alive:
            try:
                ret = self.conn.poll(1)
                if ret:
                    msg = self.conn.recv()
                    self.on_backend_message(msg)
            except Exception as e:
                logging.info(["hls-cli, poll err:", e])
                break
        pass

def createHls(index):
    logging.info(["hls-cli, create hls-backend, self", os.getpid()])
    ctx = multiprocessing.get_context('spawn')
    p1, p2 = ctx.Pipe(True)
    srv = ctx.Process(target=run_hls_service, args=(p1, index))
    srv.start()
    cli = HlsClient(p2, srv)
    cli.start()
    return cli

class HlsCenter:
    def __init__(self, dstPath, count):
        self.mutex = threading.Lock()
        self.dstPath = dstPath
        self.count = count
        self.services = []
        self.ploop = None
        self.minfos = {}
        pass

    def _checking(self, p):
        while True:
            try:
                ret = p.poll(1800)
            except:
                ret = True
            if ret:
                logging.warning("cache, pipe error or closed")
                break
            try:
                #TODO: thread security
                Cache.check_timeout(self.dstPath, "index.m3u8", 1024*20, 3600*24)
                self.clear_minfo(3600*4)
            except:
                pass
        p.close()
        pass
    def _start_loop(self):
        p1, p2 = multiprocessing.Pipe(True)
        thread.start_new_thread(self._checking, (p1, ))
        self.ploop = p2
    def _stop_loop(self):
        if self.ploop:
            self.ploop.close()
            self.ploop = None

    def init_services(self):
        self._start_loop()
        items = []
        for idx in range(self.count):
            items.append(createHls(idx))
        self.services = items
        time.sleep(1)
    def stop_services(self):
        self._stop_loop()
        for item in self.services:
            item.stop()
        self.services = []
        time.sleep(1)
    def check_services(self):
        items = []
        for idx in range(self.count):
            item = self.services[idx]
            if item.is_backend_timeout():
                logging.info("hls-center, one service timeout and stop")
                item.stop()
            elif item.no_focus() and item.is_up_timeout():
                logging.info("hls-center, one service up-timeout and stop")
                item.stop()
            if item.is_alive():
                items.append(item)
            else:
                logging.info("hls-center, one service not alive and restart")
                items.append(createHls(idx))
                time.sleep(1)
        self.services = items
    def get_service(self, name):
        self.check_services()
        if not name: return None
        for item in self.services:
            if item.in_focus(name): return item
        for item in self.services:
            if item.no_focus(): return item
        return None
    def post_service(self, msg):
        cli = self.get_service(msg.name)
        if cli:
            cli.set_focus(msg.name)
            cli.post_message(msg)
            return True
        return False

    def get_minfo(self, name):
        self.mutex.acquire()
        info = self.minfos.get(name)
        self.mutex.release()
        return info
    def set_minfo(self, name, minfo):
        self.mutex.acquire()
        self.minfos[name] = minfo
        self.mutex.release()
    def clear_minfo(self, sec=100):
        self.mutex.acquire()
        now = CUtil.nowtime_sec()
        timeouts = []
        for k,v in self.minfos.items():
            if now >= v.minfo_time + sec:
                timeouts.append(k)
        for k in timeouts:
            self.minfos.pop(k)
        self.mutex.release()
        pass


#======== parent-process web
class MyHTTPRequestHandler:
    def __init__(self, srcPath=None, dstPath=None, maxCount=0):
        if srcPath is None:
             srcPath = os.getcwd()
        self.workdir = os.fspath(srcPath)
        if dstPath is None:
            dstPath = "/tmp/cached"
        self.hlsdir = os.fspath(dstPath)
        if maxCount <= 0:
            maxCount = 1
        self.hlscenter = HlsCenter(dstPath, maxCount)
        self.hlskey = "hlsvod"

    def init(self):
        self.hlscenter.init_services()
        pass
    def uninit(self):
        self.hlscenter.stop_services()
        pass

    # hls-play:
    #   http://../source.mkv, http://../source.mkv/index.m3u8, http://../source.mkv/segment.ts
    # step0: check "." + source.mkv,
    # step1: check self.workdir + source.mkv
    # step2: check self.hlsdir + source.mkv/index.m3u8
    # step3: check self.hlsdir + source.mkv/segment.ts
    async def check_hls(self, request, uri):
        headers = request.headers
        agent = headers.get("User-Agent")
        raddr = self.get_raddr(request)
        prefix = "%s/" % self.hlskey
        opath = CUtil.translate_path(uri)

        path = opath
        pos_prefix = opath.find(prefix)
        if pos_prefix == 0:
            path = opath[len(prefix):]
        cpath = os.path.join(".", path)
        fpath = os.path.join(self.workdir, path)
        bname = os.path.basename(path)
        logging.info(["webhandler, begin:", uri, raddr, agent])

        ## check curr file/dir
        if os.path.isdir(cpath):
            for index in "index.html", "index.htm":
                index = os.path.join(cpath, index)
                if os.path.isfile(index):
                    cpath = index
                    break
            else:
                return self.list_directory(opath, cpath)
        if os.path.isfile(cpath):
            return self.send_static(cpath, headers)
        if bname == "favicon.ico":
            return web.HTTPNotFound(reason="File not found")

        ## check workdir(media source)
        if fpath.endswith("/") or os.path.isdir(fpath):
            return web.HTTPNotFound(reason="File not found")
        if os.path.isfile(fpath):
            return self.send_static(fpath, headers)

        ## --- check hlsvod ---

        ## check extensions
        parts = os.path.splitext(path)
        if not CUtil.support_exts.get(parts[1]):
            logging.warning(["webhandler, unsupport media ext: ", path])
            return web.HTTPNotFound(reason="File not found")

        ## check source
        pos = path.rfind("/")
        if pos == -1:
            logging.warning(["webhandler, no base name(/):", path])
            return web.HTTPBadRequest()
        source = path[:pos]
        src_fpath = os.path.join(self.workdir, source)
        dst_fpath = os.path.join(self.hlsdir, source)
        if not os.path.isfile(src_fpath):
            logging.warning(["webhandler, hls source not exist:", src_fpath])
            return web.HTTPNotFound(reason="Source file not found")
        user_fpath = os.path.join(self.hlsdir, path)
        message = HlsMessage("prepare", source, src_fpath, dst_fpath)
        #logging.info(["webhandler, hls source:", source, bname, user_fpath])

        # send direct if exist
        hextm = MediaExtm3u8()
        hextm.parse(dst_fpath)
        if hextm.is_end:
            try: CUtil.touchfile(hextm.index_path())
            except: pass
            # TODO: how to process playlist complete but segment not exists??
            return self.send_static(user_fpath, headers)

        ## check media info
        #self.hlscenter.clear_minfo()
        minfo = self.hlscenter.get_minfo(source)
        if not minfo:
            logging.info(["webhandler, first to parse media info...", path])
            minfo = MediaInfo()
            if not minfo.parse(src_fpath):
                logging.warning(["webhandler, m3u8 unsupport media:", path])
                return web.HTTPUnsupportedMediaType()
            if minfo.isWebDirectSupport():
                mpath = os.path.join("/%s" % prefix, source)
                logging.info(["webhandler, m3u8 redirect to media:", mpath])
                return web.HTTPTemporaryRedirect(location=mpath)
            self.hlscenter.set_minfo(source, minfo)

        ## post to service
        bpost = self.hlscenter.post_service(message)
        logging.info(["webhandler, prepare:", bpost, path, hextm.curr_seq()])

        ## check segment directly
        seg_fpath = user_fpath
        if bname != "index.m3u8":
            if not os.path.isfile(seg_fpath) and not bpost:
                logging.warning(["webhandler, segment prepare failed:", path])
                return web.HTTPTooManyRequests()
            stime = 1
            if not os.path.isfile(seg_fpath) and agent.find("VLC/") != -1:
                stime = 2
            await asyncio.sleep(stime)
            return self.send_static(seg_fpath, headers)

        ## check m3u8 at the first time
        m3u8_fpath = user_fpath
        if not os.path.exists(m3u8_fpath):
            if not bpost:
                logging.warning(["webhandler, m3u8 prepare failed:", path])
                return web.HTTPTooManyRequests()
            mpath = os.path.join("/%s" % prefix, path)
            logging.info(["webhandler, m3u8 redirect to another:", mpath])
            await asyncio.sleep(3)
            return web.HTTPTemporaryRedirect(location=mpath)

        # delay m3u8 if in transcoding
        if bpost:
            delay = 1
            if hextm.curr_seq() < 5: delay = 2
            await asyncio.sleep(delay)

        # fake m3u8 if possible
        body = None
        if agent.find("VLC/") != -1:
            body = hextm.fakeVlcContent(message.sdur, minfo.duration())
        elif hextm.curr_seq() < 3:
            body = hextm.fakeVodContent(message.sdur)
        if body:
            headers2 = {}
            headers2["Content-type"] = 'application/x-mpegURL'
            return web.Response(body=body, headers=headers2, status=200)
        return self.send_static(m3u8_fpath, headers)

    def get_raddr(self, request):
        try:
            raddr = None
            sock = request.get_extra_info('socket')
            if sock:
                raddr = sock.getpeername()
                raddr = "%s:%s" % (raddr[0], raddr[1])
        except: pass
        return raddr

    async def do_File(self, request):
        try:
            #logging.info(["do_File begin", request.url])
            uri = request.match_info["uri"]
        except Exception as e:
            logging.warning(["do_File error:", e])
            return web.HTTPBadRequest()
        else:
            resp = await self.check_hls(request, uri)
            return resp

    def send_static(self, fpath, headers):
        err, mtime = self.read_mtime(fpath)
        if err: return err
        if not self.check_modified(mtime, headers):
            return web.HTTPNotModified()
        headers2 = {}
        headers2["Content-type"] = CUtil.guess_type(fpath)
        headers2["Last-Modified"] = CUtil.datetime_string(mtime)
        return web.FileResponse(path=fpath, headers=headers2, status=200)

    def read_mtime(self, fpath):
        mtime = CUtil.parse_mtime(fpath)
        if mtime == -2:
            return web.HTTPInternalServerError(), None 
        if mtime == -1:
            return web.HTTPNotFound(reason="File not found"), None
        return None, mtime

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
            linkname = CUtil.parse_dirname(path)
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


async def run_web_server(handler):
    addr = "0.0.0.0"
    #addr = "localhost"
    port = "8001"
    logging.info(["web, start server:", addr, port])
    app = web.Application(middlewares=[])
    app.add_routes([
        web.get(r'/{uri:.*}', handler.do_File),
        ])
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, addr, port)
    await site.start()

async def run_other_task():
    while True:
        await asyncio.sleep(10)



def do_test_minfo():
    minfo = MediaInfo()
    minfo.parse("./samples/test_hevc2.mkv")
    print(minfo.info)
    pass

def do_test_cache():
    #Cache.check_timeout("/tmp/cached", "index.m3u8")
    Cache.check_timeout("./samples/cached", "index.m3u8", 10, 100)
    pass

def do_test_hls():
    ft = MediaExtm3u8()
    ft.open("index.m3u8", 5)
    print(ft.last_seq, ft.sdur, ft.probe_pos, ft.is_begin, ft.is_end)
    ft.close()
    pass

def do_test_coder():
    coder = Transcoder()
    #coder.do_hlsvod("samples/testCN.mkv", "/tmp/output", 0, 5)
    #coder.do_hlsvod("samples/test.mkv", "/tmp/output", 0, 5)
    #coder.do_hlsvod("samples/test_video.ts", "/tmp/output", 0, 5)
    #coder.do_hlsvod("samples/test_audio.ts", "/tmp/output", 0, 5)
    #coder.do_hlsvod("samples/test_hd.mov", "/tmp/output", 0, 5)
    #coder.do_hlsvod("samples/test_hevc.mkv", "/tmp/output", 0, 5)
    coder.do_hlsvod("samples/test_hevc2.mkv", "/tmp/output", 0, 10)

def do_test_loop():
    #do_test_minfo()
    #do_test_cache()
    #do_test_hls()
    do_test_coder()
    pass

def do_test():
    CUtil.set_log_file(None)
    logging.info("=======testing begin========")
    thread.start_new_thread(do_test_loop, ())
    time.sleep(300)
    pass

def do_main(srcPath, dstPath, maxCount, stdout=False):
    try:
        logf = "hls_client.txt"
        if stdout: logf = None
        CUtil.set_log_file(logf)
        logging.info("=====================\n\n")
        logging.info(["run_main, start...", srcPath, dstPath, maxCount])
        preload_check()

        handler = MyHTTPRequestHandler(srcPath, dstPath, maxCount)
        handler.init()

        loop = asyncio.get_event_loop()
        loop.create_task(run_web_server(handler))
        loop.run_until_complete(run_other_task())
        loop.run_forever()
    except:
        print()
        logging.info("main, quit for exception")
    finally:
        handler.uninit()
    print()


# should use __main__ to support child-process
if __name__ == "__main__":
    CUtil.set_log_path("/var/log/hlsvod")
    #do_test()
    #do_main("/deepnas/home", "/opt/hlscache", 2)
    #do_main(None, "/home/linaro/wspace/hlscache", 2)
    do_main(None, None, 1, True)
    sys.exit(0)
