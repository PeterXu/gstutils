function gst_which(shcmd)
    return os.execute(string.format("which %s >/dev/null", shcmd))
end

function gst_launch(opts)
    return string.format("gst-launch-1.0 %s", opts)
end

function gst_inspect(plugin)
    return os.execute(string.format("gst-inspect-1.0 --exists %s", plugin))
end

function gst_inspect_video_enc(bps) 
    local codec
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
    local demux
    local fp = io.popen(string.format("gst-typefind-1.0 %s", src))
    local result = fp:read()
    if result then
        local format = string.lower(result)
        if string.find(format, "quicktime") then
            demux = "qtdemux"
        elseif string.find(format, "matroska") then
            demux = "matroskademux"
        elseif string.find(format, "mpegts") then
            demux = "tsdemux"
        elseif string.find(format, "ogg") then
            demux = "oggdemux"
        end
    end
    return demux
end

function gst_format_demux(container)
    local demux
    local format = string.lower(container)
    if string.find(format, "quicktime") or string.find(format, "3gp") then
        demux = "qtdemux"
    elseif string.find(format, "matroska") or string.find(format, "webm") then
        demux = "matroskademux"
    elseif string.find(format, "mpeg.2 transport stream") then 
        demux = "tsdemux"
    elseif string.find(format, "ogg") then
        demux = "oggdemux"
    end
    return demux
end

function gst_audio_parse(media)
    local parse
    local format = string.lower(media)
    if string.find(format, "aac") then
        parse = "aacparse"
    elseif string.find(format, "mp3") then
        parse = "mpegaudioparse"
    elseif string.find(format, "vorbis") then
        parse = "vorbisparse"
    elseif string.find(format, "opus") then
        parse = "opusparse"
    elseif string.find(format, "amr") then
        parse = "amrparse"
    return parse

function gst_video_parse(media)
    local parse
    local format = string.lower(media)
    if string.find(format, "h.264") then
        parse = "h264parse"
    elseif string.find(format, "h.265") then
        parse = "h265parse"
    elseif string.find(format, "mpeg.4 video") then
        parse = "mpeg4videoparse"
    elseif string.find(format, "theora") then
        parse = "theoraparse"
    elseif string.find(format, "H.26n") then
        parse = "h263parse"
    elseif string.find(format, "vp8") then
        parse = nil
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
                aparse = gst_audio_parse(ret)
            else
                ret = string.match(info, "video: (.+)")
                if ret then
                    vparse = gst_video_parse(ret)
                end
            end
        end
    end
    return demux, aparse, vparse
end

function gst_transcode(src, copy, start, speed, width, height, fps, bps, outf)
    -- check source format(audio/video)
    local TAG = ">"
    local demux, aparse, vparse = gst_discover(src)
    print (TAG, "demux:", demux, "audio:", aparse, "video:", vparse)
    if demux == nil or (aparse == nil and vparse == nil) then
        return nil
    end

    -- check video encode
    local venc = gst_inspect_video_enc(bps)
    print (TAG, "video encode:", venc)
    if venc == nil then
        return nil
    end

    -- gst-launch options
    local opts = ""

    -- check output sink
    local filesink
    local dst = tonumber(outf)
    if dst == nil then
        filesink = string.format("filesink location=%s", outf)
    else
        filesink = string.format("fdsink fd=%d", dst)
        if dst == 1 then
            opts = "-q"
        end
    end

    local start_tc = string.format([[%s:00]], start)
    local arate = string.format("speed speed=%f", speed)
    local vrate = string.format("videorate rate=%f ! video/x-raw,framerate=%d/1", speed, fps)
    local vscale = string.format("videoscale ! video/x-raw,width=%d,height=%d", width, height)

    -- gst-launch command line
    local line
    local outmux = "mpegtsmux"
    local filesrc = string.format([[%s filesrc location="%s"]], gst_launch(opts), src)

    -- copy audio/video
    if false or copy then
        if demux == "matroskademux" then outmux = "matroskamux" end
        if false or (aparse and vparse) then
            line = string.format([[%s ! %s name=demux \
                demux.audio_0 ! queue ! %s ! %s name=mux \
                demux.video_0 ! queue ! %s ! mux. \
                mux. ! queue ! %s]],
                filesrc, demux,
                aparse, outmux, vparse,
                filesink);
        else
            local tmp_parse = aparse
            if vparse then tmp_parse = vparse end
            line = string.format([[%s ! parsebin name=pb \
                pb. ! %s ! queue ! %s name=mux \
                mux. ! %s]],
                filesrc,
                tmp_parse, outmux,
                filesink);
        end
        return line
    end

    -- audio-only
    if false or (aparse and not vparse) then
        -- unsupport start-tc
        line = string.format([[%s ! parsebin name=pb \
            pb. ! queue ! %s ! queue ! decodebin ! audioconvert ! audio/x-raw ! %s \
                ! avenc_aac ! queue ! %s name=mux \
            mux. ! %s ]],
            filesrc,
            aparse, arate, outmux,
            filesink);
        return line
    end

    -- video-only
    if false or (not aparse and vparse) then
        -- support start-tc.
        line = string.format([[%s ! parsebin name=pb \
            pb. ! %s ! decodebin ! videoconvert ! video/x-raw \
                ! %s ! timecodestamper ! avwait name=wait target-timecode-string="%s" \
                ! %s \
                ! %s ! %s name=mux \
            mux. ! %s]],
            filesrc,
            vparse, vrate, start_tc, vscale, venc, outmux,
            filesink);
        return line
    end

    -- audio and video
    -- support start-tc
    aparse = string.format("queue ! %s ! queue", aparse)
    vparse = string.format("queue ! %s ! queue", vparse)
    line = string.format([[%s ! parsebin name=pb \
        pb. ! %s ! decodebin ! audioconvert ! queue ! audio/x-raw ! %s \
            ! avwait name=wait target-timecode-string="%s" \
            ! avenc_aac ! queue ! %s name=mux \
        pb. ! %s ! decodebin ! videoconvert ! queue ! video/x-raw ! %s \
            ! timecodestamper ! wait. \
            wait. ! queue ! %s  \
            ! %s ! queue ! mux. \
        mux. ! %s]],
        filesrc,
        aparse, arate, start_tc, outmux,
        vparse, vrate, vscale, venc,
        filesink);
    return line
end


function test_gst(fname, outf, stdout)
    start = "00:00:10"
    speed = 1.5
    width = 1280/2
    height = 720/2
    fps = 15
    bps = 600*1000
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

function test_typefind()
    print(gst_typefind_demux("/tmp/sample-mpeg4.mkv"))
    print(gst_typefind_demux("/tmp/sample-h264.mp4"))
    print(gst_typefind_demux("/tmp/out_mp4.ts"))
end

--test_gst("/tmp/sample-h265.mp4", "/tmp/out2_mp4.ts")
--test_gst("/tmp/sample-mpeg4.mkv", "/tmp/out_mkv.ts")
--test_gst("/tmp/sample-h264.mp4", "/tmp/out_mp4.ts")
--test_gst("/tmp/out_mp4.ts", "/tmp/out_ts.ts")
--test_typefind()
