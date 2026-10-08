"""最小 fastapi 桩，仅用于离线校验 backend/main.py 的业务逻辑。"""
import sys
import types


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class UploadFile:
    def __init__(self, data=b"", filename=""):
        self._data = data
        self.filename = filename

    async def read(self):
        return self._data


def File(default=None, **kwargs):
    return default


def _identity_decorator(*args, **kwargs):
    def wrap(func):
        return func
    return wrap


class FastAPI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.routes = {}
        self.mounts = []

    def _route(self, method):
        def decorator(path, **kwargs):
            def wrap(func):
                self.routes[(method, path)] = func
                return func
            return wrap
        return decorator

    def get(self, path, **kwargs):
        return self._route("GET")(path, **kwargs)

    def post(self, path, **kwargs):
        return self._route("POST")(path, **kwargs)

    def add_middleware(self, *args, **kwargs):
        self.middleware = (args, kwargs)

    def mount(self, path, app=None, name=None):
        self.mounts.append((path, app, name))

    def exception_handler(self, exc):
        return _identity_decorator()


class StaticFiles:
    def __init__(self, directory=None, html=False):
        self.directory = directory
        self.html = html


class CORSMiddleware:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class JSONResponse:
    def __init__(self, status_code=200, content=None, **kwargs):
        self.status_code = status_code
        self.content = content


class StreamingResponse:
    def __init__(self, content=None, media_type=None, headers=None, **kwargs):
        self.body = content.read() if hasattr(content, "read") else content
        self.media_type = media_type
        self.headers = headers or {}


def install():
    """把桩模块注册进 sys.modules，必须在 import main 之前调用。"""
    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.UploadFile = UploadFile
    fastapi.File = File
    fastapi.HTTPException = HTTPException

    responses = types.ModuleType("fastapi.responses")
    responses.JSONResponse = JSONResponse
    responses.StreamingResponse = StreamingResponse

    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = StaticFiles

    middleware = types.ModuleType("fastapi.middleware")
    cors = types.ModuleType("fastapi.middleware.cors")
    cors.CORSMiddleware = CORSMiddleware
    middleware.cors = cors

    fastapi.responses = responses
    fastapi.staticfiles = staticfiles
    fastapi.middleware = middleware

    sys.modules.update({
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "fastapi.staticfiles": staticfiles,
        "fastapi.middleware": middleware,
        "fastapi.middleware.cors": cors,
    })
