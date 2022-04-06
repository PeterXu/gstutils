#export GST_OPTIONS="--gst-plugin-path=."
#lua scripts.lua
#export GST_DEBUG=2;GST_PLUGIN_LOADING=5;GST_REGISTRY=5

rm -f /tmp/out.ts
rm -f /tmp/out1.ts
rm -f /tmp/out2.ts
#python3 gstconvert.py -i /tmp/test.mkv -t 3 -s 640x360 /tmp/outh264.ts
python3 gsttranscoder.py -i /tmp/test.mkv -t 3 -s 640x360 /tmp/outh264.ts
