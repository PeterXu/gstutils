export LD_PRELOAD=/usr/local/openresty/nginx/lua/backend/nginx/deepfs.so
pkill -f pyhlsvod.py
sleep 1

rm -f /tmp/hls_out.txt
rm -f /tmp/hls_client.txt
rm -f /tmp/hls_service_*.txt
python3 pyhlsvod.py
