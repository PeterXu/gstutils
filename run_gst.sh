#export GST_OPTIONS="--gst-plugin-path=."
#lua scripts.lua

rm -f /tmp/out.ts
rm -f /tmp/out1.ts
rm -f /tmp/out2.ts
python3 gstconvert.py -i samples/small.mkv -t 3 -s 640x360 /tmp/outh264.ts
