/* GStreamer
 * Copyright (C) 1999,2000 Erik Walthinsen <omega@cse.ogi.edu>
 *                    2003 Colin Walters <cwalters@gnome.org>
 *                    2000,2005,2007 Wim Taymans <wim.taymans@gmail.com>
 *                    2007 Thiago Sousa Santos <thiagoss@lcc.ufcg.edu.br>
 *
 * gstqueuex.h:
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Library General Public
 * License as published by the Free Software Foundation; either
 * version 2 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Library General Public License for more details.
 *
 * You should have received a copy of the GNU Library General Public
 * License along with this library; if not, write to the
 * Free Software Foundation, Inc., 51 Franklin St, Fifth Floor,
 * Boston, MA 02110-1301, USA.
 */
#ifndef __GST_QUEUEX_H__
#define __GST_QUEUEX_H__

#include <gst/gst.h>
#include <stdio.h>

G_BEGIN_DECLS

#define GST_TYPE_QUEUEX \
  (gst_queuex_get_type())
#define GST_QUEUEX(obj) \
  (G_TYPE_CHECK_INSTANCE_CAST((obj),GST_TYPE_QUEUEX,GstQueuex))
#define GST_QUEUEX_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_CAST((klass),GST_TYPE_QUEUEX,GstQueuexClass))
#define GST_IS_QUEUEX(obj) \
  (G_TYPE_CHECK_INSTANCE_TYPE((obj),GST_TYPE_QUEUEX))
#define GST_IS_QUEUEX_CLASS(klass) \
  (G_TYPE_CHECK_CLASS_TYPE((klass),GST_TYPE_QUEUEX))
#define GST_QUEUEX_CAST(obj) \
  ((GstQueuex *)(obj))

typedef struct _GstQueuex GstQueuex;
typedef struct _GstQueuexSize GstQueuexSize;
typedef struct _GstQueuexClass GstQueuexClass;
typedef struct _GstQueuexRange GstQueuexRange;

/* used to keep track of sizes (current and max) */
struct _GstQueuexSize
{
  guint buffers;
  guint bytes;
  guint64 time;
  guint64 rate_time;
};

struct _GstQueuexRange
{
  GstQueuexRange *next;

  guint64 offset;          /* offset of range start in source */
  guint64 rb_offset;       /* offset of range start in ring buffer */
  guint64 writing_pos;     /* writing position in source */
  guint64 rb_writing_pos;  /* writing position in ring buffer */
  guint64 reading_pos;     /* reading position in source */
  guint64 max_reading_pos; /* latest requested offset in source */
};

struct _GstQueuex
{
  GstElement element;

  /*< private > */
  GstPad *sinkpad;
  GstPad *srcpad;

  /* upstream size in bytes (if downstream is operating in pull mode) */
  guint64 upstream_size;

  /* segments to keep track of timestamps */
  GstSegment sink_segment;
  GstSegment src_segment;

  /* Position of src/sink */
  GstClockTime sinktime, srctime;
  /* TRUE if either position needs to be recalculated */
  gboolean sink_tainted, src_tainted;
  /* Bitrates taken from tags */
  guint sink_tags_bitrate;
  guint src_tags_bitrate;

  /* flowreturn when srcpad is paused */
  GstFlowReturn srcresult;
  GstFlowReturn sinkresult;
  gboolean is_eos;
  gboolean unexpected;

  /* the queue of data we're keeping our hands on */
  GQueue queue;

  GCond query_handled;
  gboolean last_query; /* result of last serialized query */
  GstQuery *last_handled_query;

  GstQueuexSize cur_level;       /* currently in the queue */
  GstQueuexSize max_level;       /* max. amount of data allowed in the queue */
  gboolean use_buffering;
  gboolean use_tags_bitrate;
  gboolean use_rate_estimate;
  GstClockTime buffering_interval;

  /* low/high watermarks for buffering */
  gint low_watermark;
  gint high_watermark;

  /* current buffering state */
  gboolean is_buffering;
  gint buffering_percent;

  /* for measuring input/output rates */
  GTimer *in_timer;
  gboolean in_timer_started;
  gdouble last_update_in_rates_elapsed;
  gdouble last_in_elapsed;
  guint64 bytes_in;
  gdouble byte_in_rate;
  gdouble byte_in_period;

  GTimer *out_timer;
  gboolean out_timer_started;
  gdouble last_out_elapsed;
  guint64 bytes_out;
  gdouble byte_out_rate;

  GMutex qlock;                /* lock for queue (vs object lock) */
  gboolean waiting_add;
  GCond item_add;              /* signals buffers now available for reading */
  gboolean waiting_del;
  GCond item_del;              /* signals space now available for writing */

  /* temp location stuff */
  gchar *temp_template;
  gboolean temp_location_set;
  gchar *temp_location;
  gboolean temp_remove;
  FILE *temp_file;
  /* list of downloaded areas and the current area */
  GstQueuexRange *ranges;
  GstQueuexRange *current;
  /* we need this to send the first new segment event of the stream
   * because we can't save it on the file */
  gboolean segment_event_received;
  GstEvent *starting_segment;
  gboolean seeking;

  GstEvent *stream_start_event;

  guint64 ring_buffer_max_size;
  guint8 * ring_buffer;

  volatile gint downstream_may_block;

  GstBufferingMode mode;
  gint64 buffering_left;
  gint avg_in;
  gint avg_out;
  gboolean percent_changed;
  GMutex buffering_post_lock; /* assures only one posted at a time */
};

struct _GstQueuexClass
{
  GstElementClass parent_class;
};

G_GNUC_INTERNAL GType gst_queuex_get_type (void);

G_END_DECLS

#endif /* __GST_QUEUEX_H__ */
