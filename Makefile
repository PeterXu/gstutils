gstver = $(lastword $(shell gst-inspect-1.0 --version | grep GStreamer))
tmpver = $(subst ., ,$(gstver))
gstpath = $(word 1,$(tmpver)).$(word 2,$(tmpver))

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
all: prepare larks

prepare:
	@echo "=== current gstreamer version $(gstver) and symbol link to $(gstpath)"
	@rm -f $(gstver)
	@ln -s $(gstpath) $(gstver)

### test
TEST_SRCS = tests/gsttest.c
TEST_OBJS = $(TEST_SRCS:.c=.o)

### larks
LARKS_SRCS = \
	$(gstver)/gstqueuex.c \
	$(gstver)/gstvideoscalex.c \
	$(gstver)/gstelements.c

LARKS_OBJS = $(LARKS_SRCS:.c=.o)
LARKS_LIB = libgstlarks.dylib
LARKS_BIN = testlarks.bin

larks: $(LARKS_OBJS)
	@echo "=== Generate $(LARKS_LIB) ==="
	@$(CC) -shared -o $(LARKS_LIB) $(LARKS_OBJS) $(vflags) $(ldflags)

larks_test: $(TEST_OBJS) $(LARKS_OBJS)
	@echo "=== Generate $(LARKS_BIN) ==="
	@$(CC) -o $(LARKS_BIN) $(TEST_OBJS) $(LARKS_OBJS) $(vflags) $(ldflags)

larks_clean:
	@$(RM) -f $(LARKS_OBJS) $(LARKS_LIB) $(LARKS_BIN)

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
clean: larks_clean launch_clean
	@rm -f $(TEST_OBJS)
	@rm -f $(gstver)


### check
check:
	@export GST_DEBUG=2;GST_PLUGIN_LOADING=5;GST_REGISTRY=5
	@echo $(shell gst-inspect-1.0 --gst-plugin-path=. larks)

