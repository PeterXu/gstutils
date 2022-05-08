pkill -f pyhlsvod.py
sleep 1

rm -f /tmp/hls_out.txt
rm -f /tmp/hls_client.txt
rm -f /tmp/hls_service_*.txt
nohup python3 pyhlsvod.py >/dev/null 2>&1 &
