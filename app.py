import os,sqlite3,hashlib,secrets,time,uuid,asyncio
import httpx,jwt
from fastapi import FastAPI,Header,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
DB=os.getenv("DB_PATH","rugged_ai.db"); JWT_SECRET=os.getenv("JWT_SECRET","change-me"); ADMIN=os.getenv("ADMIN_TOKEN","change-me")
P=[("primary",os.getenv("PRIMARY_LLM_BASE_URL","").rstrip("/"),os.getenv("PRIMARY_LLM_API_KEY",""),os.getenv("PRIMARY_LLM_MODEL","local-model")),("backup",os.getenv("BACKUP_LLM_BASE_URL","").rstrip("/"),os.getenv("BACKUP_LLM_API_KEY",""),os.getenv("BACKUP_LLM_MODEL","local-model"))]
sem=asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_REQUESTS","8"))); app=FastAPI(title="Rugged AI")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])
def db(): c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 c=db();c.executescript("""CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,password TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS api_keys(id INTEGER PRIMARY KEY,user_id TEXT,name TEXT,key_hash TEXT UNIQUE,edition TEXT,active INTEGER DEFAULT 1,created REAL);
 CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,user_id TEXT,title TEXT,updated REAL);
 CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,conversation_id TEXT,role TEXT,content TEXT,mode TEXT,created REAL);""");c.commit()
init()
class Account(BaseModel): email:str;password:str
class Key(BaseModel): name:str;edition:str="standard"
class Chat(BaseModel): user_id:str="anonymous";conversation_id:str|None=None;content_mode:str="general";messages:list[dict];model:str|None=None;stream:bool=False;temperature:float=.8;max_tokens:int=512
def h(x):return hashlib.sha256(x.encode()).hexdigest()
def auth(a):
 try:return jwt.decode(a.split(" ",1)[1],JWT_SECRET,algorithms=["HS256"])["sub"]
 except:raise HTTPException(401,"Invalid token")
def ka(a):
 if not a or not a.lower().startswith("bearer "):raise HTTPException(401,"API key required")
 r=db().execute("SELECT * FROM api_keys WHERE key_hash=? AND active=1",(h(a.split(" ",1)[1]),)).fetchone()
 if not r:raise HTTPException(401,"Invalid API key")
 return r
@app.get("/health")
def health():return {"ok":True}
@app.post("/auth/register")
def register(x:Account):
 uid=str(uuid.uuid4());c=db()
 try:c.execute("INSERT INTO users VALUES(?,?,?,?)",(uid,x.email.lower(),h(x.password),time.time()));c.commit()
 except sqlite3.IntegrityError:raise HTTPException(409,"Account exists")
 return {"token":jwt.encode({"sub":uid},JWT_SECRET,algorithm="HS256"),"user_id":uid}
@app.post("/auth/login")
def login(x:Account):
 r=db().execute("SELECT * FROM users WHERE email=? AND password=?",(x.email.lower(),h(x.password))).fetchone()
 if not r:raise HTTPException(401,"Invalid credentials")
 return {"token":jwt.encode({"sub":r["id"]},JWT_SECRET,algorithm="HS256"),"user_id":r["id"]}
@app.post("/api/keys")
def create(x:Key,authorization:str|None=Header(None)):
 uid=auth(authorization)
 if x.edition not in ("standard","nsfw"):raise HTTPException(400,"edition must be standard or nsfw")
 raw="rk_"+("nsfw_" if x.edition=="nsfw" else "std_")+secrets.token_urlsafe(32);c=db()
 c.execute("INSERT INTO api_keys(user_id,name,key_hash,edition,created) VALUES(?,?,?,?,?)",(uid,x.name,h(raw),x.edition,time.time()));c.commit()
 return {"api_key":raw,"edition":x.edition,"default_content_mode":"general"}
@app.post("/v1/chat/completions")
async def chat(x:Chat,authorization:str|None=Header(None)):
 k=ka(authorization)
 if x.content_mode=="adult" and k["edition"]!="nsfw":raise HTTPException(403,"NSFW-capable key required")
 if x.content_mode not in ("general","adult"):raise HTTPException(400,"Invalid mode")
 system="General chat mode." if x.content_mode=="general" else "Adult-capable mode for adults. Never involve minors or sexual content involving minors. Follow applicable law and deployment rules."
 payload={"model":x.model,"messages":[{"role":"system","content":system}]+x.messages,"stream":False,"temperature":x.temperature,"max_tokens":min(x.max_tokens,2048)}
 async with sem:
  errors=[]
  for name,base,key,model in P:
   if not base:continue
   payload["model"]=x.model or model
   for attempt in range(2):
    try:
     async with httpx.AsyncClient(timeout=45) as c:r=await c.post(base+"/chat/completions",json=payload,headers={"Authorization":"Bearer "+key})
     if r.status_code<500 and r.status_code!=429:return r.json()
     errors.append(f"{name}: HTTP {r.status_code}")
    except Exception as e:errors.append(f"{name}: {e}")
    await asyncio.sleep(.5*(attempt+1))
  return {"error":{"message":"All AI providers failed","details":errors}}
@app.post("/admin/backup")
def backup(authorization:str|None=Header(None)):
 if authorization!=f"Bearer {ADMIN}":raise HTTPException(401,"Invalid admin token")
 import shutil;dest=DB+".backup-"+str(int(time.time()));shutil.copy2(DB,dest);return {"ok":True,"backup":dest}
