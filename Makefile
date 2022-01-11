gstver = $(lastword $(shell gst-inspect-1.0 --version | grep GStreamer))

glib_inc=$(shell pkg-config --cflags glib-2.0)
glib_lib=$(shell pkg-config --libs glib-2.0)

gst_inc=$(shell pkg-config --cflags gstreamer-1.0)
gst_lib=$(shell pkg-config --libs gstreamer-base-1.0) $(shell pkg-config --libs gstreamer-1.0)

gstbase_inc=$(shell pkg-config --cflags gstreamer-plugins-base-1.0)
gstbase_lib=$(shell pkg-config --libs gstreamer-plugins-base-1.0)

gstvideo_lib=$(shell pkg-config --libs gstreamer-video-1.0)



cflags = $(glib_inc) $(gst_inc) $(gstbase_inc) -I$(gstver)
ldflags = $(gstbase_lib) $(gst_lib) $(glib_lib)
vflags = $(gstvideo_lib)


.c.o:
	@echo "> Compiling $< => $@"
	@$(CC) ${cflags} ${gstbase_inc} -c $< -o $@


### all
all: videoscale queue launch


### test
TEST_SRCS = gsttest.c
TEST_OBJS = $(TEST_SRCS:.c=.o)


### videoscale
VS_SRCS = $(gstver)/videoscale/gstvideoscale.c
VS_OBJS = $(VS_SRCS:.c=.o)
VS_LIB = libgstvideoscale2.dylib
VS_BIN = testvideoscale2.bin
videoscale: $(TEST_OBJS) $(VS_OBJS)
	@echo "=== Generate $(VS_LIB) ==="
	@$(CC) -shared -o $(VS_LIB) $(VS_OBJS) $(vflags) $(ldflags)
	@echo "=== Generate $(VS_BIN) ==="
	@$(CC) -o $(VS_BIN) $(TEST_OBJS) $(VS_OBJS) $(vflags) $(ldflags)
videoscale_clean:
	@$(RM) -f $(VS_OBJS) $(VS_LIB) $(VS_BIN)


### queue
QU_SRCS = $(gstver)/queue/gstqueue.c $(gstver)/queue/gstelements.c
QU_OBJS = $(QU_SRCS:.c=.o)
QU_LIB = libgstqueue3.dylib
QU_BIN = testqueue3.bin
queue: $(TEST_OBJS) $(QU_OBJS)
	@echo "=== Generate $(QU_LIB) ==="
	@$(CC) -shared -o $(QU_LIB) $(QU_OBJS) ${ldflags}
	@echo "=== Generate $(QU_BIN) ==="
	@$(CC) -o $(QU_BIN) $(TEST_OBJS) $(QU_OBJS) ${ldflags}
queue_clean:
	@$(RM) -f $(QU_OBJS) $(QU_LIB) $(QU_BIN)


### gst-launch
LH_SRCS = $(gstver)/gst-launch.c
LH_OBJS = $(LH_SRCS:.c=.o)
LH_BIN = gst-launch
launch: $(LH_OBJS)
	@echo "=== Generate $(LH_BIN) ==="
	@$(CC) -o $(LH_BIN) $(LH_OBJS) $(cflags) $(ldflags)

launch_clean:
	@$(RM) -f $(LH_OBJS) $(LH_BIN)


### clean
clean: videoscale_clean queue_clean launch_clean
	@rm -f $(TEST_OBJS)
