import os
import sys
import time
import getopt
import _thread as thread

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib


def format_ns(ns):
    s, ns = divmod(ns, 1000000000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return "%u:%02u:%02u.%09u" % (h, m, s, ns)

def make_elem(name, props={}, alias=None):
    if not name: return None
    elem = Gst.ElementFactory.make(name, alias)
    if elem and props:
        for k,v in props.items():
            elem.set_property(k, v)
    return elem

def make_caps_filter(szcaps):
    # "video/x-raw", "audio/x-raw"
    caps = Gst.Caps.from_string(szcaps)
    return make_elem("capsfilter", {"caps": caps})

def make_video_dec(vtype):
    info = [None, None]
    if vtype.find("video/x-h264") >= 0:
        info = ["h264parse", "avdec_h264"]
    elif vtype.find("video/x-h265") >= 0:
        info = ["h265parse", "avdec_h265"]
    elif vtype.find("video/mpeg") >= 0:
        if vtype.find("mpegversion=(int)1") >= 0:
            info = ["mpegvideoparse", "avdec_mpegvideo"]
        elif vtype.find("mpegversion=(int)2") >= 0:
            info = ["mpegvideoparse", "avdec_mpeg2video"]
        elif vtype.find("mpegversion=(int)4") >= 0:
            info = ["mpeg4videoparse", "avdec_mpeg4"]
    elif vtype.find("video/x-h263") >= 0:
        info = ["h263parse", None]
    elif vtype.find("video/x-vp8") >= 0:
        info = [None, "vp8dec"]
    elif vtype.find("video/x-vp9") >= 0:
        info = [None, "vp9dec"]
    elif vtype.find("video/x-theora") >= 0:
        info = ["theoraparse", "theoradec"]
    elif vtype.find("video/x-flash-video") >= 0:
        info = [None, "avdec_flv"]
    elif vtype.find("video/x-divx") >= 0:
        if vtype.find("divxversion=(int)3") >= 0:
            info = [None, "avdec_msmpeg4"]
        elif vtype.find("divxversion=(int)4") >= 0 or vtype.find("divxversion=(int)5") >= 0:
            info = ["mpeg4videoparse", "avdec_mpeg4"]
    elif vtype.find("video/x-msmpeg") >= 0:
        if vtype.find("msmpegversion=(int)41") >= 0:
            info = [None, "avdec_msmpeg4v1"]
        elif vtype.find("msmpegversion=(int)42") >= 0:
            info = [None, "avdec_msmpeg4v2"]
        elif vtype.find("msmpegversion=(int)43") >= 0:
            info = [None, "avdec_msmpeg4"]
    elif vtype.find("video/x-wmv") >= 0:
        if vtype.find("wmvversion=(int)1") >= 0:
            info = [None, "avdec_wmv1"]
        elif vtype.find("wmvversion=(int)2") >= 0:
            info = [None, "avdec_wmv2"]
        elif vtype.find("wmvversion=(int)3") >= 0:
            if vtype.find("format=WMV3") >= 0:
                info = [None, "avdec_wmv3"]
            else:
                info = ["vc1parse", "avdec_vc1"]
    elems = [None, None]
    elems[0] = make_elem(info[0])
    mppCaps = "video/x-vp8;video/x-vp9;video/x-h264;video/x-h265;video/mpeg,mpegversion="
    if mppCaps.find(vtype) >= 0:
        elems[1] = make_elem("mppvideodec")
    if not elems[1]:
        elems[1] = make_elem(info[1])
    print("video-dec:", info)
    return elems

def make_h264_enc(kbps):
    bps = kbps * 1024
    props1 = {
            "rc-mode":  "vbr",
            "bps":      bps,
            "profile":  "main",
            }
    props2 = {
            "pass":     "pass1",
            "bitrate":  bps,
            "profile":  "main",
            }
    parse = make_elem("h264parse")
    enc = make_elem("mppvideoenc", props1)
    if not enc:
        enc = make_elem("avenc_h264_videotoolbox", props2)
    if not enc:
        enc = make_elem("avenc_h264", props2)
    return parse, enc

def make_audio_dec(atype):
    info = [None, None]
    if atype.find("audio/mpeg") >= 0:
        if atype.find("mpegversion=(int)1") >= 0:
            if atype.find("layer=(int)1") >= 0:
                info = ["mpegaudioparse", "avdec_mp1float"]
            elif atype.find("layer=(int)2") >= 0:
                info = ["mpegaudioparse", "avdec_mp2float"]
            elif atype.find("layer=(int)3") >= 0:
                info = ["mpegaudioparse", "avdec_mp3"]
        elif atype.find("mpegversion=(int)2") >= 0 or atype.find("mpegversion=(int)4") >= 0:
            info = ["aacparse", "avdec_aac"]
    elif atype.find("audio/x-vorbis") >= 0:
        info = ["vorbisparse", "vorbisdec"]
    elif atype.find("audio/x-opus") >= 0:
        info = ["opusparse", "avdec_opus"]
    elif atype.find("audio/x-flac") >= 0:
        info = ["flacparse", "avdec_flac"]
    elif atype.find("audio/AMR-WB") >= 0:
        info = [None, "avdec_amrwb"]
    elif atype.find("audio/AMR") >= 0:
        info = [None, "avdec_amrnb"]
    elif atype.find("audio/x-speex") >= 0:
        info = [None, "speexdec"]
    elif atype.find("audio/x-alaw") >= 0:
        info = ["audioparse", "alawdec"]
    elif atype.find("audio/x-mulaw") >= 0:
        info = ["audioparse", "mulawdec"]
    elif atype.find("audio/x-ac3") >= 0 or atype.find("audio/ac3") >= 0 or atype.find("audio/x-private1-ac3") >= 0:
        info = ["ac3parse", "avdec_ac3"]
    elif atype.find("audio/x-eac3") >= 0:
        info = ["ac3parse", "avdec_eac3"]
    elif atype.find("audio/x-wma") >= 0:
        if atype.find("wmaversion=(int)1") >= 0:
            info = [None, "avdec_wmav1"]
        elif atype.find("wmaversion=(int)2") >= 0:
            info = [None, "avdec_wmav2"]
        elif atype.find("wmaversion=(int)3") >= 0:
            info = [None, "avdec_wmapro"]
        elif atype.find("wmaversion=(int)4") >= 0:
            info = [None, "avdec_wmalossless"]
    elems = [None, None]
    elems[0] = make_elem(info[0])
    elems[1] = make_elem(info[1])
    print("audio-dec:", info)
    return elems

def make_aac_enc(kbps):
    bps = kbps * 1024
    enc = make_elem("avenc_aac", {"bitrate": bps})
    parse = make_elem("aacparse")
    return parse, enc

def make_queuex(sinkTime, srcTime):
    elem = Gst.ElementFactory.make("queuex")
    if elem:
        elem.set_property("min-sink-interval=%d" % sinkTime)
        elem.set_property("min-src-interval=%d" % srcTime)
    else:
        return Gst.ElementFactory.make("queue")


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

    def set_playing(self, elems=[]):
        for e in elems:
            e.set_state(Gst.State.PLAYING)

    def link_elems(self, elems=[]):
        last = None
        for e in elems:
            if not last:
                last = e
            else:
                last.link(e)
                last=e

    def link_pads(self, elems=[]):
        last = None
        for e in elems:
            if not last:
                last = e
            else:
                src = last.get_static_pad("src")
                dst = e.get_static_pad("sink")
                #print("yzxu", last.get_name(), e.get_name(), dst)
                src.link(dst)
                last = e

    def convert_audio(self, bin, pad, aparse, aenc):
        convert = make_elem("audioconvert")
        queue1 = make_elem("queue")
        queue2 = make_elem("queue")
        self.add_elems([convert, queue1, aenc, aparse, queue2])

        self.link_elems([convert, queue1, aenc, queue2, self.mux])
        pad.link(convert.get_static_pad("sink"));
        self.set_playing([convert, queue1, aenc, queue2])

    def convert_video(self, bin, pad, vparse, venc):
        convert = make_elem("videoconvert")
        queue1 = make_elem("queue")
        queue2 = make_elem("queue")
        self.add_elems([convert, queue1, venc, vparse, queue2])

        self.link_elems([convert, queue1, venc, vparse, queue2, self.mux])
        pad.link(convert.get_static_pad("sink"))
        self.set_playing([convert, queue1, venc, vparse, queue2])

    def on_pad_added(self, obj, pad):
        caps = pad.get_current_caps()
        szcaps = caps.to_string()
        #print(type(caps), szcaps)
        if szcaps.startswith("video/"):
            vparse, venc = make_h264_enc(1024)
            self.convert_video(obj, pad, vparse, venc)
        elif szcaps.startswith("audio/"):
            aparse, aenc = make_aac_enc(64)
            self.convert_audio(obj, pad, aparse, aenc)

    def do_convert(self):
        self.pipeline = Gst.Pipeline()

        source = make_elem("filesrc", {"location": self.infile})
        db = make_elem("decodebin", None, "db")
        db.connect("pad-added", self.on_pad_added)
        mux = make_elem("mpegtsmux", None, "mux")
        sink = make_elem("filesink", {"location": self.outfile})
        self.add_elems([source, db, mux, sink])
        source.link(db)
        mux.link(sink)

        self.mux = mux
        self.sink = sink
        self.check_run()

    def do_seek(self):
        if self.offset == 0:
            return
        print("seek to offset:", self.offset)
        self.pipeline.set_state(Gst.State.PAUSED)
        #self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        seek_time = self.offset * Gst.SECOND
        #self.pipeline.seek(1.0, Gst.Format.TIME, Gst.SeekFlags.FLUSH, Gst.SeekType.SET,
        #        seek_time, Gst.SeekType.NONE, -1);
        #self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        self.pipeline.seek_simple(Gst.Format.TIME,  Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, seek_time)
        self.pipeline.set_state(Gst.State.PLAYING)
        self.offset = 0

    def on_message(self, bus, msg):
        #print("message:", msg, msg.type)
        if msg.type == Gst.MessageType.EOS:
            print("EOS and quit")
            self.pipeline.set_state(Gst.State.NULL)
            self.loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            self.pipeline.set_state(Gst.State.NULL)
            err, debug = msg.parse_error()
            print("Error: %s" % err, debug)
            self.loop.quit()
        elif msg.type == Gst.MessageType.STATE_CHANGED:
            #ret = self.pipeline.set_state(Gst.State.PLAYING)
            #print("Changed:", ret)
            pass
        pass

    def check_run(self):
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

        self.loop = GLib.MainLoop()
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        thread.start_new_thread(self.seek_thread, ())
        #self.do_seek()
        #GLib.timeout_add(200, self.do_seek)
        print("run begin:", ret)
        try:
            self.loop.run()
        except:
            pass
        print("run end");
        self.pipeline.set_state(Gst.State.NULL)

    def seek_thread(self):
        while True:
            time.sleep(0.05)
            success, position = self.pipeline.query_position(Gst.Format.TIME)
            if success:
                value = float(position) / Gst.SECOND
                print("position:", value)
                if value < 2:
                    self.do_seek()
                    break



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

    #GLib.threads_init()
    Gst.init(None)
    coder.do_print()
    coder.do_convert()

