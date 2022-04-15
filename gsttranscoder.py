import os
import sys
import time
import getopt
import re
import _thread as thread

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstPbutils', '1.0')
gi.require_version('GLib', '2.0')
gi.require_version('GObject', '2.0')

from gi.repository import Gst, GObject, GLib, GstPbutils
Gst.init(None)
#GLib.threads_init()


def format_ns(ns):
    s, ns = divmod(ns, 1000000000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return "%u:%02u:%02u.%09u" % (h, m, s, ns)

def gst_make_elem(name, props={}, alias=None):
    if not name: return None
    #print(name, props, alias)
    elem = Gst.ElementFactory.make(name, alias)
    if elem and props:
        for k,v in props.items():
            elem.set_property(k, v)
    return elem

def gst_link_elems(elems, dst=None):
    last = None
    for e in elems:
        if last: last.link(e)
        last = e
    if last and dst: last.link(dst)

def gst_set_playing(elems=[]):
    for e in elems:
        e.set_state(Gst.State.PLAYING)

def gst_make_caps_filter(fmt):
    # "video/x-raw", "audio/x-raw"
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
    else:
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
    if not enc:
        return "video/x-h264"
    profile = enc
    for k, v in props[enc].items():
        profile = "%s,%s=%s" % (profile, k, v)
    return profile

def gst_make_aac_enc_profile(kbps):
    bps = kbps * 1024
    enc = gst_check_elem("avenc_aac")
    if not enc:
        return "audio/mpeg"
    return "%s,bitrate=%s" % (enc, bps)

def gst_parse_props(line, key):
    props = {}
    if line.find(key) != -1:
        ret = re.search("%s ([\w/-]+)[,]*(.*)" % key, line)
        #print(ret.groups())
        if ret and len(ret.groups()) > 0:
            props["type"] = ret.groups()[0]
            if len(ret.groups()) > 1:
                props["more"] = {}
                for item in ret.groups()[1].split(", "):
                    pair = item.strip().split("=")
                    if len(pair) == 2:
                        props["more"][pair[0]] = pair[1]
            #print(props)
    return props

def gst_discover_info(fname):
    info = {}
    shbin = "gst-discoverer-1.0 -v %s" % fname
    lines = os.popen(shbin)
    for line in lines:
        #print(line)
        pos = line.find("Duration: ")
        if pos != -1:
            items = line[pos+10:].split(".")[0].split(":")
            if len(items) == 3:
                duration = int(items[0])*3600 + int(items[1])*60 + int(items[2])
                info["duration"] = duration
        ret = gst_parse_props(line, "container:")
        if not ret: 
            ret = gst_parse_props(line, "unknown:")
        if ret:
            info["mux"] = ret
        if not ret:
            ret = gst_parse_props(line, "audio:")
            if ret: info["audio"] = ret
        if not ret:
            ret = gst_parse_props(line, "video:")
            if ret: info["video"] = ret
    #print(info)
    return info

def gst_parse_value(item):
    ret = re.search("\((.*)\)(.*)", item)
    if ret and len(ret.groups()) > 1:
        stype = ret.groups()[0]
        sval = ret.groups()[1]
        if stype == "fraction":
            ival = 0
            for ch in sval:
                if ch >= '0' and ch <= '9': ival = ival * 10 + int(ch)
                else: break
            return ival
        elif stype == "int":
            return int(sval)
        elif stype == "boolean":
            if sval == "true": return True
            return False
        else:
            return sval
    return None


class Transcoder(object):
    def __init__(self):
        self.infile = ""
        self.offset = 0
        self.mtype = ""
        self.width = 0
        self.height = 0
        self.outfile = ""

    def do_print(self):
        print(self.offset, self.mtype, self.width, self.height, self.outfile)

    def add_elems(self, elems=[]):
        for e in elems:
            if e: self.pipeline.add(e)

    def do_convert(self):
        info = gst_discover_info(self.infile)
        if not info:
            return
        self.video_fps = gst_parse_value(info["video"]["more"]["framerate"])
        self.video_width = gst_parse_value(info["video"]["more"]["width"])
        self.video_height = gst_parse_value(info["video"]["more"]["height"])
        if self.video_fps == None or self.video_width == None or self.video_height == None:
            return
        print(">media:\n", info)
        print(">video:", self.video_fps, self.video_width, self.video_height)
        return

        mux = gst_make_mux_profile(self.mtype)
        avc = gst_make_h264_enc_profile(1024)
        aac = gst_make_aac_enc_profile(64)
        profile = "%s:%s:%s" % (mux, avc, aac)
        #afilter = gst_make_caps_filter("audio/x-raw")
        #vfilter = gst_make_caps_filter("video/x-raw")
        print(">profile:", profile)

        self.pipeline = Gst.Pipeline()
        source = gst_make_elem("filesrc", {"location": self.infile})
        transcode = gst_make_elem("transcodebin")
        #transcode.set_property("audio-filter", afilter)
        #transcode.set_property("video-filter", vfilter)
        Gst.util_set_object_arg(transcode, "profile", profile);
        sink = gst_make_elem("filesink", {"location": self.outfile})

        elems = [source, transcode, sink]
        self.add_elems(elems)
        self.elems = elems

        gst_link_elems(elems)
        self.check_run()
        
    def do_seek(self):
        print(">seek:", self.offset)
        seek_time = self.offset * Gst.SECOND*2
        self.pipeline.set_state(Gst.State.PAUSED)
        event = Gst.Event.new_seek(1.0, Gst.Format.TIME, Gst.SeekFlags.KEY_UNIT,
                Gst.SeekType.SET, seek_time, Gst.SeekType.NONE, -1)
        self.elems[2].send_event(event)
        #self.pipeline.send_event(event)
        #self.pipeline.seek_simple(Gst.Format.TIME,  Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, seek_time)
        #self.pipeline.seek(1.0, Gst.Format.TIME, Gst.SeekFlags.FLUSH, Gst.SeekType.SET,
        #    seek_time, Gst.SeekType.NONE, -1);
        pass

    def do_seek2(self):
        print(">seek2:", self.offset, self.video_fps)
        steps = self.offset * 25
        if self.video_fps > 0:
            steps = self.offset * self.video_fps
        self.pipeline.set_state(Gst.State.PAUSED)
        event = Gst.Event.new_step(Gst.Format.BUFFERS, steps, 2.0, True, False)
        self.elems[2].send_event(event)
        pass

    def on_message(self, bus, msg):
        #print("message:", msg, msg.type)
        if msg.type == Gst.MessageType.EOS:
            print(">message:", "EOS and quit")
            self.pipeline.set_state(Gst.State.NULL)
            self.loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            self.pipeline.set_state(Gst.State.NULL)
            err, debug = msg.parse_error()
            print(">message:", "Error: %s" % err, debug)
            self.loop.quit()
        elif msg.type == Gst.MessageType.STATE_CHANGED:
            #print(">message: state changed")
            pass
        elif msg.type == Gst.MessageType.STEP_START:
            print(">message: step start")
        elif msg.type == Gst.MessageType.STEP_DONE:
            print(">message: step done")
        pass

    def do_position(self):
        ok, position = self.pipeline.query_position(Gst.Format.TIME)
        if ok:
            print("yzxu", position)
        pass

    def check_run(self):
        GLib.timeout_add(200, self.do_position)
        self.do_seek2()

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

        self.loop = GLib.MainLoop()
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print(">run begin:", ret)
        try:
            self.loop.run()
        except:
            pass
        print(">run end");
        self.pipeline.set_state(Gst.State.NULL)

    def seek_thread(self):
        #GLib.timeout_add(200, self.do_seek)
        #thread.start_new_thread(self.seek_thread, ())
        ok, position = self.pipeline.query_position(Gst.Format.TIME)
        if ok:
            value = float(position) / Gst.SECOND
            print(">position:", value)



def help_usage(bin, err):
    print("usage: %s -h -i input -t timeoffset -s widthxheight output" % bin)
    print()
    sys.exit(err)


if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hi:t:s:')
    except getopt.GetoptError as err:
        help_usage(sys.argv[0], 2)
    if len(args) != 1:
        help_usage(sys.argv[0], 2)

    coder = Transcoder()
    coder.infile = None,
    coder.outfile = args[0]
    coder.offset = 0 # seconds

    for o, a in opts:
        if o == "-h":
            help_usage(sys.argv[0], 0)
        elif o == "-i":
            coder.infile = a
        elif o == "-t":
            try:
                coder.offset = int(a)
            except:
                help_usage(sys.argv[0], 2)
        elif o == "-s":
            try:
                size = a.split("x")
                coder.width = int(size[0])
                coder.height = int(size[1])
            except:
                help_usage(sys.argv[0], 2)
        else:
            help_usage(sys.argv[0], 2)

    _, ext = os.path.splitext(coder.outfile)
    if ext == ".ts":
        coder.mtype = "video/mpegts"
    elif ext == ".mp4" or ext == ".mov":
        coder.mtype = "video/quicktime"
    else:
        print("only support ts or mp4")
        sys.exit(2)
    coder.do_print()
    coder.do_convert()

