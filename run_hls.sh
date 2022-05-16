(
while [ ! -f "/opt/media/env.sh" ];
do
    pkill -f "pyhlsvod.py"
    pkill -f "multiprocessing.*_tracker"
    pkill -f "multiprocessing.spawn"
    sleep 3
done
sleep 3

. /opt/media/env.sh
[ -f "/opt/media/wspace/pyhlsvod.py" ] && cd /opt/media/wspace

rm -f nohup.out
rm -f /tmp/hls_*.txt
rm -f /var/log/hlsvod/hls_*.txt
[ -f "$DEEPFS_SO" ] && export LD_PRELOAD="$LD_PRELOAD:$DEEPFS_SO"
nohup python3 pyhlsvod.py &
) >/dev/null 2>&1 &
