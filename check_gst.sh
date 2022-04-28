#
profile="video/mpegts,systemstream=true,packetsize=188:audio/mpeg,mpegversion=4,bitrate=65536:video/x-h264,stream-format=byte-stream,bitrate=1048576"

do_convert_audio_video()  {
    name="$1"
    video="$2"
    audio="$3"
    gst-launch-1.0 filesrc location="$name" name=fs \
	parsebin name=pb \
 	decodebin3 name=db \
	encodebin profile="$profile" name=eb \
	filesink location="/tmp/$name.out.ts" name=sink \
	fs. ! pb. \
	pb. ! $video ! queue ! db.sink_0 \
	db.video_0 ! queue ! eb.video_0 \
	pb. ! $audio ! queue ! db.sink_1 \
	db.audio_0 ! queue ! eb.audio_0 \
	eb. ! queuex min-sink-interval=5000 ! sink.
}

do_convert_video() {
    name="$1"
    video="$2"
    gst-launch-1.0 filesrc location="$name" name=fs \
	parsebin name=pb \
 	decodebin name=db \
	encodebin profile="$profile" name=eb \
	filesink location="/tmp/$name.out.ts" name=sink \
	fs. ! pb. \
	pb. ! $video ! queue ! db. \
	db. ! video/x-raw ! queue ! eb.video_0 \
	eb. ! queue ! sink.
}

do_convert_audio() {
    name="$1"
    audio="$2"
    gst-launch-1.0 filesrc location="$name" name=fs \
	parsebin name=pb \
 	decodebin name=db \
	encodebin profile="$profile" name=eb \
	filesink location="/tmp/$name.out.ts" name=sink \
	fs. ! pb. \
	pb. ! $audio ! queue ! db. \
	db. ! audio/x-raw ! queue ! eb.audio_0 \
	eb. ! queue ! sink.
}


mkdir -p /tmp/samples
fnames=$(ls samples/small.*)
for name in $fnames; do
	audio=$(gst-discoverer-1.0 -v $name 2>/dev/null | grep "audio:" | awk -F" " '{print $2}' | awk -F"," '{print $1}')
	video=$(gst-discoverer-1.0 -v $name 2>/dev/null | grep "video:" | awk -F" " '{print $2}' | awk -F"," '{print $1}')
	echo "\n===================="
	echo $name, $audio, $video
	echo "===================="
	if [ "#$audio" != "#" -a "#$video" != "#" ]; then
		echo ">>>>>>>> $audio and $video"
		do_convert_audio_video "$name" "$video" "$audio"
		echo
	else
		if [ "#$video" != "#" ]; then
			echo ">>>>>>>> only video: $video"
			do_convert_video "$name" "$video"
		fi
		if [ "#$audio" != "#" ]; then
			echo ">>>>>>>> only audio: $audio"
			do_convert_audio "$name" "$audio"
		fi
	fi
	sleep 1
done

exit 0

