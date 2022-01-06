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
    return demux
end

function gst_format_demux(container)
    local demux
    if container == "Quicktime" then
        demux = "qtdemux"
    elseif container == "Matroska" then
        demux = "matroskademux"
    end
    return demux
end

function gst_format_parse(media)
    local parse
    local format = string.upper(media)
    if string.find(format, "AAC") then
        parse = "aacparse"
    elseif string.find(format, "MP3") then
        parse = "mpegaudioparse"
    elseif string.find(format, "OGM") then
        parse = "ogmaudioparse"
    elseif string.find(format, "OPUS") then
        parse = "opusparse"
    elseif string.find(format, "H.264") then
        parse = "h264parse"
    elseif string.find(format, "H.265") then
        parse = "h265parse"
    elseif string.find(format, "MPEG.4") then
        parse = "mpeg4videoparse"
    end
    return parse
end

function gst_discover(src)
    local line = string.format("gst-discoverer-1.0 %s", src)
    local fp = io.popen(line)
    local demux, aparse, vparse
    for info in fp:lines() do
        ret = string.match(info, "container: (.+)")
        if ret then 
            demux = gst_format_demux(ret)
        else
            ret = string.match(info, "audio: (.+)")
            if ret then
                aparse = gst_format_parse(ret)
            else
                ret = string.match(info, "video: (.+)")
                if ret then
                    vparse = gst_format_parse(ret)
                end
            end
        end
    end
    return demux, aparse, vparse
end

function gst_transcode(src, copy, start, speed, width, height, fps, bps, outf)
    -- check source format(audio/video)
    local demux, aparse, vparse = gst_discover(src)
    print ("demux:", demux, "audio:", aparse, "video:", vparse)
    if demux == nil or (aparse == nil and vparse == nil) then
        return nil
    end

    -- check output video codec
    local vcodec = gst_inspect_vcodec(bps)
    if vcodec == nil then
        return nil
    end

    -- gst-launch options
    local opts = ""

    -- check output sink
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

    -- gst-launch command line
    local line
    local outmux = "mpegtsmux"

    -- copy audio/video
    if false or copy then
        if demux == "matroskademux" then outmux = "matroskamux" end
        if false or (aparse and vparse) then
            line = string.format([[
                %s filesrc location=%s ! %s name=demux \
                demux.audio_0 ! queue ! %s ! %s name=mux \
                demux.video_0 ! queue ! %s ! mux. \
                mux. ! queue ! %s]],
                gst_launch(opts), src, demux,
                aparse, outmux,
                vparse,
                sink);
        else
            local tmp_parse = aparse
            if vparse then tmp_parse = vparse end
            line = string.format([[
                %s filesrc location=%s ! parsebin name=pb \
                pb. ! %s ! queue ! %s name=mux \
                mux. ! %s]],
                gst_launch(opts), src, 
                tmp_parse, outmux,
                sink);
        end
        return line
    end

    -- audio-only
    if false or (aparse and not vparse) then
        line = string.format([[
            %s filesrc location=%s ! parsebin name=pb \
            pb. ! %s ! decodebin ! audioconvert ! %s ! avenc_aac ! %s name=mux \
            mux. ! %s \
            ]],
            gst_launch(opts), src,
            aparse, arate, outmux,
            sink);
        return line
    end

    -- video-only
    if false or (not aparse and vparse) then
        line = string.format([[
            %s filesrc location=%s ! parsebin name=pb \
            pb. ! %s ! decodebin ! %s ! %s ! videoconvert ! %s ! %s name=mux \
            mux. ! %s]],
            gst_launch(opts), src,
            vparse, vrate, vscale, vcodec, outmux,
            sink);
        return line
    end

    -- audio and video
    arate = string.format("queue ! %s", arate)
    vrate = string.format("queue ! %s", vrate)
    line = string.format([[
        %s filesrc location=%s ! parsebin name=pb \
        pb. ! queue ! %s ! queue ! decodebin ! audioconvert ! %s ! avenc_aac ! queue ! %s name=mux \
        pb. ! queue ! %s ! queue ! decodebin ! %s ! %s ! videoconvert ! %s ! queue ! mux. \
        mux. ! %s]],
        gst_launch(opts), src,
        aparse, arate, outmux,
        vparse, vrate, vscale, vcodec,
        sink);
    return line
end


function test_gst(fname, outf, stdout)
    start = "00:00:00"
    speed = 1.0
    width = 1280/2
    height = 720/2
    fps = 25
    bps = 500*1000
    copy = false

    local cmd
    if stdout then
        cmd = gst_transcode(fname, copy, start, speed, width, height, fps, bps, 1)
        cmd = string.format("%s >%s", cmd, outf)
    else
        cmd = gst_transcode(fname, copy, start, speed, width, height, fps, bps, outf)
    end

    print("============", fname, "===========")
    print(cmd)
    local begintm = os.time();
    os.execute(cmd)
    local endtm = os.time();
    print(os.difftime(endtm, begintm))
end

--test_gst("/Users/peter/Downloads/samples/sample-h264.mp4", "/tmp/out_mp4.ts")
test_gst("/Users/peter/Downloads/samples/sample-mpeg4.mkv", "/tmp/out_mkv.ts")

