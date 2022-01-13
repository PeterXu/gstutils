/* GStreamer
 * Copyright (C) 1999,2000 Erik Walthinsen <omega@cse.ogi.edu>
 *                    2000 Wim Taymans <wtay@chello.be>
 *
 * gstelements.c:
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
/**
 * plugin-coreelements:
 *
 * GStreamer core elements
 */

#include <gst/gst.h>

#include "gstqueuex.h"
#include "gstvideoscalex.h"

#include "gst/gst-i18n-lib.h"

static gboolean
plugin_init (GstPlugin * plugin)
{
  if (!gst_element_register (plugin, "queuex", GST_RANK_NONE,
          gst_queuex_get_type ()))
    return FALSE;

  if (!gst_element_register (plugin, "videoscalex", GST_RANK_NONE,
          GST_TYPE_VIDEO_SCALEX))
    return FALSE;

  return TRUE;
}

GST_PLUGIN_DEFINE (GST_VERSION_MAJOR, GST_VERSION_MINOR, larks,
    "GStreamer larks elements", plugin_init, VERSION, GST_LICENSE,
    GST_PACKAGE_NAME, GST_PACKAGE_ORIGIN);
