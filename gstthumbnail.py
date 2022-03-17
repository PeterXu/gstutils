import os
import sys
import time
import getopt

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

def get_frame(path, offset=5, mtype="image/png", width=0, height=0):
    pipeline = Gst.parse_launch('playbin')
    pipeline.props.uri = 'file://' + os.path.abspath(path)
    pipeline.props.audio_sink = Gst.ElementFactory.make('fakesink')
    pipeline.props.video_sink = Gst.ElementFactory.make('fakesink')
    pipeline.set_state(Gst.State.PAUSED)

    # Wait for state change to finish.
    pipeline.get_state(Gst.CLOCK_TIME_NONE)
    time.sleep(0.5)

    # Seek time
    seek_time = offset * Gst.SECOND
    pipeline.seek(1.0, Gst.Format.TIME, Gst.SeekFlags.FLUSH, Gst.SeekType.SET,
            seek_time, Gst.SeekType.NONE, -1);

    # Wait for seek to finish.
    pipeline.get_state(Gst.CLOCK_TIME_NONE)
    time.sleep(0.5)

    caps = Gst.Caps.from_string(mtype)
    #caps.set_value("pixel-aspect-ratio", "(fraction)1/1")
    if width > 0: caps.set_value("width", width)
    if height > 0: caps.set_value("height", height)
    buf = pipeline.emit('convert-sample', caps)
    if not buf:
        return None
    cache = buf.get_buffer()
    ret, mmap = cache.map(Gst.MapFlags.READ)
    if not ret:
        return None
    data = mmap.data
    pipeline.set_state(Gst.State.NULL)
    return data

def main(source, dest, offset, mtype, width, height):
    Gst.init(None)
    image = get_frame(source, offset, mtype, width, height)
    if image != None:
        print("success")
        with open(dest, 'wb') as fp:
            fp.write(image)
    else:
        print("failed")

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

    # default offset: 3seconds
    source, dest, offset = None, args[0], 3
    mtype, width, height = "", 0, 0
    for o, a in opts:
        if o == "-h":
            help_usage(sys.argv[0], 0)
        elif o == "-i":
            source = a
        elif o == "-t":
            try:
                offset = int(a)
            except:
                help_usage(sys.argv[0], 2)
        elif o == "-s":
            try:
                size = a.split("x")
                width = int(size[0])
                height = int(size[1])
            except:
                help_usage(sys.argv[0], 2)
        else:
            help_usage(sys.argv[0], 2)
    fname, ext = os.path.splitext(dest)
    if ext == ".png":
        mtype = "image/png"
    elif ext == ".jpg" or ext == ".jpeg":
        mtype = "image/jpeg"
    else:
        print("only support png or jpg")
        sys.exit(2)
    #print(source, dest, offset, mtype, width, height)
    main(source, dest, offset, mtype, width, height)

