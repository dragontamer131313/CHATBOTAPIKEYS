import os, time, uuid, secrets, hashlib, hmac, asyncio, json, io, subprocess
from typing import Optional
import httpx
import jwt
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Text, Float, Integer, Boolean, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///./rugged_ai.db")
# Render/external providers may supply the legacy postgres:// scheme.
# SQLAlchemy 2.x expects postgresql://; explicitly select psycopg (v3).
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL="postgresql+psycopg://"+DATABASE_URL[len("postgres://"): ]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL="postgresql+psycopg://"+DATABASE_URL[len("postgresql://"): ]
JWT_SECRET=os.getenv("JWT_SECRET", "change-me-in-production")
ADMIN_TOKEN=os.getenv("ADMIN_TOKEN", "change-me-in-production")
CORS_ORIGINS=[x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
MAX_REQUEST_BYTES=int(os.getenv("MAX_REQUEST_BYTES", "262144"))
MAX_CONCURRENCY=int(os.getenv("MAX_CONCURRENCY", "32"))
RATE_LIMIT_PER_MIN=int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
REDIS_URL=os.getenv("REDIS_URL", "")

PROVIDERS=[
    ("primary", os.getenv("PRIMARY_LLM_BASE_URL", "").rstrip("/"), os.getenv("PRIMARY_LLM_API_KEY", ""), os.getenv("PRIMARY_LLM_MODEL", "rugged-local")),
    ("backup", os.getenv("BACKUP_LLM_BASE_URL", "").rstrip("/"), os.getenv("BACKUP_LLM_API_KEY", ""), os.getenv("BACKUP_LLM_MODEL", "rugged-local")),
]

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"; id:Mapped[str]=mapped_column(String(64),primary_key=True); email:Mapped[str]=mapped_column(String(320),unique=True,index=True); password:Mapped[str]=mapped_column(String(256)); created:Mapped[float]=mapped_column(Float)
class ApiKey(Base):
    __tablename__="api_keys"; id:Mapped[str]=mapped_column(String(64),primary_key=True); user_id:Mapped[str]=mapped_column(String(64),index=True); name:Mapped[str]=mapped_column(String(100)); key_hash:Mapped[str]=mapped_column(String(128),unique=True,index=True); edition:Mapped[str]=mapped_column(String(16)); active:Mapped[bool]=mapped_column(Boolean,default=True); created:Mapped[float]=mapped_column(Float); last_used:Mapped[Optional[float]]=mapped_column(Float,nullable=True)
class Usage(Base):
    __tablename__="usage"; id:Mapped[str]=mapped_column(String(64),primary_key=True); user_id:Mapped[str]=mapped_column(String(64),index=True); key_id:Mapped[str]=mapped_column(String(64),index=True); provider:Mapped[str]=mapped_column(String(32)); input_tokens:Mapped[int]=mapped_column(Integer,default=0); output_tokens:Mapped[int]=mapped_column(Integer,default=0); created:Mapped[float]=mapped_column(Float)

connect_args={"check_same_thread":False} if DATABASE_URL.startswith("sqlite") else {}
engine=create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
Base.metadata.create_all(engine)
sem=asyncio.Semaphore(MAX_CONCURRENCY)
_local_rate={}
_redis=None
if REDIS_URL:
    try:
        import redis
        _redis=redis.Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        _redis=None

app=FastAPI(title="Rugged AI API",version="7.0")
app.add_middleware(CORSMiddleware,allow_origins=CORS_ORIGINS,allow_methods=["*"],allow_headers=["*"],allow_credentials=False)

@app.middleware("http")
async def request_guard(request:Request, call_next):
    cl=request.headers.get("content-length")
    if cl:
        try:
            if int(cl)>MAX_REQUEST_BYTES:return JSONResponse({"detail":"Request too large"},status_code=413)
        except ValueError:return JSONResponse({"detail":"Invalid Content-Length"},status_code=400)
    return await call_next(request)

def pwd_hash(password:str)->str:
    salt=secrets.token_bytes(16); dk=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,210_000); return "pbkdf2$210000$"+salt.hex()+"$"+dk.hex()
def pwd_ok(password:str,stored:str)->bool:
    try:
        _,n,salt,dk=stored.split("$"); got=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),int(n)); return hmac.compare_digest(got.hex(),dk)
    except Exception:return False
def jwt_for(uid:str):return jwt.encode({"sub":uid,"iat":int(time.time())},JWT_SECRET,algorithm="HS256")
def account(authorization):
    try:return jwt.decode((authorization or "").split(" ",1)[1],JWT_SECRET,algorithms=["HS256"])["sub"]
    except Exception:raise HTTPException(401,"Invalid account token")
def key_auth(authorization):
    raw=(authorization or "")
    if not raw.lower().startswith("bearer "):raise HTTPException(401,"API key required")
    secret=raw.split(" ",1)[1]
    kh=hashlib.sha256(secret.encode()).hexdigest()
    with Session(engine) as db:r=db.scalar(select(ApiKey).where(ApiKey.key_hash==kh,ApiKey.active==True))
    if not r:raise HTTPException(401,"Invalid or revoked API key")
    return r

def rate_limit(key_id:str):
    now=int(time.time()); bucket=now//60; rk=f"rugged:rate:{key_id}:{bucket}"
    if _redis:
        try:
            n=_redis.incr(rk); _redis.expire(rk,70)
            if n>RATE_LIMIT_PER_MIN:raise HTTPException(429,"Rate limit exceeded")
            return
        except HTTPException:raise
        except Exception:pass
    local=_local_rate.get((key_id,bucket),0)+1; _local_rate[(key_id,bucket)]=local
    if local>RATE_LIMIT_PER_MIN:raise HTTPException(429,"Rate limit exceeded")

class AccountIn(BaseModel): email:str; password:str=Field(min_length=8,max_length=256)
class KeyIn(BaseModel): name:str=Field(default="My Project",max_length=100); edition:str="standard"
class PublicKeyIn(BaseModel): name:str=Field(default="My Project",max_length=100); edition:str="standard"
class Chat(BaseModel): messages:list[dict]; content_mode:str="general"; model:Optional[str]=None; stream:bool=False; temperature:float=Field(.8,ge=0,max=2); max_tokens:int=Field(512,ge=1,le=4096)

@app.get("/")
def root():
    return {"name":"Rugged AI API","version":"7.1","status":"online","docs":"/docs","health":"/health","chat":"/v1/chat/completions","developer_portal":"Use the Netlify frontend connected to this API."}

@app.get("/health")
def health():return {"ok":True,"version":"7.1"}
@app.get("/ready")
def ready():return {"ready":True,"database":DATABASE_URL.split(":",1)[0],"redis":bool(_redis)}
@app.get("/api/capabilities")
def capabilities():return {"local_first":True,"remote_provider_optional":True,"postgres_supported":True,"redis_enabled":bool(_redis),"provider_count":sum(bool(x[1]) for x in PROVIDERS)}

@app.post("/auth/register")
def register(x:AccountIn):
    uid=str(uuid.uuid4())
    with Session(engine) as db:
        if db.scalar(select(User).where(User.email==x.email.lower())):raise HTTPException(409,"Account exists")
        db.add(User(id=uid,email=x.email.lower(),password=pwd_hash(x.password),created=time.time()));db.commit()
    return {"token":jwt_for(uid),"user_id":uid}
@app.post("/auth/login")
def login(x:AccountIn):
    with Session(engine) as db:u=db.scalar(select(User).where(User.email==x.email.lower()))
    if not u or not pwd_ok(x.password,u.password):raise HTTPException(401,"Invalid credentials")
    return {"token":jwt_for(u.id),"user_id":u.id}

@app.post("/api/keys/generate")
def generate_public_key(x:PublicKeyIn, request:Request):
    """Create a developer API key without creating a Rugged account.
    The secret is returned exactly once. Only its SHA-256 hash is stored.
    """
    if x.edition not in ("standard", "nsfw"):
        raise HTTPException(400,"edition must be standard or nsfw")
    # Basic abuse control for anonymous key creation. Redis is shared when available;
    # local fallback is intentionally conservative.
    ip=request.client.host if request.client else "unknown"
    bucket=int(time.time())//3600
    limiter_key=f"rugged:keygen:{ip}:{bucket}"
    try:
        if _redis:
            n=_redis.incr(limiter_key); _redis.expire(limiter_key,3700)
        else:
            n=_local_rate.get(limiter_key,0)+1; _local_rate[limiter_key]=n
        if n>5:
            raise HTTPException(429,"Too many key generations. Try again later.")
    except HTTPException:
        raise
    except Exception:
        pass
    raw="rk_"+("nsfw_" if x.edition=="nsfw" else "std_")+secrets.token_urlsafe(32)
    kid=str(uuid.uuid4())
    # Anonymous developer keys use a reserved owner; no login/account is required.
    with Session(engine) as db:
        db.add(ApiKey(id=kid,user_id="public",name=x.name,key_hash=hashlib.sha256(raw.encode()).hexdigest(),edition=x.edition,active=True,created=time.time()));db.commit()
    return {"api_key":raw,"id":kid,"edition":x.edition,"default_content_mode":"general","warning":"Save this API key now. The full secret will not be shown again."}

@app.post("/api/keys")
def create_key(x:KeyIn,authorization:Optional[str]=Header(None)):
    uid=account(authorization)
    if x.edition not in ("standard","nsfw"):raise HTTPException(400,"edition must be standard or nsfw")
    raw="rk_"+("nsfw_" if x.edition=="nsfw" else "std_")+secrets.token_urlsafe(32)
    kid=str(uuid.uuid4())
    with Session(engine) as db:db.add(ApiKey(id=kid,user_id=uid,name=x.name,key_hash=hashlib.sha256(raw.encode()).hexdigest(),edition=x.edition,active=True,created=time.time()));db.commit()
    return {"api_key":raw,"id":kid,"edition":x.edition,"default_content_mode":"general"}
@app.post("/api/keys/revoke-self")
def revoke_self(authorization:Optional[str]=Header(None)):
    k=key_auth(authorization)
    with Session(engine) as db:
        r=db.scalar(select(ApiKey).where(ApiKey.id==k.id))
        if not r: raise HTTPException(404,"Key not found")
        r.active=False; db.commit()
    return {"ok":True,"revoked":True}

@app.get("/api/keys")
def list_keys(authorization:Optional[str]=Header(None)):
    uid=account(authorization)
    with Session(engine) as db:rows=db.scalars(select(ApiKey).where(ApiKey.user_id==uid).order_by(ApiKey.created.desc())).all()
    return [{"id":r.id,"name":r.name,"edition":r.edition,"active":r.active,"created":r.created,"last_used":r.last_used} for r in rows]
@app.delete("/api/keys/{key_id}")
def revoke_key(key_id:str,authorization:Optional[str]=Header(None)):
    uid=account(authorization)
    with Session(engine) as db:
        r=db.scalar(select(ApiKey).where(ApiKey.id==key_id,ApiKey.user_id==uid))
        if not r:raise HTTPException(404,"Key not found")
        r.active=False;db.commit()
    return {"ok":True}
@app.get("/api/usage")
def usage(authorization:Optional[str]=Header(None)):
    uid=account(authorization)
    with Session(engine) as db:
        rows=db.execute(select(Usage.provider,func.sum(Usage.input_tokens),func.sum(Usage.output_tokens),func.count(Usage.id)).where(Usage.user_id==uid).group_by(Usage.provider)).all()
    return [{"provider":p,"input_tokens":i or 0,"output_tokens":o or 0,"requests":n} for p,i,o,n in rows]

def provider_stream(resp):
    for line in resp.iter_lines():
        if line:yield line+"\n"

async def provider_request(base,key,model,payload,stream=False):
    headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0,connect=10.0)) as c:
        return await c.post(base+"/chat/completions",json={**payload,"model":model,"stream":stream},headers=headers)

@app.post("/v1/chat/completions")
async def chat(x:Chat,authorization:Optional[str]=Header(None)):
    k=key_auth(authorization);rate_limit(k.id)
    if x.content_mode not in ("general","adult"):raise HTTPException(400,"Invalid mode")
    if x.content_mode=="adult" and k.edition!="nsfw":raise HTTPException(403,"NSFW-capable key required")
    system="General chat mode." if x.content_mode=="general" else "Adult-capable mode for adults. Never involve minors or sexual content involving minors. Follow applicable law and deployment rules."
    payload={"messages":[{"role":"system","content":system}]+x.messages,"temperature":x.temperature,"max_tokens":x.max_tokens}
    errors=[]
    async with sem:
        for pname,base,pkey,pmodel in PROVIDERS:
            if not base:continue
            try:
                r=await provider_request(base,pkey,x.model or pmodel,payload,x.stream)
                if r.status_code in (429,) or r.status_code>=500:
                    errors.append(f"{pname}: HTTP {r.status_code}");continue
                if r.status_code>=400:raise HTTPException(r.status_code,r.text[:500])
                with Session(engine) as db:
                    k.last_used=time.time();db.add(Usage(id=str(uuid.uuid4()),user_id=k.user_id,key_id=k.id,provider=pname,input_tokens=0,output_tokens=0,created=time.time()));db.commit()
                if x.stream:
                    return StreamingResponse(provider_stream(r),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Rugged-Provider":pname})
                return r.json()
            except HTTPException:raise
            except Exception as e:errors.append(f"{pname}: {type(e).__name__}")
    raise HTTPException(503,"No model provider available",headers={"X-Rugged-Errors": "; ".join(errors)[:1000]})

@app.post("/admin/backup")
def backup(authorization:Optional[str]=Header(None)):
    if authorization!=f"Bearer {ADMIN_TOKEN}":raise HTTPException(401,"Invalid admin token")
    if not DATABASE_URL.startswith("sqlite"):
        raise HTTPException(501,"For PostgreSQL, use the scheduled backup job in deploy/backup.sh")
    import shutil
    dest=os.getenv("BACKUP_DIR",".")+"/rugged_ai-"+str(int(time.time()))+".db"
    shutil.copy2(DATABASE_URL.replace("sqlite:///", ""),dest)
    return {"ok":True,"backup":dest}
