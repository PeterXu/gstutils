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
import threading
import _thread as thread

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


def tonumber(val, default=None):
    try:
        ret = default
        ret = int(val)
    except: 
        try: ret = float(val)
        except: pass
    return ret


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
    return "video/x-matroska"
def gst_make_aac_enc_profile(kbps):
    bps = kbps * 1024
    return "audio/mpeg,mpegversion=4,bitrate=%s" % bps
def gst_make_h264_enc_profile(kbps):
    bps = kbps * 1024
    return "video/x-h264,stream-format=byte-stream,bitrate=%s" % bps
def gst_make_audio_props(name, kbps):
    bps = kbps * 1024
    props = {
        "faac": {"bitrate": bps},
        "voaacenc": {"bitrate": bps},
        "avenc_aac": {"bitrate": bps},
    }
    for k, v in props.items():
        if name.find(k) == 0: return v
    return None
def gst_make_video_props(name, kbps):
    bps = kbps * 1024
    props1 = {"rc-mode":"vbr", "bps":bps, "profile":"main",}
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
def gst_mpp_dec(dec):
    # vp8/vp9/h264/h265/mpeg
    if gst_make_elem("mppvideodec"):
        return "mppvideodec"
    return dec

def gst_find_items(prop, items):
    for item in items:
        if prop.find(item) != -1: return True
    return False
def gst_mux_type(prop):
    if not prop: return None
    if gst_find_items(prop, ["/quicktime", "/x-3gp", "/x-mj2", "/x-m4a"]):
        return "qtmux"
    if gst_find_items(prop, ["/x-matroska"]):
        return "matroskamux"
    if gst_find_items(prop, ["/webm"]):
        return "webmmux"
    if gst_find_items(prop, ["/mpegts"]):
        return "mpegtsmux"
    if gst_find_items(prop, ["/mpeg", "/x-cdxa"]):
        return "mpegpsmux"
    if gst_find_items(prop, ["/x-msvideo"]):
        return "avimux"
    if gst_find_items(prop, ["/ogg", "/kate"]):
        return "oggmux"
    if gst_find_items(prop, ["/x-flv"]):
        return "flvmux"
    return None
def gst_audio_type(prop):
    if not prop: return [None, None]
    if gst_find_items(prop, ["audio/mpeg"]):
        if gst_find_items(prop, ["mpegversion=(int)1"]):
            dec = None
            if gst_find_items(prop, ["layer=(int)1"]):
                dec = "avdec_mp1float"
            elif gst_find_items(prop, ["layer=(int)2"]):
                dec = "avdec_mp2float"
            elif gst_find_items(prop, ["layer=(int)3"]):
                dec = "avdec_mp3"
            return ["mpegaudioparse", dec]
        if gst_find_items(prop, ["mpegversion=(int)2", "mpegversion=(int)4"]):
            return ["aacparse", "avdec_aac"]
    if gst_find_items(prop, ["audio/x-vorbis"]):
        return ["vorbisparse", "vorbisdec"]
    if gst_find_items(prop, ["audio/x-opus"]):
        return ["opusparse", "avdec_opus"]
    if gst_find_items(prop, ["audio/x-flac"]):
        return ["flacparse", "avdec_flac"]
    if gst_find_items(prop, ["audio/x-alaw", "audio/x-mulaw"]):
        dec = "alawdec"
        if gst_find_items(prop, ["audio/x-mulaw"]):
            dec = "mulawdec"
        return ["audioparse", dec]
    if gst_find_items(prop, ["audio/x-ac3", "audio/ac3", "audio/x-private1-ac3", "audio/x-eac3"]):
        dec = "avdec_ac3"
        if gst_find_items(prop, ["audio/x-eac3"]):
            dec = "avdec_eac3"
        return ["ac3parse", dec]
    return [None, None]
def gst_video_type(prop):
    if not prop: return [None, None]
    if gst_find_items(prop, ["video/x-h264"]):
        return ["h264parse", gst_mpp_dec("avdec_h264")]
    if gst_find_items(prop, ["video/x-h265"]):
        return ["h265parse", gst_mpp_dec("avdec_h265")]
    if gst_find_items(prop, ["video/mpeg"]):
        if gst_find_items(prop, ["mpegversion=(int)1", "mpegversion=(int)2"]):
            dec = "avdec_mpegvideo"
            if gst_find_items(prop, ["mpegversion=(int)2"]):
                dec = "avdec_mpeg2video"
            return ["mpegvideoparse", gst_mpp_dec(dec)]
        if gst_find_items(prop, ["mpegversion=(int)4"]):
            return ["mpeg4videoparse", gst_mpp_dec("avdec_mpeg4")]
    if gst_find_items(prop, ["video/x-h263"]):
        return ["h263parse", "avdec_h263"]
    if gst_find_items(prop, ["video/x-vp8"]):
        return [None, gst_mpp_dec("vp8dec")]
    if gst_find_items(prop, ["video/x-vp9"]):
        return [None, gst_mpp_dec("vp9dec")]
    if gst_find_items(prop, ["video/x-theora"]):
        return ["theoraparse", "theoradec"]
    if gst_find_items(prop, ["video/x-divx"]):
        if gst_find_items(prop, ["divxversion=(int)4", "divxversion=(int)5"]):
            return ["mpeg4videoparse", "avdec_mpeg4"]
    if gst_find_items(prop, ["video/x-wmv"]):
        if gst_find_items(prop, ["wmvversion=(int)3"]):
            if not gst_find_items(prop, ["format=WMV3"]):
                return ["vc1parse", "avdec_vc1"]
    return [None, None]

def gst_parse_props(line, key):
    if line.find(key) == -1: return {}
    ret = re.search("%s ([\w/-]+)[,]*(.*)" % key, line)
    if not ret or len(ret.groups()) == 0: return {}
    #print(ret.groups())
    props = {}
    props["detail"] = line
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


#========= processing media files
class MediaInfo(object):
    def __init__(self):
        self.infile = ''
        self.info = {}

    def fileSize(self):
        return self.info.get("filesize", 0)

    def duration(self):
        return self.info.get("duration", 0)

    def bitrate(self):
        return self.info.get("bitrate", 0)

    def mediaType(self, kind): #mux/audio/video
        return self.info.get(kind, {}).get("type", None)

    def hasAudio(self):
        return self.mediaType("audio") != None

    def hasVideo(self):
        return self.mediaType("video") != None

    def frameRate(self):
        value = self.info.get("video", {}).get("more", {}).get("framerate", 0)
        if type(value) == int: return value
        return gst_parse_value(value)

    def width(self):
        value = self.info.get("video", {}).get("more", {}).get("width", 0)
        if type(value) == int: return value
        return gst_parse_value(value)

    def height(self):
        value = self.info.get("video", {}).get("more", {}).get("height", 0)
        if type(value) == int: return value
        return gst_parse_value(value)

    def muxType(self):
        return gst_mux_type(self.info.get("mux", {}).get("detail"))

    def audioType(self):
        return gst_audio_type(self.info.get("audio", {}).get("detail"))

    def videoType(self):
        return gst_video_type(self.info.get("video", {}).get("detail"))

    def isWebDirectSupport(self):
        mux = self.mediaType("mux")
        if mux == "video/quicktime" or mux == "application/x-3gp" or mux == "audio/x-m4a":
            audio = self.mediaType("audio")
            video = self.mediaType("video")
            if audio != None and audio != "audio/mpeg": return False
            if video != None and video != "video/x-h264": return False 
            if self.fileSize() <= 100*1024*1024:  #100MB
                if self.bitrate() <= 5*1024*1024: #5Mbps
                    return True
        return False

    def parse(self, infile):
        info = gst_discover_info(infile)
        if not info: return False
        self.infile = infile
        self.info = info
        if self.duration() == 0:
            return False
        try:
            fp = open(infile, "rb")
            fs = os.fstat(fp.fileno())
            fp.close()
            bps = fs.st_size * 8 / self.duration()
            info["filesize"] = fs.st_size
            info["bitrate"] = int(bps)
        except:
            info["filesize"] = 0
            info["bitrate"] = 0
            pass
        #print(info)
        #print("coder media:", info)
        if self.hasVideo():
            fps = self.frameRate()
            width = self.width()
            height = self.height()
            if fps == 0 or width == 0 or height == 0:
                return False
            print("coder video: ", width, height, fps)
        else:
            print("coder no video")
        return True


class Transcoder(object):
    def __init__(self):
        self.working = 0
        self.loop = None
        self.pipeline = None
        self.start_pos = 0

    def do_hlsvod(self, infile, inpos):
        print("gst-coder, begin:", infile, inpos)
        self.start_pos = inpos
        self.working = 1
        self.do_work(infile, 64, 1024, "video/mpegts")
        self.working = -1

    def do_work(self, infile, akbps, vkbps, outcaps):
        aac = gst_make_aac_enc_profile(akbps)
        avc = gst_make_h264_enc_profile(vkbps)
        mux = gst_make_mux_profile(outcaps)
        print("gst-coder, elems:", mux, avc, aac)
        profile = "%s:%s:%s" % (mux, aac, avc)

        minfo = MediaInfo()
        if not minfo.parse(infile):
            logging.warning("gst-coder, invalid media")
            return

        start = self.start_pos
        muxType = minfo.muxType()
        aType = minfo.audioType()
        vType = minfo.videoType()
        print("gst-coder, media-type:", muxType, aType, vType)
        if not aType[1] and not vType[1]:
            logging.warning("gst-coder, media-type no decoder")
            return

        parts1 = []
        parts1.append("filesrc location=\"%s\" name=fs" % infile)
        parts1.append("parsebin name=pb")
        parts1.append("proxysink name=psink0")
        parts1.append("proxysink name=psink1")
        parts1.append("fs. ! pb.")
        parts1.append("pb. ! mpeg4videoparse ! queue ! psink0.")
        parts1.append("pb. ! aacparse ! queue ! psink1.")
        sstr1 = " ".join(parts1)
        p1 = Gst.parse_launch(sstr1)
        psink0 = p1.get_by_name("psink0")
        psink1 = p1.get_by_name("psink1")
        print("gst-coder, pipeline1:", sstr1, p1, psink0, psink1)

        print("gst-coder, outputfile: test_output.ts")
        parts2 = []
        parts2.append("proxysrc name=psrc0")
        parts2.append("proxysrc name=psrc1")
        parts2.append("filesink location=test_output.ts name=fs")
        parts2.append("decodebin3 name=db")
        parts2.append("encodebin profile=\"%s\" name=eb" % profile)
        parts2.append("psrc0. ! db.sink_0")
        parts2.append("psrc1. ! db.sink_1")
        parts2.append("db.video_0 ! queue ! eb.video_0")
        parts2.append("db.audio_0 ! queue ! eb.audio_0")
        parts2.append("eb. ! fs.")

        sstr2 = " ".join(parts2)
        p2 = Gst.parse_launch(sstr2)
        psrc0 = p2.get_by_name("psrc0")
        psrc1 = p2.get_by_name("psrc1")
        print("gst-coder, pipeline2:", sstr2, p2, psrc0, psrc1)

        psrc0.set_property('proxysink', psink0)
        psrc1.set_property('proxysink', psink1)

        clock = Gst.SystemClock.obtain()
        p1.use_clock(clock)
        p2.use_clock(clock)
        clock.unref()

        #p1.set_base_time(0)
        #p2.set_base_time(0)

        self.pipeline = p1
        bus = p1.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        self.loop = GLib.MainLoop()
        p1.set_state(Gst.State.PLAYING)
        p2.set_state(Gst.State.PLAYING)
        if start > 0: self.do_seek(p1, start)
        self.loop.run()
        print("gst-coder, end")

    def do_seek(self, elem, steps):
        print("gst-coder, seek:", elem, steps)
        self.pipeline.set_state(Gst.State.PAUSED)
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        time.sleep(0.5)
        event = Gst.Event.new_seek(1.0, Gst.Format.TIME, Gst.SeekFlags.FLUSH|Gst.SeekFlags.KEY_UNIT,
                Gst.SeekType.SET, steps * Gst.SECOND, Gst.SeekType.NONE, -1)
        self.pipeline.send_event(event)
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        time.sleep(3)
        print("gst-coder, seek end")

    def on_message(self, bus, msg):
        #print("message: %s", msg.type)
        if msg.type == Gst.MessageType.EOS:
            print("gst-coder, message EOS and quit")
            self.pipeline.set_state(Gst.State.NULL)
            self.loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            self.pipeline.set_state(Gst.State.NULL)
            err, debug = msg.parse_error()
            print("gst-coder, message Error:", err, debug)
            self.loop.quit()
        elif msg.type == Gst.MessageType.STATE_CHANGED:
            pass
        elif msg.type == Gst.MessageType.DURATION_CHANGED:
            value = -1
            ok, pos = self.pipeline.query_duration(Gst.Format.TIME)
            if ok: value = int(float(pos) / Gst.SECOND)
            print("gst-coder duration:", value)
        pass


def do_test_coder():
    coder = Transcoder()
    coder.do_hlsvod("test.mkv", 50)

def do_test():
    thread.start_new_thread(do_test_coder, ())
    time.sleep(200)

if __name__ == "__main__":
    do_test()
    sys.exit(0)
