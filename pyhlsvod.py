#!/usr/bin/python
# coding=utf-8
# peterxu

import os
import sys
import re
import time
import random
import string
import shutil
import mimetypes
import posixpath
import logging
from multiprocessing import Process, Pipe
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
gi.require_version('GstPbutils', '1.0')
gi.require_version('GLib', '2.0')
gi.require_version('GObject', '2.0')
from gi.repository import Gst, GObject, GLib, GstPbutils


#======== common tools
def nowtime(): #ms
    return int(time.time()*1000)

def copyfile(source, dest):
    shutil.copyfile(source, dest)

def tonumber(val, default=None):
    try:
        ret = default
        ret = int(val)
    except: 
        try: ret = float(val)
        except: pass
    return ret

def gen_hex_string(length):
    sets = "0123456789ABCDEF"
    return ''.join(random.choice(sets) for i in range(length))

def gen_uuid():
    items = [gen_hex_string(val) for val in [8, 4, 4, 4, 12]]
    return '-'.join(items)

async def wait_file_exist(fname, timeout=0):
    if os.path.exists(fname): return True
    if timeout == 0: return False
    interval = 1.0
    if interval > timeout: interval = timeout
    times = int(timeout / interval)
    while times > 0:
        times -= 1
        await asyncio.sleep(interval)
        if os.path.exists(fname): return True
    return False


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
def hls_parse_prop(line, default=None):
    pos1 = line.find(":")
    if pos1 < 0: return default
    pos2 = line.find(",", pos1+1)
    if pos2 >= 0:
        val = line[pos1+1:pos2]
    else:
        val = line[pos1+1:]
    return tonumber(val, default)
def hls_parse_segment(line, default=None):
    try:
        result = re.search(".*_segment_(\d+).ts", line)
        return int(result.groups()[0])
    except:
        return default


#========== file monitor
class MediaMonitor(events.FileSystemEventHandler):
    def __init__(self):
        self.observer = None
        self.last_path = None
        self.last_lines = []
        self.cb_changed = None
        pass
    def on_any_event(self, evt):
        #logging.info(["mon-any", evt, evt.src_path])
        pass
    def on_moved(self, evt):
        #logging.info(["mon-moved", evt])
        self.check_path_modified(evt.dest_path)

    def check_path_modified(self, fname):
        if not os.path.isfile(fname): return
        if os.path.basename(fname) != "index.m38u": return
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
                        if lines[idx].find("#EXT-X-MEDIA-SEQUENCE") == -1:
                            theSame = False
                            break
                if theSame:
                    result = new_lines[old_number:]
                else:
                    result = new_lines
        #logging.info(["mon index.m38u changed:", len(self.last_lines), len(new_lines), result])
        self.last_lines = new_lines
        if self.cb_changed:
            self.cb_changed(self.last_path, result)
        pass
    def start(self, path, cb):
        self.last_path = path
        self.last_lines = []
        self.cb_changed = cb
        try:
            event_handler = self
            self.observer = Observer()
            self.observer.schedule(event_handler, path, recursive=False)
            self.observer.start()
        except:
            self.stop()
            pass
    def stop(self):
        self.cb_changed = None
        if not self.observer: return
        try:
            self.observer.stop()
            self.observer.join()
            self.observer = None
        except:
            pass
        pass


#======== processing m38u
class MediaExtm38u(object):
    def __init__(self):
        self.fp = None
        self.fpath = None
        self.last_seq = -1
        self.duration = 0
        self.is_begin = False
        self.is_end = False
        self.probe_count = 0
        self.probe_pos = 0
    def _init(self):
        self.last_seq = -1
        self.duration = 0
        self.is_begin = False
        self.is_end = False
        self.probe_count = 0
        self.probe_pos = 0
    def open(self, path, seconds, is_new=False):
        if self.fp:
            return False
        if seconds <= 0:
            return False
        fp = None
        fname = os.path.join(path, "index.m38u")
        if not is_new and os.path.isfile(fname):
            try:
                fp = open(fname, "r+")
                self._init()
                if fp and not self._parse(fp.readlines(), seconds):
                    logging.warning("extm3u: discard this m38u")
                    fp.close()
                    fp = None
            except:
                pass
        if not fp:
            try:
                fp = open(fname, "w")
                self._init()
            except:
                return False
        self.fp = fp
        self.fpath = path
        self.duration = seconds
        return True
    def write(self, name, seconds):
        if not self.fp:
            return False
        if not self.is_begin:
            self._add_begin(self.fp, self.duration)
            self.is_begin = True
        if self.is_end:
            return False
        self._add_one(self.fp, name, seconds)
        self.fp.flush()
    def writeProbe(self, count):
        if self.fp and self.is_begin and not self.is_end:
            self.fp.write("#PROBE_COUNT:%d\n" % count) 
            self.fp.flush()
        pass
    def next_name(self):
        self.last_seq += 1
        name = "hls_segment_%06d.ts" % self.last_seq
        return name, os.path.join(self.fpath, name)
    def curr_dur(self):
        if self.last_seq < 0: return 0
        return (self.last_seq + 1) * self.duration - 1

    def close(self):
        if self.fp:
            self.fp.close()
            self.fp = None
    def closeEnd(self):
        if self.fp:
            self._add_end(self.fp)
            self.is_end = True
        self.close()
    def _parse(self, lines, seconds):
        last_pos = 0
        last_probe = 0
        isSeg = False
        for line in lines:
            if line.find("#EXTM3U") == 0:
                self.is_begin = True
            elif line.find("#EXT-X-ENDLIST") == 0:
                self.is_end = True
            elif line.find("#EXT-X-TARGETDURATION:") == 0:
                self.duration = hls_parse_prop(line, 0)
            elif line.find("#EXTINF:") == 0:
                isSeg = True
                last_pos += hls_parse_prop(line, 0)
                continue
            elif line.find("#PROBE_COUNT:") == 0:
                last_probe = hls_parse_prop(line, 0)
            elif len(line.strip()) == 0 or line[0] == "#":
                continue
            if isSeg:
                isSeg = False
                seq = hls_parse_segment(line, None)
                if seq == None:
                    logging.warning("extm3u: invalid segment seq")
                    return False
                if seq != 0 and seq != self.last_seq + 1:
                    logging.warning("extm3u: segment seq not continous: %d", seq)
                    return False
                self.last_seq = seq
        if not self.is_begin:
            return False
        if self.duration != seconds:
            logging.warning("extm3u: invalid duration and restart")
            return False
        if not self.is_end:
            self.probe_count = last_probe
            self.probe_pos = last_pos
            if self.probe_count > 0:
                logging.info("extm3u: continue to last pos: %d", self.probe_count)
                return True
            return False
        logging.info("extm3u: last ended and nop again!")
        self.probe_count = 0
        self.probe_pos = 0
        return True
    def _add_begin(self, fp, seconds):
        fp.write("#EXTM3U\n")
        fp.write("#EXT-X-VERSION:3\n")
        fp.write("#EXT-X-ALLOW-CACHE:NO\n")
        fp.write("#EXT-X-MEDIA-SEQUENCE:0\n")
        fp.write("#EXT-X-TARGETDURATION:%d\n" % seconds)
        fp.write("\n")
        return True
    def _add_one(self, fp, segment, seconds):
        if type(seconds) == float:
            fp.write("#EXTINF:%.2f,\n" % seconds)
        else:
            fp.write("#EXTINF:%d,\n" % int(seconds))
        fp.write("%s\n" % segment)
        return True
    def _add_end(self, fp):
        fp.write("#EXT-X-ENDLIST")
        return True


#========= processing media files
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
        #logging.info(["coder media:", info])
        if self.hasVideo():
            fps = self.frameRate()
            width = self.width()
            height = self.height()
            if fps == 0 or width == 0 or height == 0:
                return False
            logging.info("coder video: %dx%d@%d", width, height, fps)
        else:
            logging.info("coder no video")
        return True


class Transcoder(object):
    def __init__(self):
        self.mutex = threading.Lock()
        self.working = 0
        self.state = -1
        self.loop = None
        self.pipeline = None
        self.start_pos = [0, 0]
        self.buffer_count = -1
        self.map_count = {}
        pass

    def outdated(self):
        return self.working == -1

    def get_count(self, dur):
        self.mutex.acquire()
        count = self.map_count.get(int(dur), 0)
        self.mutex.release()
        return count

    def set_count(self, dur, count):
        self.mutex.acquire()
        if dur < 0 or count < 0:
            self.buffer_count = 0
            self.map_count = {}
        else:
            self.buffer_count += count
            self.map_count[int(dur)] = self.buffer_count
        count2 = self.buffer_count
        self.mutex.release()
        return count2

    def do_hlsvod(self, infile, outpath, inpos, duration):
        outfile = os.path.join(outpath, "index.ts")
        playlist = os.path.join(outpath, "index.m38u")
        segment = os.path.join(outpath, "hls_segment_%06d.ts")
        options = {
            "max-files": 1000000,
            "target-duration": duration,
            "playlist-length": 0,
            "playlist-location": playlist,
            "location": segment,
        }
        sink = gst_make_elem("hlssink", options)
        logging.info("coder hls: %s - %s, start: %s, duration: %d", infile, outpath, inpos, duration)
        self.start_pos = inpos
        self.set_count(-1, -1)
        self.do_work(infile, outfile, sink, "video/mpegts", 64, 1024)

    def do_work(self, infile, outfile, sink, outcaps, akbps, vkbps):
        self.working = 1
        mux = gst_make_mux_profile(outcaps)
        aac = gst_make_aac_enc_profile(akbps)
        avc = gst_make_h264_enc_profile(vkbps)
        profile = "%s:%s:%s" % (mux, avc, aac)
        logging.info("coder profile: %s", profile)

        source = gst_make_elem("filesrc", {"location": infile})
        transcode = gst_make_elem("transcodebin")
        Gst.util_set_object_arg(transcode, "profile", profile);
        if not sink:
            sink = gst_make_elem("filesink", {"location": outfile})
        elems = [source, transcode, sink]

        pad = sink.get_static_pad("sink")
        if pad:
            #ptype = Gst.PadProbeType.BUFFER
            ptype = Gst.PadProbeType.BUFFER_LIST
            ret = pad.add_probe(ptype, self.transcode_probe, ptype)
            logging.info(["add probe", pad, ptype, ret])

        self.pipeline = Gst.Pipeline()
        gst_add_elems(self.pipeline, elems)
        gst_link_elems(elems)
        self.elems = elems
        self.check_run()

    def do_stop(self):
        if self.loop and self.pipeline:
            self.loop.quit()

    def do_pause(self):
        if self.loop and self.pipeline:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.state = int(Gst.State.PAUSED)

    # VOID_PENDING:0, NULL:1, READY:2, PAUSED:3, PLAYING:4
    def get_state(self):
        return self.state

    def transcode_probe(self, pad, info, ptype):
        count = -1
        if ptype == Gst.PadProbeType.BUFFER_LIST:
            items = info.get_buffer_list()
            if items: count = items.length()
        elif ptype == Gst.PadProbeType.BUFFER:
            item = info.get_buffer()
            if item: count = 1
        if count >= 0:
            value = 0
            ok, pos = self.pipeline.query_position(Gst.Format.TIME)
            if ok: value = int(float(pos) / Gst.SECOND)
            total_count = self.set_count(value, count)
            logging.info(["probe", count, total_count, value, self.start_pos])
            if total_count <= self.start_pos[0]:
                return Gst.PadProbeReturn.DROP
        return Gst.PadProbeReturn.OK

    def check_run(self):
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

        self.loop = GLib.MainLoop()
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        self.state = int(Gst.State.PLAYING)
        logging.info("coder run begin: %d", ret)
        try:
            self.loop.run()
        except Exception as e:
            logging.warning(["coder run error", e]);
            pass
        else:
            logging.info("coder run end");
        self.pipeline.set_state(Gst.State.NULL)
        self.state = int(Gst.State.NULL)
        self.working = -1
        pass

    def do_position(self):
        st = self.get_state()
        if st == int(Gst.State.PLAYING):
            ok, pos = self.pipeline.query_position(Gst.Format.TIME)
            if ok:
                value = int(float(pos) / Gst.SECOND)
                logging.info("coder state: %d, position: %d - %d", st, pos, value)

    def do_seek_steps(self, sink, steps):
        self.pipeline.set_state(Gst.State.PAUSED)
        event = Gst.Event.new_step(Gst.Format.BUFFERS, steps, 1.0, True, False)
        #event = Gst.Event.new_step(Gst.Format.TIME, steps * Gst.SECOND, 1.0, True, False)
        #event = Gst.Event.new_seek(1.0, Gst.Format.TIME, Gst.SeekFlags.FLUSH,
        #        Gst.SeekType.SET, steps * Gst.SECOND, Gst.SeekType.NONE, -1)
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
class HlsMessage:
    def __init__(self, mtype, name, fsrc=None, fdst=None):
        self.mtype = mtype
        self.name = name
        self.fsrc = fsrc
        self.fdst = fdst
        self.duration = 5
        self.result = None

class HlsService:
    def __init__(self, conn):
        self.mutex = threading.Lock()
        self.conn = conn
        self.coder = None
        self.source = None
        self.monitor = None
        self.extm38u = None
        self.last_coder_time = 0
        pass

    def _reset(self):
        self.coder = None
        self.source = None
        if self.monitor:
            self.monitor.stop()
            self.monitor = None
        if self.extm38u:
            self.extm38u.close()
            self.extm38u = None
        self.last_coder_time = 0

    def _loop(self, coder, fsrc, fdst, fpos, duration):
        try:
            logging.info("coder loop...")
            coder.do_hlsvod(fsrc, fdst, fpos, duration)
        except Exception as e:
            logging.warning(["coder loop error", e])
        except:
            logging.warning("coder loop other error")
        else:
            logging.info("coder loop end")

    def get_coder(self):
        if self.coder and self.coder.outdated():
            self._reset()
        return self.coder

    def get_coder_count(self, dur):
        coder = self.get_coder()
        if coder: return coder.get_count(dur)
        return -1

    def is_coder_alive(self):
        coder = self.get_coder()
        if coder: return True
        return False

    def is_coder_timeout(self):
        if self.last_coder_time != 0:
            return nowtime() >= self.last_coder_time + 30*1000
        return False

    def stop_coder(self):
        coder = self.get_coder()
        if coder:
            logging.info("coder stop...")
            coder.do_stop()
        self._reset()

    def start_coder(self, fsrc, fdst, duration):
        # final destination
        extm = MediaExtm38u()
        if not extm.open(fdst, duration):
            return False
        if extm.is_end:
            logging.info("coder had end and nop")
            extm.close()
            return False
        self.extm38u = extm

        # tmp destination for transcoder
        fdst_tmp = os.path.join(fdst, "cached");
        if not os.path.exists(fdst_tmp):
            os.makedirs(fdst_tmp, exist_ok=True)
        mmon = MediaMonitor()
        mmon.start(fdst_tmp, self.mon_changed)
        self.monitor = mmon

        self.last_coder_time = nowtime()
        self.coder = Transcoder()
        fpos = [extm.probe_count, extm.probe_pos]
        logging.info("coder start, pos=%s", fpos)
        thread.start_new_thread(self._loop, (self.coder, fsrc, fdst_tmp, fpos, duration))
        logging.info("coder end...")

    def mon_changed(self, path, lines):
        extm = self.extm38u
        if not extm:
            logging.error("coder changed: invalid extm38u")
            return

        isSeg = False
        seconds = 0
        for line in lines:
            if line.find("#EXT-X-TARGETDURATION:") == 0:
                extm.duration = hls_parse_prop(line, 0)
                continue
            elif line.find("#EXT-X-ENDLIST") == 0:
                logging.info("coder new-segment end")
                extm.closeEnd()
                continue
            elif line.find("#EXTINF:") == 0:
                isSeg = True
                seconds = hls_parse_prop(line, 0)
                continue
            elif len(line.strip()) == 0 or line[0] == "#":
                continue
            if isSeg:
                isSeg = False
                srcf = os.path.join(path, line.strip())
                name, dstf = extm.next_name()
                logging.info("coder new-segment: %s - %s - %s", srcf, name, dstf)
                copyfile(srcf, dstf)
                extm.write(name, seconds)
            else:
                logging.warning("coder new-segment invalid: %s", line)
                pass
            pass
        if seconds > 0:
            count = self.get_coder_count(extm.curr_dur())
            if count > 0: extm.writeProbe(count)
            logging.info("coder changed count: %d", count)
        pass

    def prepare_coder(self, source, fsrc, fdst, duration):
        if duration < 5: duration = 5
        if not source or not fsrc or not fdst:
            logging.warning("invalid coder args")
            return False
        if not os.path.isfile(fsrc):
            logging.warning("src not exist: %s", fsrc)
            return False
        if not os.path.exists(fdst):
            os.makedirs(fdst, exist_ok=True)
        elif os.path.isfile(fdst):
            logging.warning("dst is file: %s", fdst)
            return False
        if self.is_coder_alive():
            if source != self.source:
                logging.warning("another working: %s", self.source)
                return False
            self.last_coder_time = nowtime()
            return True
        self.source = source
        ret = self.start_coder(fsrc, fdst, duration)
        return ret

    def on_hls_message(self, msg):
        if not msg:
            logging.warning("invalid msg: %s", msg)
            return
        logging.info("recv message: %s", msg)
        resp = HlsMessage("ack", msg.name)
        if self.prepare_coder(msg.name, msg.fsrc, msg.fdst, msg.duration):
            resp.result = True
        else:
            resp.result = False
        self.conn.send(resp)
        pass

    def run_forever(self):
        while True:
            try:
                ret = self.conn.poll(0.5)
                if ret:
                    msg = self.conn.recv()
                    self.on_hls_message(msg)
            except Exception as e:
                logging.warning("poll err and quit: %s", e)
                break
            except:
                logging.warning("poll other err and quit")
                break

            try:
                #logging.info("coder checking...")
                if self.is_coder_alive() and self.is_coder_timeout():
                    logging.warning("coder timeout...")
                    self.stop_coder()
                    pass
                self.conn.send(HlsMessage("status", self.source))
                pass
            except:
                pass
        self.stop_coder()
        time.sleep(1)
        pass
    pass


def run_hls_service(conn, index):
    logf = "/tmp/hls_service_%d.txt" % index
    logging.basicConfig(filename=logf, encoding='utf-8',
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%m/%d/%Y %H:%M:%S',
            level=logging.INFO)
    logging.info("run_hls_service begin")
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
        self.tmp_source = None
        self.last_backend_time = nowtime()

    def no_focus(self):
        return (self.source == None) and (self.tmp_source == None)
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
        return nowtime() >= self.last_backend_time + 3000

    def post_message(self, msg):
        self.conn.send(msg)

    def on_backend_message(self, msg):
        self.last_backend_time = nowtime()
        if not msg:
            print("invalid msg:", msg)
            return
        #print("recv msg:", msg)
        if msg.mtype == "status" or msg.result is True:
            self.source = msg.name
            self.tmp_source = None
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
        logging.info("hls-cli run begin")
        self.child.join()
        self.set_alive(False)
        logging.info("hls-cli run end")

    def _listen(self):
        while self.alive:
            try:
                ret = self.conn.poll(1)
                if ret:
                    msg = self.conn.recv()
                    self.on_backend_message(msg)
            except Exception as e:
                logging.warning(["hls-cli poll err:", e])
                break
        pass

def createHls(index):
    p1, p2 = Pipe(True)
    srv = Process(target=run_hls_service, args=(p1, index))
    srv.start()
    cli = HlsClient(p2, srv)
    cli.start()
    return cli

class HlsCenter:
    def __init__(self):
        self.count = 1
        self.services = []
        pass
    def init_services(self):
        items = []
        for idx in range(self.count):
            items.append(createHls(idx))
        self.services = items
        time.sleep(1)
    def stop_services(self):
        for item in self.services:
            item.stop()
        self.services = []
    def check_services(self):
        items = []
        for idx in range(self.count):
            item = self.services[idx]
            if item.is_alive() and item.is_backend_timeout():
                logging.info("hls-center, one service timeout and stop")
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
        self.hlscenter = HlsCenter()

    def init(self):
        self.hlscenter.init_services()
        pass
    def uninit(self):
        self.hlscenter.stop_services()
        pass

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
                message = HlsMessage("prepare", source, src_fpath, dst_fpath)
                bret = self.hlscenter.post_service(message)
                if not bret:
                    logging.warning("check_hls m38u prepare failed: %s", source)
                    return web.HTTPTooManyRequests()
                await asyncio.sleep(5)
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
                message = HlsMessage("prepare", source, src_fpath, dst_fpath)
                bret = self.hlscenter.post_service(message)
                if not bret:
                    logging.warning("check_hls m38u failed: %s", source)
                    return web.HTTPTooManyRequests()
                logging.info("check_hls check m38u: %s", m38u_fpath)
                await asyncio.sleep(3)
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
                message = HlsMessage("prepare", source, src_fpath, dst_fpath)
                bret = self.hlscenter.post_service(message)
                if not bret:
                    logging.warning("check_hls ts failed: %s", source)
                    return web.HTTPTooManyRequests()
                await wait_file_exist(seg_fpath, 10)
                pass
            #logging.info("check_hls ts file:%s", seg_fpath)
            return self.send_static(seg_fpath, headers)
        return web.HTTPBadRequest()

    async def do_File(self, request):
        try:
            #logging.info("do_File begin")
            headers = request.headers
            uri = request.match_info["uri"]
        except Exception as e:
            logging.warning(["do_File error:", e])
            return web.HTTPBadRequest()
        else:
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
        finally:
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


async def run_web_server(handler):
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


def do_test():
    #ftest = MediaExtm38u()
    #ftest.open("index.m38u", 5)
    #print(ftest.last_seq, ftest.duration, ftest.probe_count, ftest.is_begin, ftest.is_end, ftest)
    pass

def do_main():
    logging.basicConfig(
            format='%(asctime)s [%(levelname)s][hls-cli] %(message)s',
            datefmt='%m/%d/%Y %H:%M:%S',
            level=logging.INFO)
    try:
        handler = MyHTTPRequestHandler()
        handler.init()

        loop = asyncio.get_event_loop()
        loop.create_task(run_web_server(handler))
        loop.run_until_complete(run_other_task())
        loop.run_forever()
    except:
        print()
        logging.warning("quit for exception")
    finally:
        handler.uninit()
    print()


# should use __main__ to support child-process
if __name__ == "__main__":
    do_test()
    do_main()
