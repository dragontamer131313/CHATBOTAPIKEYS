import os, requests
base=os.environ["RUGGED_API_URL"].rstrip("/")
key=os.environ["RUGGED_API_KEY"]
r=requests.post(base+"/v1/chat/completions",headers={"Authorization":"Bearer "+key},json={"model":"rugged-ai","messages":[{"role":"user","content":"Hello"}]},timeout=120)
r.raise_for_status(); print(r.json())
