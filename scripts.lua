function tprint (tbl)
    local jstr = "{\n"
    if tbl then 
        for k, v in pairs(tbl) do
            if type(v) == "table" then
                jstr = jstr .. string.format("    %s: ...,\n", tostring(k))
            else
                jstr = jstr .. string.format("    %s: %s,\n", tostring(k), tostring(v))
            end
        end
    end
    jstr = jstr .. "}\n"
    return jstr
end

function gst_which(shcmd)
    return os.execute(string.format("which %s >/dev/null", shcmd))
end

function gst_launch(opts)
    return string.format("gst-launch-1.0 %s", opts)
end

function gst_inspect(plugin)
    return os.execute(string.format("gst-inspect-1.0 --exists %s", plugin))
end

function gst_inspect_video_dec(caps, default)
    local mpp_caps = [[video/x-vp8;video/x-vp9;video/x-h264;video/x-h265;video/mpeg,mpegversion=]]
    if string.find(mpp_caps, caps, 1, true) then
        if gst_inspect("mppvideodec") then
            return "mppvideodec"
        end
    end
    return default
end

function gst_inspect_video_enc(bps) 
    -- only use h264
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
        if string.find(format, "/quicktime", 1, true) then
            demux = "qtdemux"
        elseif string.find(format, "/x-matroska", 1, true) then
            demux = "matroskademux"
        elseif string.find(format, "/mpegts", 1, true) then
            demux = "tsdemux"
        elseif string.find(format, "/ogg", 1, true) then
            demux = "oggdemux"
        elseif string.find(format, "/x-flv", 1, true) then
            demux = "flvdemux"
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
    elseif string.find(format, "mpeg-2 transport stream", 1, true) then 
        demux = "tsdemux"
    elseif string.find(format, "ogg") then
        demux = "oggdemux"
    elseif string.find(format, "flv") then
        demux = "flvdemux"
    end
    return demux
end

function gst_audio_info(media)
    local info
    local format = string.lower(media)
    if string.find(format, "aac") then
        info = {caps = "audio/mpeg", parse = "aacparse", dec = "avdec_aac"}
    elseif string.find(format, "mp3") then
        info = {caps = "audio/mpeg", parse = "mpegaudioparse", dec = "avdec_mp3"}
    elseif string.find(format, "vorbis") then
        info = {caps = "audio/x-vorbis", parse = "vorbisparse", dec = "vorbisdec"}
    elseif string.find(format, "opus") then
        info = {caps = "audio/x-opus", parse = "opusparse", dec = "avdec_opus"}
    elseif string.find(format, "amr") then
        info = {caps = nil, parse = "amrparse", dec = nil} --auto: amrnb/amrwb
    end
    return info
end

function gst_video_info(media)
    local info
    local format = string.lower(media)
    if string.find(format, "h.264") then
        info = {caps = "video/x-h264", parse = "h264parse", dec = "avdec_h264"}
    elseif string.find(format, "h.265") then
        info = {caps = "video/x-h265", parse = "h265parse", dec = "avdec_h265"}
    elseif string.find(format, "mpeg.4 video") then
        info = {caps = "video/mpeg,mpegversion=4", parse = "mpeg4videoparse", dec = "avdec_mpeg4"}
    elseif string.find(format, "theora") then
        info = {caps = "video/x-theora", parse = "theoraparse", dec = "theoradec"}
    elseif string.find(format, "h.26n") then
        info = {caps = "video/x-h263", parse = "h263parse", dec = nil} -- auto
    elseif string.find(format, "vp8") then
        info = {caps = "video/x-vp8", parse = nil, dec = "vp8dec"} -- no pb
    elseif string.find(format, "vp9") then
        info = {caps = "video/x-vp9", parse = nil, dec = "vp9dec"} -- no pb
    end
    if info then
        info.dec = gst_inspect_video_dec(info.caps, info.dec)
    end
    return info
end

function gst_discover(src)
    local line = string.format("gst-discoverer-1.0 %s", src)
    local fp = io.popen(line)
    local demux, ainfo, vinfo
    for info in fp:lines() do
        ret = string.match(info, "container: (.+)")
        if ret then 
            demux = gst_format_demux(ret)
        else
            ret = string.match(info, "audio: (.+)")
            if ret then
                ainfo = gst_audio_info(ret)
            else
                ret = string.match(info, "video: (.+)")
                if ret then
                    vinfo = gst_video_info(ret)
                end
            end
        end
    end
    return demux, ainfo, vinfo
end

function gst_transcode(src, copy, start, speed, width, height, fps, bps, outf)
    local TAG = ">"

    -- check media info(audio/video)
    local demux, ainfo, vinfo = gst_discover(src)
    print (TAG .. "demux:", demux)
    print (TAG .. "audio:", tprint(ainfo))
    print (TAG .. "video:", tprint(vinfo))
    if demux == nil or (ainfo == nil and vinfo == nil) then
        return nil
    else
        --return nil
    end

    -- should have one of parse/dec
    if ainfo and (not ainfo.parse) and (not ainfo.dec) then
        return nil
    end

    -- should have one of parse/dec
    if vinfo and (not vinfo.parse) and (not vinfo.dec) then
        return nil
    end

    local aparse, vparse, adec, vdec

    -- get audio parse/dec
    if ainfo then
        aparse = ainfo.parse
        if ainfo.dec then
            adec = string.format("queue ! %s ! queue", ainfo.dec)
        else
            adec = string.format("queue ! %s ! queue ! decodebin", ainfo.parse) -- auto
        end
    end

    -- get video parse/dec
    if vinfo then
        vparse = vinfo.parse
        if vinfo.dec then
            vdec = string.format("queue ! %s ! queue", vinfo.dec)
        else
            vdec = string.format("queue ! %s ! queue ! decodebin", vinfo.parse) -- auto
        end
    end

    -- check video enc
    local venc = gst_inspect_video_enc(bps)
    print (TAG .. "video-enc:", venc, "\n")
    if venc == nil then
        return nil
    end

    -- gst-launch options
    local opts = ""

    -- check output sink
    local outsink
    local dst = tonumber(outf)
    if dst == nil then
        outsink = string.format("filesink location=%s", outf)
    else
        outsink = string.format("fdsink fd=%d", dst)
        if dst == 1 then
            opts = "-q"
        end
    end

    -- gst-launch command line
    local line
    local outmux = "mpegtsmux"
    local filesrc = string.format([[%s filesrc location="%s"]], gst_launch(opts), src)

    local start_tc = string.format("%s:00", start)
    local arate = string.format("speed speed=%f", speed)
    local vrate = string.format("videorate rate=%f ! video/x-raw,framerate=%d/1", speed, fps)
    local vscale = string.format("videoscale ! video/x-raw,width=%d,height=%d", width, height)

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
                outsink);
        elseif aparse or vparse then
            local tmp_parse = aparse
            if vparse then tmp_parse = vparse end
            line = string.format([[%s ! parsebin name=pb \
                pb. ! %s ! queue ! %s name=mux \
                mux. ! %s]],
                filesrc,
                tmp_parse, outmux,
                outsink);
        else
            print(TAG .. "unsupported: need parse!")
        end
        return line
    end

    -- audio-only
    if false or (adec and not vdec) then
        -- unsupport start-tc
        line = string.format([[%s ! parsebin name=pb \
            pb. ! %s ! audioconvert ! audio/x-raw ! %s \
                ! avenc_aac ! queue ! %s name=mux \
            mux. ! %s ]],
            filesrc,
            adec, arate, outmux,
            outsink);
        return line
    end

    -- video-only
    if false or (not adec and vdec) then
        -- support start-tc.
        line = string.format([[%s ! parsebin name=pb \
            pb. ! %s ! videoconvert ! video/x-raw \
                ! %s ! timecodestamper ! avwait name=wait target-timecode-string="%s" \
                ! %s \
                ! %s ! %s name=mux \
            mux. ! %s]],
            filesrc,
            vdec, vrate, start_tc, vscale, venc, outmux,
            outsink);
        return line
    end

    -- audio and video
    -- support start-tc
    line = string.format([[%s ! parsebin name=pb \
        pb. ! %s ! audioconvert ! queue ! audio/x-raw ! %s \
            ! avwait name=wait target-timecode-string="%s" \
            ! avenc_aac ! queue ! %s name=mux \
        pb. ! %s ! videoconvert ! queue ! video/x-raw ! %s \
            ! timecodestamper ! wait. \
            wait. ! queue ! %s  \
            ! %s ! queue ! mux. \
        mux. ! %s]],
        filesrc,
        adec, arate, start_tc, outmux,
        vdec, vrate, vscale, venc,
        outsink);
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

--test_gst("/tmp/samples/sample-h265.mp4", "/tmp/out2_mp4.ts")
--test_gst("/tmp/samples/sample-mpeg4.mkv", "/tmp/out_mkv.ts")
--test_gst("/tmp/samples/sample-h264.mp4", "/tmp/out_mp4.ts")
--test_gst("/tmp/samples/small.3gp", "/tmp/out_3gp.ts")
--test_gst("/tmp/out_mp4.ts", "/tmp/out_ts.ts")
--test_typefind()
