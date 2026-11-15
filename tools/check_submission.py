"""Check Git index before push without displaying secret values."""
from pathlib import PurePosixPath
import re
import subprocess
import sys
def git(*args): return subprocess.check_output(['git',*args])
files=list(filter(None,git('ls-files','-z').decode('utf-8').split(chr(0))))
blocked=[]
for name in files:
 p=PurePosixPath(name)
 bad=(p.name=='.env' or (p.name.startswith('.env.') and p.name!='.env.example')
      or p.name in {'secrets.h','first-login.txt','compile_commands.json'}
      or bool(set(p.parts)&{'.venv','.pio','__pycache__','runtime','certs','.git'})
      or p.suffix.lower() in {'.key','.pem','.p12','.pfx','.db','.sqlite','.db-wal','.db-shm','.exe','.log'})
 if bad: blocked.append(name+': forbidden path'); continue
 data=git('show',':'+name)
 if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',data): blocked.append(name+': private key marker')
 if re.search(rb'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}',data): blocked.append(name+': possible GitHub token')
if blocked:
 print('BLOCKED paths; values hidden:'); print(*blocked,sep=chr(10)); sys.exit(1)
print('Index check passed:',len(files),'files. Inspect staged diff and use a dedicated secret scanner as well; this checker is not exhaustive.')
