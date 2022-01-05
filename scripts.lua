function gst_inspect(plugin)
    local line = string.format("gst-inspect-1.0 --exists %s", plugin)
    return os.execute(line)
end

function gst_inspect_vcodec(bps) 
    local codec = nil
    if gst_inspect("mpph264enc") then
        codec = string.format("mpph264enc rc-mode=vbr bps=%d profile=main ! h264parse", bps)
    elseif gst_inspect("avenc_h264") then
        codec = string.format("avenc_h264 pass=pass1 bitrate=%d profile=main ! h264parse", bps)
    elseif gst_inspect("avenc_h264_videotoolbox") then
        codec = string.format("avenc_h264_videotoolbox pass=pass1 bitrate=%d profile=main ! h264parse", bps)
    end
    return codec
end

function gst_typefind_demux(src)
    local demux = nil
    local line = string.format("gst-typefind-1.0 %s | sed 's#.* - video/##g' | sed 's#,.*##g'", src)
    local fp = io.popen(line)
    local result = fp:read()
    if result == "quicktime" then
        demux="qtdemux"
    elseif result == "x-matroska" then
        demux="matroskademux"
    end
    -- TODO: skip H265 video-codec
    return demux
end

function gst_transcode(src, start, speed, width, height, fps, bps, fd, outf)
    local vcodec = gst_inspect_vcodec(bps)
    if vcodec == nil then
        return nil
    end

    local demux = gst_typefind_demux(src)
    if demux == nil then
        return nil
    end

    start = "00:00:00"
    local await = string.format("avwait mode=timecode target-timecode-string=\"00:00:40:00\" ! audio/x-raw")
    local vwait = string.format("avwait mode=timecode target-timecode-string=\"00:00:40:00\" ! video/x-raw")
    local vrate = string.format("videorate rate=%f ! video/x-raw,framerate=%d/1", speed, fps)
    local vscale = string.format("videoscale ! video/x-raw,width=%d,height=%d", width, height)
    local sink = string.format("filesink location=%s", outf)
    if fd >= 0 and fd <= 65535 then
        sink = string.format("fdsink fd=%d", fd)
    end

    local line

    if true then
    line = string.format([[
        gst-launch-1.0 filesrc location=%s ! %s name=demux \
         demux.audio_0 ! queue ! mpegtsmux name=mux \
         demux.video_0 ! decodebin ! %s ! queue ! %s ! %s ! %s ! mux. \
         mux. ! %s]],
        src, demux,
        vwait, vrate, vscale, vcodec, sink);
    return line
    end

    line = string.format([[
        gst-launch-1.0 filesrc location=%s ! %s name=demux \
         demux.audio_0 ! queue ! mpegtsmux name=mux \
         demux.video_0 ! decodebin ! queue ! %s ! mux. \
         mux. ! %s]],
        src, demux, codec, sink);
    return line;
end


function test_gst()
    local fname = "/Users/peter/Downloads/samples/SampleVideo_1280x720_20mb.mp4"
    start = "00:00:10"
    speed = 1.0
    width = 1280/2
    height = 720/2
    fps = 25
    bps = 500*1000
    local cmd = gst_transcode(fname, start, speed, width, height, fps, bps, -1, "/tmp/out.ts")
    print(cmd)
    os.execute(cmd)
end

test_gst()
