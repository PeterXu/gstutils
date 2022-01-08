--
-- base tools
--

function ifone(a, b, c)
    if a then return b else return c end
end

function table2json(tbl, short)
    local newline = ifone(short, "", "\n")
    local jstr = "{" .. newline
    if type(tbl) == "table" then 
        for k, v in pairs(tbl) do
            local val = ifone(type(v) == "table", "...", tostring(v))
            jstr = jstr .. string.format("  %s: %s,", tostring(k), val) .. newline
        end
    end
    jstr = jstr .. "}" .. newline
    return jstr
end

function findstr(str, pat, nocase)
    if nocase then
        return string.find(string.lower(str), string.lower(pat), 1, true)
    else
        return string.find(str, pat, 1, true)
    end
end

-- ignore case
function findistr(str, pat)
    return findstr(str, pat, true)
end

-- get path of currrent executing script 
function script_path()
  local str = debug.getinfo(2, "S").source:sub(2)
  return str:match("(.*[/\\])") or "."
end

function sh_which(cmd)
    return os.execute(string.format("which %s >/dev/null", cmd))
end

--
-- gst process
-- 

function gst_launch(opts)
    return string.format("gst-launch-1.0 %s", opts)
end

function gst_inspect(plugin)
    return os.execute(string.format("gst-inspect-1.0 --exists %s", plugin))
end

-- check video HW/SW decoder
function gst_inspect_video_dec(caps, default)
    local mpp_caps = [[video/x-vp8;video/x-vp9;video/x-h264;video/x-h265;video/mpeg,mpegversion=]]
    if findistr(mpp_caps, caps) then
        if gst_inspect("mppvideodec") then
            return "mppvideodec"
        end
    end
    return default
end

-- check video HW/SW encoder(only use h264)
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

-- check media file's info
function gst_media_info(src)
    local info
    local fp = io.popen(string.format("gst-typefind-1.0 %s", src))
    local result = fp:read()
    if result then
        local kind, format = string.match(result, ".*% %-% (%w+)%/([%w%-]+)")
        local caps = kind .. "/" .. format
        if findistr(caps, "/quicktime") or
           findistr(caps, "/x-3gp") or
           findistr(caps, "/x-mj2") or
           findistr(caps, "/x-m4a") then
            info = {caps = caps, demux = "qtdemux"}
        elseif findistr(caps, "/x-matroska") or findistr(caps, "/webm") then
            info = {caps = caps, demux = "matroskademux"}
        elseif findistr(caps, "/mpegts") then
            info = {caps = caps, demux = "tsdemux"}
        elseif findistr(caps, "/mpeg") or findistr(caps, "/x-cdxa") then
            info = {caps = caps, demux = "mpegpsdemux"}
        elseif findistr(caps, "/x-msvideo") then
            info = {caps = caps, demux = "avidemux"}
        elseif findistr(caps, "/ogg") or findistr(caps, "/kate") then
            info = {caps = caps, demux = "oggdemux"}
        elseif findistr(caps, "/x-flv") then
            info = {caps = caps, demux = "flvdemux"}
        end
    end
    return info
end

-- check audio codec format's info
function gst_audio_info(format, sampleRate)
    local info
    if findistr(format, "MPEG-4 AAC") then
        info = {caps = "audio/mpeg", parse = "aacparse", dec = "avdec_aac"}
    elseif findistr(format, "MP2") or findistr(format, "MPEG-1 Layer 2") then
        info = {caps = "audio/mpeg", parse = "mpegaudioparse", dec = "avdec_mp2float"}
    elseif findistr(format, "MP3") or findistr(format, "MPEG-1 Layer 3") then
        info = {caps = "audio/mpeg", parse = "mpegaudioparse", dec = "avdec_mp3"}
    elseif findistr(format, "Vorbis") then
        info = {caps = "audio/x-vorbis", parse = "vorbisparse", dec = "vorbisdec"}
    elseif findistr(format, "Opus") then
        info = {caps = "audio/x-opus", parse = "opusparse", dec = "avdec_opus"}
    elseif findistr(format, "FLAC") then
        info = {caps = "audio/x-flac", parse = "flacparse", dec = "avdec_flac"}
    elseif findistr(format, "AMR") then
        -- amrparse does not work
        if sampleRate == 8000 then
            info = {caps = "audio/AMR", parse = nil, dec = "avdec_amrnb"} -- 8000
        else
            info = {caps = "audio/AMR-WB", parse = nil, dec = "avdec_amrwb"} -- 16000
        end
    end
    return info
end

-- check video codec format's info
function gst_video_info(format)
    local info
    if findistr(format, "H.264") then
        info = {caps = "video/x-h264", parse = "h264parse", dec = "avdec_h264"}
    elseif findistr(format, "H.265") then
        info = {caps = "video/x-h265", parse = "h265parse", dec = "avdec_h265"}
    elseif findistr(format, "MPEG-1 Video") then
        info = {caps = "video/mpeg,mpegversion=1", parse = "mpegvideoparse", dec = "avdec_mpegvideo"}
    elseif findistr(format, "MPEG-2 Video") then
        info = {caps = "video/mpeg,mpegversion=2", parse = "mpegvideoparse", dec = "avdec_mpeg2video"}
    elseif findistr(format, "MPEG-4 Video") then
        info = {caps = "video/mpeg,mpegversion=4", parse = "mpeg4videoparse", dec = "avdec_mpeg4"}
    elseif findistr(format, "Theora") then
        info = {caps = "video/x-theora", parse = "theoraparse", dec = "theoradec"}
    elseif findistr(format, "ITU H.26n") then
        info = {caps = "video/x-h263", parse = "h263parse", dec = nil} -- auto
    elseif findistr(format, "VP8") then
        info = {caps = "video/x-vp8", parse = nil, dec = "vp8dec"} -- no pb
    elseif findistr(format, "VP9") then
        info = {caps = "video/x-vp9", parse = nil, dec = "vp9dec"} -- no pb
    elseif findistr(format, "Sorenson Spark Video") then
        info = {caps = "video/x-flash-video", parse = nil, dec = "avdec_flv"}
    end
    if info then
        info.dec = gst_inspect_video_dec(info.caps, info.dec)
    end
    return info
end

-- discover media file's info
function gst_discover(src)
    local container, audio, sampleRate, video
    local line = string.format("gst-discoverer-1.0 %s", src)
    local fp = io.popen(line)
    for info in fp:lines() do
        local ret
        ret = string.match(info, "container: (.+)")
        if ret then container = ret end
        ret = string.match(info, "audio: (.+)")
        if ret then audio = ret end
        ret = string.match(info, "Sample rate: (.+)")
        if ret then sampleRate = ret end
        ret = string.match(info, "video: (.+)")
        if ret then video = ret end
    end
    local minfo = gst_media_info(src)
    if minfo then minfo.name = container end
    local ainfo = gst_audio_info(audio, tonumber(sampleRate))
    local vinfo = gst_video_info(video)
    return minfo, ainfo, vinfo
end

-- transcode routine
function gst_transcode(src, copy, start, speed, width, height, fps, bps, outf)
    local TAG = ">"

    -- check media info(audio/video)
    local minfo, ainfo, vinfo = gst_discover(src)
    print (TAG .. "media:", table2json(minfo))
    print (TAG .. "audio:", table2json(ainfo))
    print (TAG .. "video:", table2json(vinfo))
    if minfo == nil or (ainfo == nil and vinfo == nil) then
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

    local demux = minfo.demux
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
            local tmp_parse = ifone(aparse, aparse, vparse)
            line = string.format([[%s ! parsebin name=pb \
                pb. ! %s ! queue ! %s name=mux \
                mux. ! %s]],
                filesrc,
                tmp_parse, outmux,
                outsink);
        else
            print(TAG .. "unsupported: need codec-parse!")
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

--
-- testing cases
--

function test_gst(fname, outf, stdout)
    start = "00:00:00"
    speed = 1.0
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

function test_typefind(flist)
    for _, item in pairs(flist) do
        print(item, gst_media_info(item))
    end
end

function test_discover(flist)
    for _, item in pairs(flist) do
        local d,a,v = gst_discover(item)
        print(item, d, table2json(a, true))
    end
end


function test_files()
    local path = script_path()
    local items = {
        f01 = "/tmp/samples/sample-h265.mkv",
        f02 = "/tmp/samples/sample-mpeg4.mkv",
        f03 = "/tmp/samples/sample-h264.mp4",

        f11 = path .. "/samples/small.mp4",
        f12 = path .. "/samples/small.3gp",
        f13 = path .. "/samples/small.webm",
        f14 = path .. "/samples/small.ogm",
        f15 = path .. "/samples/small.flv",
        f16 = path .. "/samples/small.mpg",
        f17 = path .. "/samples/small.avi",
    }
    --test_typefind({items.f11, items.f12, items.f13, items.f14, items.f15})
    --test_discover({items.f11, items.f12, items.f13, items.f14, items.f15})

    local fin = items.f17
    local fout = "/tmp/out_media.ts"
    test_gst(fin, fout)
end


test_files()
