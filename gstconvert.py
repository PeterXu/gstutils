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

def make_elem(name, prop=None, value=None):
    elem = Gst.ElementFactory.make(name)
    if elem and prop:
        elem.set_property(prop, value)
    return elem
def make_video_dec(vtype):
    return Gst.ElementFactory.make("avdec_h264")
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

    def convert_aac(self, srcbin, srcpad):
        parse = make_elem("aacparse")
        self.pipeline.add(parse)

        queue = make_elem("queue")
        self.pipeline.add(queue)

        dec = make_elem("avdec_aac")
        self.pipeline.add(dec)

        sink = make_elem("filesink", "location", "/tmp/out2.ts")
        self.pipeline.add(sink)


        srcbin.link(parse)
        parse.link(queue)
        queue.link(dec)
        dec.link(sink)
        self.pipeline.set_state(Gst.State.PLAYING);

    def convert_h264(self, srcbin, srcpad):
        parse = make_elem("h264parse")
        self.pipeline.add(parse)
        
        queue = make_elem("queue")
        self.pipeline.add(queue)

        dec = make_h264_dec()
        self.pipeline.add(dec)

        sink = make_elem("filesink", "location", "/tmp/out1.ts")
        self.pipeline.add(sink)

        srcbin.link(parse)
        parse.link(queue)
        queue.link(dec)
        dec.link(sink)
        pass

    def on_pad_added(self, obj, pad):
        caps = pad.get_current_caps()
        struct = caps.get_structure(0)
        ctype = struct.get_name()
        print("====")
        print(caps)
        print(struct)
        print(ctype)
        print("====")
        if ctype == "video/x-h264":
            self.convert_h264(obj, pad)
        elif ctype == "audio/mpeg":
            self.convert_aac(obj, pad)
            pass

    def do_convert(self):
        self.pipeline = Gst.Pipeline()
        source = make_elem("filesrc")
        source.props.location = self.infile
        self.pipeline.add(source)

        pb = Gst.ElementFactory.make("parsebin", "pb")
        self.pipeline.add(pb)
        pb.connect("pad-added", self.on_pad_added)
        source.link(pb)

        mux = make_elem("mpegtsmux", "mux")
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

    GLib.threads_init()
    Gst.init(None)
    coder.do_print()
    coder.do_convert()

