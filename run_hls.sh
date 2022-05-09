pkill -f pyhlsvod.py
sleep 1

rm -f /tmp/hls_*.txt
rm -f /var/log/hlsvod/hls_*.txt
[ -f "$DEEPFS_SO" ] && export LD_PRELOAD="$LD_PRELOAD:$DEEPFS_SO"
nohup python3 pyhlsvod.py &
