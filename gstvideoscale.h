/* GStreamer
 * Copyright (C) <1999> Erik Walthinsen <omega@cse.ogi.edu>
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

#ifndef __GST_VIDEO_SCALE2_H__
#define __GST_VIDEO_SCALE2_H__

#include <gst/gst.h>
#include <gst/video/video.h>
#include <gst/video/gstvideofilter.h>

G_BEGIN_DECLS

#define GST_TYPE_VIDEO_SCALE2 (gst_video_scale2_get_type())
#define GST_VIDEO_SCALE2_CAST(obj) ((GstVideoScale2 *)(obj))
G_DECLARE_FINAL_TYPE (GstVideoScale2, gst_video_scale2, GST, VIDEO_SCALE2,
    GstVideoFilter)


/**
 * GstVideoScale2Method:
 * @GST_VIDEO_SCALE2_NEAREST: use nearest neighbour scaling (fast and ugly)
 * @GST_VIDEO_SCALE2_BILINEAR: use 2-tap bilinear scaling (slower but prettier).
 * @GST_VIDEO_SCALE2_4TAP: use a 4-tap sinc filter for scaling (slow).
 * @GST_VIDEO_SCALE2_LANCZOS: use a multitap Lanczos filter for scaling (slow).
 * @GST_VIDEO_SCALE2_BILINEAR2: use a multitap bilinear filter
 * @GST_VIDEO_SCALE2_SINC: use a multitap sinc filter
 * @GST_VIDEO_SCALE2_HERMITE: use a multitap bicubic Hermite filter
 * @GST_VIDEO_SCALE2_SPLINE: use a multitap bicubic spline filter
 * @GST_VIDEO_SCALE2_CATROM: use a multitap bicubic Catmull-Rom filter
 * @GST_VIDEO_SCALE2_MITCHELL: use a multitap bicubic Mitchell filter
 *
 * The videoscale2 method to use.
 */
typedef enum {
  GST_VIDEO_SCALE2_NEAREST,
  GST_VIDEO_SCALE2_BILINEAR,
  GST_VIDEO_SCALE2_4TAP,
  GST_VIDEO_SCALE2_LANCZOS,

  GST_VIDEO_SCALE2_BILINEAR2,
  GST_VIDEO_SCALE2_SINC,
  GST_VIDEO_SCALE2_HERMITE,
  GST_VIDEO_SCALE2_SPLINE,
  GST_VIDEO_SCALE2_CATROM,
  GST_VIDEO_SCALE2_MITCHELL
} GstVideoScale2Method;

/**
 * GstVideoScale2:
 *
 * Opaque data structure
 */
struct _GstVideoScale2 {
  GstVideoFilter element;

  /* properties */
  GstVideoScale2Method method;
  gboolean add_borders;
  double sharpness;
  double sharpen;
  gboolean dither;
  int submethod;
  double envelope;
  gboolean gamma_decode;
  gint n_threads;

  GstVideoConverter *convert;

  gint borders_h;
  gint borders_w;
};

G_END_DECLS

#endif /* __GST_VIDEO_SCALE2_H__ */
