import os
import sys
import time
import getopt

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
    enc = make_elem("mppvideoenc", props1)
    if not enc:
        enc = make_elem("avenc_h264_videotoolbox", props2)
    if not enc:
        enc = make_elem("avenc_h264", props2)
    return enc

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

def make_audio_enc(kbps):
    bps = kbps * 1024
    enc = make_elem("avenc_aac", {"bitrate": bps})
    return enc

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

    def convert_media(self, srcbin, minfo, outf):
        if not minfo[1]:
            return
        queue = make_elem("queue")
        sink = make_elem("filesink", {"location": outf})

        if minfo[0]:
            self.pipeline.add(minfo[0])
        self.pipeline.add(queue)
        self.pipeline.add(minfo[1])
        self.pipeline.add(sink)

        if minfo[0]:
            srcbin.link(minfo[0])
            minfo[0].link(queue)
        else:
            srcbin.link(queue)
        queue.link(minfo[1])
        minfo[1].link(sink)

    def on_pad_added(self, obj, pad):
        caps = pad.get_current_caps()
        szcaps = caps.to_string()
        print("====")
        print(type(caps), szcaps)
        print("====")
        if szcaps.startswith("video/"):
            vinfo = make_video_dec(szcaps)
            self.convert_media(obj, vinfo, "/tmp/out1.ts")
        elif szcaps.startswith("audio/"):
            ainfo = make_audio_dec(szcaps)
            self.convert_media(obj, ainfo, "/tmp/out2.ts")
            self.pipeline.set_state(Gst.State.PLAYING);

    def do_convert(self):
        self.pipeline = Gst.Pipeline()
        source = make_elem("filesrc", {"location": self.infile})
        self.pipeline.add(source)

        pb = make_elem("parsebin", None, "pb")
        self.pipeline.add(pb)
        pb.connect("pad-added", self.on_pad_added)
        source.link(pb)

        #mux = make_elem("mpegtsmux", None, "mux")
        #self.pipeline.add(mux)

        #sink = make_elem("filesink")
        #self.pipeline.add(sink)

        self.check_run2()


    def on_message(self, bus, msg):
        #print("message:", msg, msg.type)
        if msg.type == Gst.MessageType.EOS:
            self.pipeline.set_state(Gst.State.NULL)
            self.loop.quit()
        elif msg.type == Gst.MessageType.ERROR:
            self.pipeline.set_state(Gst.State.NULL)
            err, debug = msg.parse_error()
            print("Error: %s" % err, debug)
            self.loop.quit()
        pass

    def check_run2(self):
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

        self.loop = GLib.MainLoop()
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        print("run begin:", ret)
        try:
            self.loop.run()
        except:
            pass
        print("run end");
        self.pipeline.set_state(Gst.State.NULL)

    def check_run(self):
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("ERROR: Unable to set the pipeline to the playing state")
            sys.exit(1)

        terminate = False
        bus = self.pipeline.get_bus()
        while True:
            msg = bus.timed_pop_filtered(Gst.CLOCK_TIME_NONE,
                    Gst.MessageType.STATE_CHANGED | Gst.MessageType.EOS | Gst.MessageType.ERROR)
            if not msg:
                print("====")
                continue
            t = msg.type
            if t == Gst.MessageType.ERROR:
                err, dbg = msg.parse_error()
                print("ERROR:", msg.src.get_name(), " ", err.message)
                if dbg:
                    print("debugging info:", dbg)
                terminate = True
            elif t == Gst.MessageType.EOS:
                print("End-Of-Stream reached")
                terminate = True
            elif t == Gst.MessageType.STATE_CHANGED:
                if msg.src == self.pipeline:
                    old_state, new_state, pending_state = msg.parse_state_changed()
                    print("Pipeline state changed from {0:s} to {1:s}".format(
                        Gst.Element.state_get_name(old_state),
                        Gst.Element.state_get_name(new_state)))
                pass
            else:
                print("ERROR: Unexpected message received")
                break
            if terminate:
                break;
        self.pipeline.set_state(Gst.State.NULL)


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
    coder.offset = 3 # default 3s

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

