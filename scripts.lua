function gst_which(shcmd)
    local line = string.format("which %s >/dev/null", shcmd)
    return os.execute(line)
end

function gst_launch(opts)
    local name1 = "./gst-launch"
    local name2 = "gst-launch-1.0"
    if gst_which(name1) then
        return string.format("%s %s", name1, opts)
    elseif gst_which(name2) then
        return string.format("%s %s", name2, opts)
    end
    return nil
end

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

function gst_transcode(src, start, speed, width, height, fps, bps, outf)
    local vcodec = gst_inspect_vcodec(bps)
    if vcodec == nil then
        return nil
    end

    local demux = gst_typefind_demux(src)
    if demux == nil then
        return nil
    end

    local opts = ""

    local sink
    local dst = tonumber(outf)
    if dst == nil then
        sink = string.format("filesink location=%s", outf)
    else
        sink = string.format("fdsink fd=%d", dst)
        if dst == 1 then
            opts = "-q"
        end
    end

    local await = string.format("avwait mode=timecode target-timecode-string=\"%s:00\" ! audio/x-raw", start)
    local arate = string.format("speed speed=%f", speed)

    local vwait = string.format("avwait mode=timecode target-timecode-string=\"%s:00\" ! video/x-raw", start)
    local vrate = string.format("videorate rate=%f ! video/x-raw,framerate=%d/1", speed, fps)
    local vscale = string.format("videoscale ! video/x-raw,width=%d,height=%d", width, height)

    local line

    -- audio-only
    if false then
        line = string.format([[
            %s filesrc location=%s ! %s name=demux \
            demux.audio_0 ! decodebin ! audioconvert ! %s ! avenc_aac ! mpegtsmux name=mux \
            mux. ! %s \
            ]],
            gst_launch(opts), src, demux,
            arate,
            sink);
        return line
    end

    -- video-only
    if false then
        line = string.format([[
            %s filesrc location=%s ! %s name=demux \
            demux.video_0 ! decodebin ! %s ! %s ! %s ! mpegtsmux name=mux \
            mux. ! %s]],
            gst_launch(opts), src, demux,
            vrate, vscale, vcodec,
            sink);
        return line
    end

    -- audio and video
    if true then
        arate = string.format("queue ! %s", arate)
        vrate = string.format("queue ! %s", vrate)
        line = string.format([[
            %s filesrc location=%s ! %s name=demux \
            demux.audio_0 ! decodebin ! audioconvert ! %s ! avenc_aac ! mpegtsmux name=mux \
            demux.video_0 ! decodebin ! %s ! %s ! %s ! mux. \
            mux. ! %s]],
            gst_launch(opts), src, demux,
            arate,
            vrate, vscale, vcodec,
            sink);
        return line
    end

    -- copy
    line = string.format([[
        %s filesrc location=%s ! %s name=demux \
         demux.audio_0 ! queue ! mpegtsmux name=mux \
         demux.video_0 ! queue ! mux. \
         mux. ! %s]],
        gst_launch(opts), src, demux,
        sink);
    return line;
end


function test_gst()
    local fname = "/Users/peter/Downloads/samples/sample-h264.mp4"
    start = "00:00:00"
    speed = 1.0
    width = 1280/2
    height = 720/2
    fps = 25
    bps = 500*1000

    local cmd
    if true then
        cmd = gst_transcode(fname, start, speed, width, height, fps, bps, "/tmp/out.ts")
    else
        cmd = gst_transcode(fname, start, speed, width, height, fps, bps, 1)
        cmd = string.format("%s >/tmp/out_fd.ts", cmd)
    end

    print(cmd)
    local begintm = os.time();
    os.execute(cmd)
    local endtm = os.time();
    print(os.difftime(endtm, begintm))
end

test_gst()
