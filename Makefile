
glib_inc=$(shell pkg-config --cflags glib-2.0)
glib_lib=$(shell pkg-config --libs glib-2.0)

gst_inc=$(shell pkg-config --cflags gstreamer-1.0)
gst_lib=$(shell pkg-config --libs gstreamer-1.0)

cflags = $(glib_inc) $(gst_inc) -DBUILD_TEST
ldflags = -lgstbase-1.0 $(gst_lib) $(glib_lib)

# gstqueue: 1.18.5
all:
	cc -c gsttest.c -o gsttest.o
	cc -c gstqueue.c -o gstqueue.o ${cflags}
	cc -c gstelements.c -o gstelements.o ${cflags}
	cc -o testgst gsttest.o gstqueue.o gstelements.o ${ldflags}
	cc -shared -o libgstqueue.dylib gstqueue.o gstelements.o ${ldflags}

# gst-launch: 1.18.5
launch:
	gcc -o gst-launch gst-launch.c $(cflags) $(ldflags)
