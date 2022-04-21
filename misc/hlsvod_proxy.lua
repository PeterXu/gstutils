--[[
The media source root:
    "/deepnas/home"
The media cache root:
    "/deepnas/hlsvod_cached"

The request uri:
    /deepnas/media/hlsvod/U1000/avatar.mp4/index.m3u8?sid=mysid74f12718
    /hlsvod/U1000/avatar.mp4/index.m3u8

The nginx conf:
        location /hlsvod {
            lua_code_cache off;
            set $upstream "";
            rewrite_by_lua_file lua/hlsvod_proxy.lua;
            proxy_pass $upstream;
        }
        location /deepnas/media/hlsvod {
            lua_code_cache off;
            set $upstream "";
            rewrite_by_lua_file lua/hlsvod_proxy.lua;
            proxy_pass $upstream;
        }
--]]

-- default proxy addr
local proxy_addr = "http://127.0.0.1:8001"

local uri = ngx.var.uri
if uri:find("/hlsvod/", 1, true) == 1 then
    ngx.var.upstream = proxy_addr
    return
end

local args = ngx.req.get_uri_args()
local headers = ngx.req.get_headers()
local sid = args["sid"]
if not sid then
    sid = headers["sid"]
end
-- TODO: to verify sid

path = uri:match("/deepnas/media/hlsvod/(.*)")
if not path then
    ngx.status = 404;
    ngx.exit(404)
    return
end
path = "/" .. path

ngx.var.upstream = proxy_addr
ngx.req.set_uri(path)
ngx.log(ngx.ERR, uri, ",", path, ",", sid)
