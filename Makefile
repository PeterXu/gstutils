
glib_inc=$(shell pkg-config --cflags glib-2.0)
glib_lib=$(shell pkg-config --libs glib-2.0)

gst_inc=$(shell pkg-config --cflags gstreamer-1.0)
gst_lib=$(shell pkg-config --libs gstreamer-1.0) -lgstbase-1.0

gstbase_inc=$(shell pkg-config --cflags gstreamer-plugins-base-1.0)
gstbase_lib=$(shell pkg-config --libs gstreamer-plugins-base-1.0) -lgstvideo-1.0.0

cflags = $(glib_inc) $(gst_inc) $(gstbase_inc)
ldflags = $(gstbase_lib) $(gst_lib) $(glib_lib)



.c.o:
	@echo "> Compiling $< => $@"
	@$(CC) ${cflags} ${gstbase_inc} -c $< -o $@


# test
TEST_SRCS = gsttest.c
TEST_OBJS = $(TEST_SRCS:.c=.o)


# videoscale: 1.18.5
VS_SRCS = gstvideoscale.c
VS_OBJS = $(VS_SRCS:.c=.o)
VS_LIB = libgstvideoscale2.dylib
VS_BIN = testvideoscale2.bin

videoscale: $(TEST_OBJS) $(VS_OBJS)
	@echo "=== Generate $(VS_LIB) ==="
	@$(CC) -shared -o $(VS_LIB) $(VS_OBJS) $(ldflags)
	@echo "=== Generate $(VS_BIN) ==="
	@$(CC) -o $(VS_BIN) $(TEST_OBJS) $(VS_OBJS) $(ldflags)


# gstqueue: 1.18.5
QU_SRCS = gstqueue.c gstelements.c
QU_OBJS = $(QU_SRCS:.c=.o)
QU_LIB = libgstqueue3.dylib
QU_BIN = testqueue3.bin

queue: $(TEST_OBJS) $(QU_OBJS)
	@echo "=== Generate $(QU_LIB) ==="
	@$(CC) -shared -o $(QU_LIB) $(QU_OBJS) ${ldflags}
	@echo "=== Generate $(QU_BIN) ==="
	@$(CC) -o $(QU_BIN) $(TEST_OBJS) $(QU_OBJS) ${ldflags}


# gst-launch: 1.18.5
TARGET = gst-launch
launch:
	@echo "=== Generate $(TARGET) ==="
	@$(CC) -o $(TARGET) gst-launch.c $(cflags) $(ldflags)


# clean
clean:
	@rm -f *.o *.dylib *.bin
	@rm -f $(TARGET)
