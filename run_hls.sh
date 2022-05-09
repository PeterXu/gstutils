(
pkill -f "pyhlsvod.py"
pkill -f "multiprocessing.*_tracker"
pkill -f "multiprocessing.spawn"
sleep 1

[ -f "/opt/media/env.sh" ] && . /opt/media/env.sh
[ -f "/opt/wspace/pyhlsvod.py" ] && cd /opt/wspace
rm -f nohup.out
rm -f /tmp/hls_*.txt
rm -f /var/log/hlsvod/hls_*.txt
[ -f "$DEEPFS_SO" ] && export LD_PRELOAD="$LD_PRELOAD:$DEEPFS_SO"
nohup python3 pyhlsvod.py &
) >/dev/null 2>&1 &
