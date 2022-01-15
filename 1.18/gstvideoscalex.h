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

#ifndef __GST_VIDEO_SCALEX_H__
#define __GST_VIDEO_SCALEX_H__

#include <gst/gst.h>
#include <gst/video/video.h>
#include <gst/video/gstvideofilter.h>

G_BEGIN_DECLS

#define GST_TYPE_VIDEO_SCALEX (gst_video_scalex_get_type())
#define GST_VIDEO_SCALEX_CAST(obj) ((GstVideoScalex *)(obj))
G_DECLARE_FINAL_TYPE (GstVideoScalex, gst_video_scalex, GST, VIDEO_SCALEX,
    GstVideoFilter)


/**
 * GstVideoScalexMethod:
 * @GST_VIDEO_SCALEX_NEAREST: use nearest neighbour scaling (fast and ugly)
 * @GST_VIDEO_SCALEX_BILINEAR: use 2-tap bilinear scaling (slower but prettier).
 * @GST_VIDEO_SCALEX_4TAP: use a 4-tap sinc filter for scaling (slow).
 * @GST_VIDEO_SCALEX_LANCZOS: use a multitap Lanczos filter for scaling (slow).
 * @GST_VIDEO_SCALEX_BILINEAR2: use a multitap bilinear filter
 * @GST_VIDEO_SCALEX_SINC: use a multitap sinc filter
 * @GST_VIDEO_SCALEX_HERMITE: use a multitap bicubic Hermite filter
 * @GST_VIDEO_SCALEX_SPLINE: use a multitap bicubic spline filter
 * @GST_VIDEO_SCALEX_CATROM: use a multitap bicubic Catmull-Rom filter
 * @GST_VIDEO_SCALEX_MITCHELL: use a multitap bicubic Mitchell filter
 *
 * The videoscale method to use.
 */
typedef enum {
  GST_VIDEO_SCALEX_NEAREST,
  GST_VIDEO_SCALEX_BILINEAR,
  GST_VIDEO_SCALEX_4TAP,
  GST_VIDEO_SCALEX_LANCZOS,

  GST_VIDEO_SCALEX_BILINEAR2,
  GST_VIDEO_SCALEX_SINC,
  GST_VIDEO_SCALEX_HERMITE,
  GST_VIDEO_SCALEX_SPLINE,
  GST_VIDEO_SCALEX_CATROM,
  GST_VIDEO_SCALEX_MITCHELL
} GstVideoScalexMethod;

/**
 * GstVideoScalex:
 *
 * Opaque data structure
 */
struct _GstVideoScalex {
  GstVideoFilter element;

  /* properties */
  GstVideoScalexMethod method;
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

#endif /* __GST_VIDEO_SCALEX_H__ */
