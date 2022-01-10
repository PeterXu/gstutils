
glib_inc=$(shell pkg-config --cflags glib-2.0)
glib_lib=$(shell pkg-config --libs glib-2.0)

gst_inc=$(shell pkg-config --cflags gstreamer-1.0)
gst_lib=$(shell pkg-config --libs gstreamer-1.0)

gstbase_inc=$(shell pkg-config --cflags gstreamer-plugins-base-1.0)
gstbase_lib=$(shell pkg-config --libs gstreamer-plugins-base-1.0)

cflags = $(glib_inc) $(gst_inc) -DBUILD_TEST
ldflags = -lgstbase-1.0 $(gst_lib) $(glib_lib)


# videoscale
all: base
	cc -c gstvideoscale.c -o gstvideoscale.o ${cflags} ${gstbase_inc}
	cc -shared -o libgstvideoscale2.dylib gstvideoscale.o ${gstbase_lib} -lgstvideo-1.0.0 ${ldflags}
	cc -o testvideoscale2.bin gsttest.o gstvideoscale.o ${gstbase_lib} -lgstvideo-1.0.0 ${ldflags}

base:
	cc -c gsttest.c -o gsttest.o

# gstqueue: 1.18.5
queue: base
	cc -c gstqueue.c -o gstqueue.o ${cflags}
	cc -c gstelements.c -o gstelements.o ${cflags}
	cc -o testqueue3.bin gsttest.o gstqueue.o gstelements.o ${ldflags}
	cc -shared -o libgstqueue3.dylib gstqueue.o gstelements.o ${ldflags}

# gst-launch: 1.18.5
launch:
	gcc -o gst-launch gst-launch.c $(cflags) $(ldflags)


clean:
	rm -f *.o *.dylib *.bin
	rm -f gst-launch
