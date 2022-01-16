#include "gstqueuex_ext.h"

/**
 * init
 */

static void
gst_queuex_ext_init (GstQueuexExt *ext)
{
    if (ext) {
        ext->min_sink_interval = 0;
        ext->last_sink_time = 0;

        ext->min_src_interval = 0;
        ext->last_src_time = 0;
    }
}

static GParamSpec *
gst_queuex_ext_sink_property ()
{
    return g_param_spec_uint64 ("min-sink-interval", "Interval (microseconds)",
            "Min interval between sink-pad incoming adjacent packets",
            0, G_MAXUINT64, 0, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);
}

static GParamSpec *
gst_queuex_ext_src_property ()
{
    return g_param_spec_uint64 ("min-src-interval", "Interval (microseconds)",
            "Min interval between src-pad outgoing adjacent packets",
            0, G_MAXUINT64, 0, G_PARAM_READWRITE | G_PARAM_STATIC_STRINGS);
}


/**
 * get property value
 */

static void
gst_queuex_ext_get_sink_interval (GstQueuexExt *ext, GValue * value)
{
    if (ext && value) {
        g_value_set_uint64 (value, ext->min_sink_interval);
    }
}

static void
gst_queuex_ext_get_src_interval (GstQueuexExt *ext, GValue * value)
{
    if (ext && value) {
        g_value_set_uint64 (value, ext->min_src_interval);
    }
}

/**
 * set property value
 */

static void
gst_queuex_ext_set_sink_interval (GstQueuexExt *ext, const GValue * value)
{
    if (ext && value) {
        ext->min_sink_interval = g_value_get_uint64 (value);
    }
}

static void
gst_queuex_ext_set_src_interval (GstQueuexExt *ext, const GValue * value)
{
    if (ext && value) {
        ext->min_src_interval = g_value_get_uint64 (value);
    }
}

/**
 * check src/sink timeou
 */

static void
gst_queuex_ext_check_timeout (guint64 *last_time, guint64 min_interval)
{
  /* wait interval */
  if ((last_time != NULL) && min_interval > 0) {
      guint64 current = g_get_real_time ();
      if (current < (*last_time) + min_interval) {
          gint64 diff = (*last_time) + min_interval - current;
          g_usleep (diff);
          current = g_get_real_time ();
      }
      *last_time = current;
  }
}

static void
gst_queuex_ext_check_sink_timeout (GstQueuexExt *ext)
{
    if (ext) {
        gst_queuex_ext_check_timeout (&ext->last_sink_time, ext->min_sink_interval);
    }
}

static void
gst_queuex_ext_check_src_timeout (GstQueuexExt *ext)
{
    if (ext) {
        gst_queuex_ext_check_timeout (&ext->last_src_time, ext->min_src_interval);
    }
}
