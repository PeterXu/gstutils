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
function gst_media_info(caps, props)
    local info
    if caps then
        if findistr(caps, "/quicktime") or
           findistr(caps, "/x-3gp") or
           findistr(caps, "/x-mj2") or
           findistr(caps, "/x-m4a") then
            info = {demux = "qtdemux"}
        elseif findistr(caps, "/x-matroska") or findistr(caps, "/webm") then
            info = {demux = "matroskademux"}
        elseif findistr(caps, "/mpegts") then
            info = {demux = "tsdemux"}
        elseif findistr(caps, "/mpeg") or findistr(caps, "/x-cdxa") then
            info = {demux = "mpegpsdemux"}
        elseif findistr(caps, "/x-msvideo") then
            info = {demux = "avidemux"}
        elseif findistr(caps, "/ogg") or findistr(caps, "/kate") then
            info = {demux = "oggdemux"}
        elseif findistr(caps, "/x-flv") then
            info = {demux = "flvdemux"}
        end
        if info then
            info.caps = caps
        end
    end
    return info
end

-- check audio codec format's info
function gst_audio_info(caps, props)
    local info
    if caps then
        if findistr(caps, "audio/mpeg") then
            if findistr(props, "mpegversion=(int)1")
               and findistr(props, "mpegaudioversion=(int)1") then
                if findistr(props, "layer=(int)2") then
                    info = {parse = "mpegaudioparse", dec = "avdec_mp2float"}
                elseif findistr(props, "layer=(int)3") then
                    info = {parse = "mpegaudioparse", dec = "avdec_mp3"}
                end
            elseif findistr(props, "mpegversion=(int)4") then
                info = {parse = "aacparse", dec = "avdec_aac"}
            end
        elseif findistr(caps, "audio/x-vorbis") then
            info = {parse = "vorbisparse", dec = "vorbisdec"}
        elseif findistr(caps, "audio/x-opus") then
            info = {parse = "opusparse", dec = "avdec_opus"}
        elseif findistr(caps, "audio/x-flac") then
            info = {parse = "flacparse", dec = "avdec_flac"}
        elseif findistr(caps, "audio/AMR-WB") then
            info = {parse = nil, dec = "avdec_amrwb"} -- 16000
        elseif findistr(caps, "audio/AMR") then
            info = {parse = nil, dec = "avdec_amrnb"} -- 8000
        end
        if info then
            info.caps = caps
        end
    end
    return info
end

-- check video codec format's info
function gst_video_info(caps, props)
    local info
    if caps then
        if findistr(caps, "video/x-h264") then
            info = {parse = "h264parse", dec = "avdec_h264"}
        elseif findistr(caps, "video/x-h265") then
            info = {parse = "h265parse", dec = "avdec_h265"}
        elseif findistr(caps, "video/mpeg") then
            if findistr(props, "mpegversion=(int)1") then
                info = {parse = "mpegvideoparse", dec = "avdec_mpegvideo"}
            elseif findistr(props, "mpegversion=(int)2") then
                info = {parse = "mpegvideoparse", dec = "avdec_mpeg2video"}
            elseif findistr(props, "mpegversion=(int)4") then
                info = {parse = "mpeg4videoparse", dec = "avdec_mpeg4"}
            end
        elseif findistr(caps, "video/x-theora") then
            info = {parse = "theoraparse", dec = "theoradec"}
        elseif findistr(caps, "video/x-h263") then
            info = {parse = "h263parse", dec = nil} -- auto dec
        elseif findistr(caps, "video/x-vp8") then
            info = {parse = nil, dec = "vp8dec"} -- no parse
        elseif findistr(caps, "video/x-vp9") then
            info = {parse = nil, dec = "vp9dec"} -- no parse
        elseif findistr(caps, "video/x-flash-video") then
            info = {parse = nil, dec = "avdec_flv"} -- no parse
        end
        if info then
            info.caps = caps
            info.dec = gst_inspect_video_dec(info.caps, info.dec)
        end
    end
    return info
end

-- discover media file's info
function gst_discover(src)
    local minfo, ainfo, vinfo
    local line = string.format("gst-discoverer-1.0 -v %s", src)
    local fp = io.popen(line)
    for info in fp:lines() do
        local ret, props 
        ret, props = string.match(info, "container: ([%w%-%/]+)[%,]*(.*)")
        if ret then minfo = gst_media_info(ret, props) end

        ret, props = string.match(info, "audio: ([%w%-%/]+)[%,]*(.*)")
        if ret then ainfo = gst_audio_info(ret, props) end

        ret, props = string.match(info, "video: ([%w%-%/]+)[%,]*(.*)")
        if ret then vinfo = gst_video_info(ret, props) end
    end
    --print(table2json(minfo), table2json(ainfo), table2json(vinfo))
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

function test_discover(flist)
    for _, item in pairs(flist) do
        local d,a,v = gst_discover(item)
        print(">Media: " .. item, table2json(d, true))
        print(">Audio:" .. item, table2json(a, true))
        print(">Video:" .. item, table2json(v, true))
        print()
    end
end


function test_files()
    local path = script_path()
    local items = {
        f01 = "/tmp/samples/sample-h265.mkv",
        f02 = "/tmp/samples/sample-mpeg4.mkv",
        f03 = "/tmp/samples/sample-h264.mp4",

        f05 = path .. "/samples/small.ogg",
        f06 = path .. "/samples/small.m4a",

        f11 = path .. "/samples/small.mp4",
        f12 = path .. "/samples/small.3gp",
        f13 = path .. "/samples/small.webm",
        f14 = path .. "/samples/small.ogm",
        f15 = path .. "/samples/small.flv",
        f16 = path .. "/samples/small.mpg",
        f17 = path .. "/samples/small.avi",
        f18 = path .. "/samples/small.mkv",
    }
    
    local dinfo = true
    if dinfo then
        test_discover({items.f05, items.f06}) 
        test_discover({items.f11, items.f12, items.f13, items.f14, items.f15}) 
        test_discover({items.f16, items.f17, items.f18}) 
    else
        local fin = items.f17
        local fout = "/tmp/out_media.ts"
        test_gst(fin, fout)
    end
end


test_files()
