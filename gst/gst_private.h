/* GStreamer
 * Copyright (C) 1999,2000 Erik Walthinsen <omega@cse.ogi.edu>
 *                    2000 Wim Taymans <wtay@chello.be>
 *
 * gst_private.h: Private header for within libgst
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

#ifndef __GST_PRIVATE_H__
#define __GST_PRIVATE_H__

#ifdef HAVE_CONFIG_H
# ifndef GST_LICENSE   /* don't include config.h twice, it has no guards */
#  include "config.h"
# endif
#endif

/* This needs to be before glib.h, since it might be used in inline
 * functions */
extern const char             g_log_domain_gstreamer[];

#include <glib.h>

#include <stdlib.h>
#include <string.h>

/* Needed for GST_API */
#include "gst/gstconfig.h"

/* Needed for GstRegistry * */
#include "gst/gstregistry.h"
#include "gst/gststructure.h"

/* we need this in pretty much all files */
#include "gst/gstinfo.h"

/* for the flags in the GstPluginDep structure below */
#include "gst/gstplugin.h"

/* for the pad cache */
#include "gst/gstpad.h"

/* for GstElement */
#include "gst/gstelement.h"

/* for GstDeviceProvider */
#include "gst/gstdeviceprovider.h"

/* for GstToc */
#include "gst/gsttoc.h"

#include "gst/gstdatetime.h"

//#include "gsttracerutils.h"

#endif /* __GST_PRIVATE_H__ */
