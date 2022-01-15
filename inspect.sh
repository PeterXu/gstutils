
export GST_DEBUG=2;GST_PLUGIN_LOADING=5;GST_REGISTRY=5
gst-inspect-1.0 --gst-plugin-path=. $1
