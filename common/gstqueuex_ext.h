#ifndef __GST_QUEUEX_EXT_H__
#define __GST_QUEUEX_EXT_H__

#include <gst/gst.h>
#include <stdio.h>

struct _GstQueuexExt {
  guint64 min_sink_interval;
  guint64 last_sink_time;

  guint64 min_src_interval;
  guint64 last_src_time;
};

typedef struct _GstQueuexExt GstQueuexExt;

#endif // __GST_QUEUEX_EXT_H__
