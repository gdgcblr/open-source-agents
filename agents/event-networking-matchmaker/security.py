"""Bound request bodies before multipart parsing, including chunked uploads."""
from starlette.responses import JSONResponse

class BodyLimitMiddleware:
    def __init__(self,app,limit=6*1024*1024):
        self.app,self.limit=app,limit

    async def __call__(self,scope,receive,send):
        if scope["type"]!="http" or scope["method"] not in {"POST","PUT","PATCH"}:
            return await self.app(scope,receive,send)
        chunks=[];total=0
        while True:
            message=await receive()
            if message["type"]=="http.disconnect":
                return
            chunk=message.get("body",b"");total+=len(chunk)
            if total>self.limit:
                response=JSONResponse({"detail":"Request exceeds 6 MB."},status_code=413,headers={"Cache-Control":"no-store"})
                return await response(scope,receive,send)
            chunks.append(chunk)
            if not message.get("more_body",False):
                break
        delivered=False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {"type":"http.request","body":b"".join(chunks),"more_body":False}
            return await receive()
        await self.app(scope,replay,send)
