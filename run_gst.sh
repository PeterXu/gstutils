#export GST_OPTIONS="--gst-plugin-path=."
#lua scripts.lua

python3 gstconvert.py -i samples/small.mkv -t 3 -s 640x360 /tmp/outh264.ts
