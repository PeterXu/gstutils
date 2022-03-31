--
-- base tools
--

function shexecute(cmd)
    return os.execute(cmd)
end

function sh_which(cmd)
    return shexecute(string.format("which %s >/dev/null", cmd))
end

function ifone(a, b, c)
    if a then return b else return c end
end

function ifelse(a, b)
    if a then return a else return b end
end

function ifclip(v, min, max, default)
    if not v then return default end
    if v < min then return min end
    if v > max then return max end
    return v
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
  print(str);
  return str:match("(.*[/\\])") or "."
end

function parse_path(path)
    local dir, name, ext
    dir = path:match("(.*)[/\\]")
    ext = path:match(".*%.(.*)")
    if dir and ext then
        name = path:match(".*[/\\](.*)%..*")
    elseif dir then
        name = path:match(".*[/\\](.*)")
    elseif ext then
        name = path:match("(.*)%..*")
    else
        name = path
    end
    if not dir or #dir == 0 then dir = "." end
    if not name or #name == 0 then name = nil end
    if not ext or #ext == 0 then ext = nil end
    --print (">", path, dir, name, ext)
    return dir, name, ext
end


--
-- gst tools, supported env: GST_OPTIONS/GST_VIDEO_DEC_DELAY/GST_VIDEO_ENC_DELAY
--

function gst_launch(opts)
    if type(opts) ~= "string" then opts = "" end
    local eopts = ifelse(os.getenv("GST_OPTIONS"), "")
    return string.format("gst-launch-1.0 %s %s", eopts, opts)
end

function gst_inspect(plugin)
    local eopts = ifelse(os.getenv("GST_OPTIONS"), "")
    local line = string.format("gst-inspect-1.0 %s %s >/dev/null 2>&1", eopts, plugin)
    local iret = shexecute(line)
    if type(iret) == "boolean" then
        return iret
    end
    return (iret == 0)
end

function gst_video_delay(speed)
    local decdelay = ifelse(tonumber(os.getenv("GST_VIDEO_DEC_DELAY")), 1000)
    local encdelay = ifelse(tonumber(os.getenv("GST_VIDEO_ENC_DELAY")), 5000)
    if speed > 0 then
        return math.floor(decdelay/speed), math.floor(encdelay/speed)
    else
        return decdelay, encdelay
    end
end

-- check element queue/queuex
function gst_inspect_queue(sink_interval, src_interval)
    local element = "queue"
    if gst_inspect("queuex") then
        element = "queuex"
        local sink_val = tonumber(sink_interval)
        local src_val = tonumber(src_interval)
        if sink_val > 0 or src_val > 0 then
            element = string.format("queuex min-sink-interval=%d min-src-interval=%d",
                                    math.floor(sink_val), math.floor(src_val))
        end
    end
    return element
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
function gst_inspect_video_enc(kbps)
    local codec
    local bps = math.floor(tonumber(kbps)) * 1024
    if gst_inspect("mpph264enc") then
        codec = string.format("mpph264enc rc-mode=vbr bps=%d profile=main ! h264parse", bps)
    elseif gst_inspect("avenc_h264") then
        codec = string.format("avenc_h264 pass=pass1 bitrate=%d profile=main ! h264parse", bps)
    elseif gst_inspect("avenc_h264_videotoolbox") then
        codec = string.format("avenc_h264_videotoolbox pass=pass1 bitrate=%d profile=main ! h264parse", bps)
    end
    return codec
end

function gst_inspect_audio_enc(kbps)
    local codec
    local bps = math.floor(tonumber(kbps)) * 1024
    if gst_inspect("avenc_aac") then
        codec = string.format("avenc_aac bitrate=%d", bps)
    end
    return codec
end

-- check media file's info
-- supported media files: mp4(mov,3gp,m4a)/mkv(webm)/mpeg(ps,ts)/avi/ogg/flv/id3(mp3)/asf(wmv)
function gst_media_info(caps, props)
    local info
    if caps then
        if findistr(caps, "/quicktime")
            or findistr(caps, "/x-3gp")
            or findistr(caps, "/x-mj2")
            or findistr(caps, "/x-m4a") then
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
        elseif findistr(caps, "/x-id3") then
            info = {demux = "id3demux"}
        elseif findistr(caps, "/x-ms-asf") then
            info = {demux = "asfdemux"}
        end
        if info then
            info.caps = caps
        end
    end
    return info
end

-- check audio codec format's info
-- supported audio: mpeg(mp1,mp2,mp3,aac)/vorbis/opus/flac/amr(nb,wb)/speex/alaw(ulaw)/ac3/wma
function gst_audio_info(caps, props)
    local info
    if caps then
        if findistr(caps, "audio/mpeg") then
            -- findistr(props, "mpegaudioversion=(int)1")
            if findistr(props, "mpegversion=(int)1") then
                if findistr(props, "layer=(int)1") then
                    info = {parse = "mpegaudioparse", dec = "avdec_mp1float"}
                elseif findistr(props, "layer=(int)2") then
                    info = {parse = "mpegaudioparse", dec = "avdec_mp2float"}
                elseif findistr(props, "layer=(int)3") then
                    info = {parse = "mpegaudioparse", dec = "avdec_mp3"}
                end
            elseif findistr(props, "mpegversion=(int)2")
                or findistr(props, "mpegversion=(int)4") then
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
        elseif findistr(caps, "audio/x-speex") then
            info = {parse = nil, dec = "speexdec"}
        elseif findistr(caps, "audio/x-alaw") then
            info = {parse = "audioparse", dec = "alawdec"}
        elseif findistr(caps, "audio/x-mulaw") then
            info = {parse = "audioparse", dec = "mulawdec"}
        elseif findistr(caps, "audio/x-ac3")
            or findistr(caps, "audio/ac3")
            or findistr(caps, "audio/x-private1-ac3") then
            info = {parse = "ac3parse", dec = "avdec_ac3"}
        elseif findistr(caps, "audio/x-eac3") then
            info = {parse = "ac3parse", dec = "avdec_eac3"}
        elseif findistr(caps, "audio/x-wma") then
            if findistr(props, "wmaversion=(int)1") then
                info = {parse = nil, dec = "avdec_wmav1"}
            elseif findistr(props, "wmaversion=(int)2") then
                info = {parse = nil, dec = "avdec_wmav2"}
            elseif findistr(props, "wmaversion=(int)3") then
                info = {parse = nil, dec = "avdec_wmapro"}
            elseif findistr(props, "wmaversion=(int)4") then
                info = {parse = nil, dec = "avdec_wmalossless"}
            end
        end
        if info then
            info.caps = caps
        end
    end
    return info
end

-- check video codec format's info
-- supported video: h263/h264/h265/mpeg(mpeg1,mpge2,mpge4,divx,msmpeg4)/vp8(vp9)/theora/flash/wmv
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
        elseif findistr(caps, "video/x-h263") then
            info = {parse = "h263parse", dec = nil} -- auto dec
        elseif findistr(caps, "video/x-vp8") then
            info = {parse = nil, dec = "vp8dec"} -- no parse
        elseif findistr(caps, "video/x-vp9") then
            info = {parse = nil, dec = "vp9dec"} -- no parse
        elseif findistr(caps, "video/x-theora") then
            info = {parse = "theoraparse", dec = "theoradec"}
        elseif findistr(caps, "video/x-flash-video") then
            info = {parse = nil, dec = "avdec_flv"} -- no parse
        elseif findistr(caps, "video/x-divx") then
            if findistr(props, "divxversion=(int)3") then
                info = {parse = nil, dec = "avdec_msmpeg4"}
            elseif findistr(props, "divxversion=(int)4")
                or findistr(props, "divxversion=(int)5") then
                info = {parse = "mpeg4videoparse", dec = "avdec_mpeg4"}
            end
        elseif findistr(caps, "video/x-msmpeg") then
            if findistr(props, "msmpegversion=(int)41") then
                info = {parse = nil, dec = "avdec_msmpeg4v1"}
            elseif findistr(props, "msmpegversion=(int)42") then
                info = {parse = nil, dec = "avdec_msmpeg4v2"}
            elseif findistr(props, "msmpegversion=(int)43") then
                info = {parse = nil, dec = "avdec_msmpeg4"}
            end
        elseif findistr(caps, "video/x-wmv") then
            if findistr(props, "wmvversion=(int)1") then
                info = {parse = nil, dec = "avdec_wmv1"}
            elseif findistr(props, "wmvversion=(int)2") then
                info = {parse = nil, dec = "avdec_wmv2"}
            elseif findistr(props, "wmvversion=(int)3") then
                if findistr(props, "format=WMV3") then
                    info = {parse = nil, dec = "avdec_wmv3"}
                else
                    info = {parse = "vc1parse", dec = "avdec_vc1"} -- WVC1/WMVA
                end
            end
        end
        if info then
            info.caps = caps
            info.dec = gst_inspect_video_dec(caps, info.dec)
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
        if not minfo then
            ret, props = string.match(info, "unknown: ([%w%-%/]+)[%,]*(.*)")
            if ret then minfo = gst_media_info(ret, props) end
        end

        ret, props = string.match(info, "audio: ([%w%-%/]+)[%,]*(.*)")
        if ret then ainfo = gst_audio_info(ret, props) end

        ret, props = string.match(info, "video: ([%w%-%/]+)[%,]*(.*)")
        if ret then vinfo = gst_video_info(ret, props) end
    end
    --print(table2json(minfo), table2json(ainfo), table2json(vinfo))
    return minfo, ainfo, vinfo
end

-- transcode routine: outf - int/string/nil
function gst_transcode(src, copy, start, speed, width, height, fps, v_kbps, a_kbps, outf)
    local TAG = ">"

    -- check media info(audio/video)
    local minfo, ainfo, vinfo = gst_discover(src)
    print (TAG .. "media:", table2json(minfo))
    print (TAG .. "audio:", table2json(ainfo))
    print (TAG .. "video:", table2json(vinfo))
    if minfo == nil or (ainfo == nil and vinfo == nil) then
        return nil
    end

    -- should have one of parse/dec
    if ainfo and (not ainfo.parse) and (not ainfo.dec) then
        print (TAG .. "audio: unsupported audio")
        return nil
    end

    -- should have one of parse/dec
    if vinfo and (not vinfo.parse) and (not vinfo.dec) then
        print (TAG .. "video: unsupported video")
        return nil
    end


    ---
    --- construct gst launch command line
    ---
    local media = {
        -- src
        src = nil,
        caps = minfo.caps,
        demux = minfo.demux,
        start_tc = nil,

        -- audio
        aparse = ainfo and ainfo.parse,
        arate = nil,
        aenc = gst_inspect_audio_enc(a_kbps),

        -- video
        vparse = vinfo and vinfo.parse,
        vrate = nil,
        vscale = nil,
        venc = gst_inspect_video_enc(v_kbps),

        -- sink
        mux = "mpegtsmux",
        mime = "video/mpegts",
        --mux = "qtmux",
        --mime = "video/quicktime",
        sink = nil
    }

    if not media.aenc or not media.venc then
        print (TAG .. "media: no encoder(aac/h264)")
        return nil
    end
    print (TAG .. "audio: encoder -", media.aenc, "\n")
    print (TAG .. "video: encoder -", media.venc, "\n")


    -- check output sink
    local opts
    if outf then
        local dstfd = tonumber(outf)
        if dstfd == nil then
            media.sink = string.format("filesink location=%s", outf)
        else
            media.sink = string.format("fdsink fd=%d", dstfd)
            opts = ifone(dstfd == 1, "-q", "")
        end
    else
        opts = "-q"
        media.sink = "";
    end

    -- check input src
    media.src = string.format([[%s filesrc location="%s"]], gst_launch(opts), src)

    -- check parameters
    speed = ifclip(tonumber(speed), 0.5, 3.0, 1.0)
    fps = ifclip(tonumber(fps), 0, 60, 0)

    -- check sink queue(microseconds)
    local vdecdelay, vencdelay = gst_video_delay(speed)
    local vqueue_enc = gst_inspect_queue(vencdelay, 0)
    local aqueue_enc = gst_inspect_queue(vencdelay*0.75, 0)

    -- check audio/video rate
    media.start_tc = string.format("%s:00", start)
    media.arate = string.format("speed speed=%f", speed)
    media.vrate = string.format("videorate rate=%f ! video/x-raw", speed)
    if fps > 0 then
        media.vrate = media.vrate .. string.format(",framerate=%d/1", fps)
    end

    -- check audio dec/enc
    if ainfo then
        media.aenc = string.format("%s ! %s", media.aenc, aqueue_enc)
    end

    -- check video dec/enc
    if vinfo then
        media.venc = string.format("%s ! %s", media.venc, vqueue_enc)
    end

    -- check video scale
    media.vscale = string.format("videoscale ! video/x-raw")
    if tonumber(width) > 0 and tonumber(height) > 0 then
        media.vscale = media.vscale .. string.format(",width=%d,height=%d", width, height)
    end

    local line
    local mime = media.mime

    -- 1). copy audio/video
    if false or copy then
        if false or (media.aparse and media.vparse) then
            if media.demux == "matroskademux" then
                media.mux = "matroskamux"
                media.mime = media.caps
                mime = media.mime
            end
            line = string.format([[%s ! %s name=demux \
                demux.audio_0 ! queue ! %s ! %s name=mux \
                demux.video_0 ! queue ! %s ! mux. \
                mux. ! queue ! %s]],
                media.src, media.demux,
                media.aparse, media.mux,
                media.vparse,
                media.sink);
        elseif media.aparse or media.vparse then
            local tmp_parse = ifelse(media.aparse, media.vparse)
            line = string.format([[%s ! parsebin name=pb \
                pb. ! %s ! queue ! %s name=mux \
                mux. ! %s]],
                media.src,
                tmp_parse, media.mux,
                media.sink);
        else
            print(TAG .. "media: copy need codec or parse!")
        end
        return line, mime
    end

    -- 2) audio-only transcode
    if false or (ainfo and not vinfo) then
        -- unsupport start-tc
        line = string.format([[%s ! decodebin name=db \
            db. ! audio/x-raw ! audioconvert ! audio/x-raw ! %s \
                ! %s ! %s name=mux \
            mux. ! %s ]],
            media.src,
            media.arate,
            media.aenc, media.mux,
            media.sink);
        return line, mime
    end

    -- 3). video-only transcode (support start-tc)
    if false or (not ainfo and vinfo) then
        line = string.format([[%s ! decodebin name=db \
            db. ! video/x-raw ! videoconvert ! queue ! video/x-raw ! %s \
                ! timecodestamper ! avwait name=wait target-timecode-string="%s" \
                wait. ! %s ! %s name=mux \
            mux. ! %s]],
            media.src,
            media.vrate,
            media.start_tc,
            media.venc, media.mux,
            media.sink);
        return line, mime
    end

    -- 4). audio and video trancode (support start-tc)
    line = string.format([[%s ! decodebin name=db \
        db. ! audio/x-raw ! audioconvert ! queue ! audio/x-raw ! %s \
            ! avwait name=wait target-timecode-string="%s" \
            ! %s ! %s name=mux \
        db. ! video/x-raw ! videoconvert ! queue ! video/x-raw ! %s \
            ! timecodestamper ! wait. \
            wait. ! queue ! %s ! mux. \
        mux. ! %s]],
        media.src,
        media.arate, media.start_tc, media.aenc, media.mux,
        media.vrate, media.venc,
        media.sink);
    return line, mime
end


--- outf: like before, e.g. /tmp/out_hls.mp4, changed to hls output(/tmp/out_hls.m38u)
function gst_transcode_hls(src, copy, start, speed, width, height, fps, v_kbps, a_kbps, outf)
    dir, name, ext = parse_path(outf)
    if not dir or not name then
        return nil, nil
    end
    fm38u = string.format([[%s/%s.m38u]], dir, name)
    fsegment = string.format([[%s/%s_segment_%%05d.ts]], dir, name)

    cmd, mime = gst_transcode(fname, copy, start, speed, width, height, fps, vkbps, akbps, nil)
    if cmd then
        hlscmd = string.format([[%s hlssink max-files=50 target-duration=15 playlist-length=5 \
            playlist-location="%s" location="%s"]],
            cmd, fm38u, fsegment)
        return hlscmd, mime
    end
    return nil, nil
end


--
-- testing cases
--

function test_gst(fname, outf, stdout)
    start = "00:00:01"
    speed = 1.0
    width = 1280/2
    height = 720/2
    fps = 15 --15
    vkbps = 600 -- video
    akbps = 64 -- audio
    copy = false

    local cmd, mime
    if stdout then
        cmd, mime = gst_transcode(fname, copy, start, speed, width, height, fps, vkbps, akbps, 1)
        if cmd then
            cmd = string.format("%s >%s", cmd, outf)
        end
    else
        cmd, mime = gst_transcode(fname, copy, start, speed, width, height, fps, vkbps, akbps, outf)
    end

    print("============", fname, "===========", mime)
    if cmd then
        print(cmd)
        local begintm = os.time();
        shexecute(cmd)
        local endtm = os.time();
        print(os.difftime(endtm, begintm))
    end
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
        --f01 = "/tmp/sample-h265.mkv",
        --f02 = "/tmp/sample-mpeg4.mkv",
        --f03 = "/tmp/sample-h264.mp4",

        f05 = path .. "/samples/small.ogg",
        f06 = path .. "/samples/small.m4a",
        f07 = path .. "/samples/small.mp3",

        f11 = path .. "/samples/small.mp4",
        f12 = path .. "/samples/small.3gp",
        f13 = path .. "/samples/small.webm",
        f14 = path .. "/samples/small.ogm",
        f15 = path .. "/samples/small.flv",
        f16 = path .. "/samples/small.mpg",
        f17 = path .. "/samples/small.avi",
        f18 = path .. "/samples/small.mkv",
        f19 = path .. "/samples/small.asf",
        f20 = path .. "/samples/small.vob",
        f21 = path .. "/samples/small.wmv",
        f22 = path .. "/samples/small.mov",
        f23 = path .. "/samples/small.ts",
    }

    local dinfo = false
    if dinfo then
        test_discover({items.f05, items.f06, items.f07})
        test_discover({items.f11, items.f12, items.f13, items.f14, items.f15})
        test_discover({items.f16, items.f17, items.f18, items.f19, items.f20})
        test_discover({items.f21, items.f22, items.f23})
    else
        for _, item in pairs(items) do
            local fin = item
            local fout = "/tmp/out_media.mp4"
            test_gst(fin, fout)
            print("=====================\n\n")
        end
    end
end

function test_one()
    fname = "/deepnas/home/U1000/avatar.mp4"
    fname = "./samples/small.mp4"
    copy = false
    start = "00:00:00"
    speed = 1
    width = 640
    height = 360
    fps = 30
    vkbps = 400
    akbps = 60
    cmd, mime = gst_transcode_hls(fname, copy, start, speed, width, height, fps, vkbps, akbps, "/tmp/out.mp4")
    print(cmd, mime)
    --shexecute(cmd)
end

--test_files()
test_one()
