
glib_inc=$(shell pkg-config --cflags glib-2.0)
glib_lib=$(shell pkg-config --libs glib-2.0)

gst_inc=$(shell pkg-config --cflags gstreamer-1.0)
gst_lib=$(shell pkg-config --libs gstreamer-1.0)

cflags = $(glib_inc) $(gst_inc)
ldflags = $(gst_lib) $(glib_lib)

all:
	gcc -o gst-launch gst-launch.c $(cflags) $(ldflags)
