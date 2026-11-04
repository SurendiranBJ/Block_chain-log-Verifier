#!/usr/bin/env python3
"""Standalone local log forwarder. Download from LogChain; no packages required."""
import argparse
import json
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def read_events(path, format_name, state):
    if path.stat().st_size > 900000:
        raise ValueError('Source exceeds 900 KB. Register a new source for log rotation.')
    content=path.read_text(encoding='utf-8')
    if format_name=='json':
        events=json.loads(content)
        if not isinstance(events,list) or any(not isinstance(e,dict) for e in events):
            raise ValueError('JSON format requires an array of structured audit events')
        return events
    # Only complete lines are observed; a writer may still be completing the last line.
    lines=content.splitlines(keepends=True)
    if lines and not lines[-1].endswith(('\n','\r')):
        lines.pop()
    events=[]
    for index,line in enumerate(lines,1):
        raw=line.rstrip('\r\n')
        if not raw.strip():
            continue
        value=json.loads(raw) if format_name=='jsonl' else None
        if isinstance(value,dict) and all(k in value for k in ('event_id','sequence','timestamp','actor','action','message')):
            events.append(value)
            continue
        # Stable physical-line identity makes an edit/restoration compare with its original.
        # Do not hash line contents into IDs: that would hide edits behind new identities.
        timestamp=state.setdefault(str(index),stamp())
        event={'event_id':f'line-{index}','sequence':index,'timestamp':timestamp,
               'actor':'external-application','action':'log','message':raw or '(empty)'}
        if value is not None:
            event['data']=value
        events.append(event)
    return events


def post(config, suffix, payload):
    url=config['api_url'].rstrip('/')+'/api/sources/'+config['source_id']+'/'+suffix
    content=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
    if len(content)>1000000:
        raise ValueError('Snapshot is too large. Rotate the log using a new LogChain source.')
    request=Request(url,data=content,headers={'Content-Type':'application/json','Authorization':'Bearer '+config['token']})
    with urlopen(request,timeout=20) as response:
        return json.load(response)


def save_state(path,state):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(state),encoding='utf-8')
    temp.chmod(0o600)
    os.replace(temp,path)


def main():
    parser=argparse.ArgumentParser(description='Continuously mirror an existing project log into LogChain')
    parser.add_argument('--config',required=True,help='Downloaded source connection JSON')
    parser.add_argument('--file',help='Override the configured log file path')
    parser.add_argument('--once',action='store_true',help='Send one snapshot, then exit')
    args=parser.parse_args()
    os.umask(0o077)
    config_path=Path(args.config).expanduser().resolve()
    config=json.loads(config_path.read_text())
    if config.get('mode')!='file':
        parser.error('This agent needs a file-agent connection; API sources send events directly')
    url=urlsplit(config['api_url'])
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:
        parser.error('Invalid API address')
    if not re.fullmatch(r'[a-f0-9]{12}',config.get('source_id','')):
        parser.error('Invalid source ID in connection config')
    source=Path(args.file or config.get('file_path','')).expanduser().resolve()
    if not args.file and not config.get('file_path'):
        parser.error('Choose a log file with --file /absolute/path/to/app.log')
    fmt=config.get('format','text')
    if fmt not in ('text','json','jsonl'):
        parser.error('Unsupported source format')
    interval=float(config.get('interval_seconds',2))
    if not 0.5<=interval<=5:
        parser.error('Use an interval between 0.5 and 5 seconds')
    state_path=config_path.parent/('logchain-'+config['source_id']+'.state.json')
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    identity={'source_id':config['source_id'],'file':str(source),'format':fmt}
    if state and state.get('identity')!=identity:
        parser.error('This state belongs to another file/source. Register a new source for rotation.')
    state.setdefault('identity',identity)
    timestamps=state.setdefault('timestamps',{})
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.set())
    print(f'Monitoring {source} ({fmt}). Keep this agent and LogChain running.',flush=True)
    was_online=False
    while not stop.is_set():
        try:
            try:
                events=read_events(source,fmt,timestamps)
                # Persist stable identities before network delivery, including retries/restarts.
                save_state(state_path,state)
            except (OSError,ValueError) as exc:
                post(config,'unavailable',{'error':('External log unreadable: '+str(exc))[:500]})
                raise
            result=post(config,'sync',{'events':events})
            if not was_online or result.get('accepted'):
                print(f"Connected: {len(events)} records observed; {result['accepted']} new records queued for anchoring.",flush=True)
            was_online=True
        except Exception as exc:
            print(f'Forwarding unavailable: {exc}. Retrying automatically.',file=sys.stderr,flush=True)
            was_online=False
            if args.once:
                return 1
        if args.once:
            return 0
        stop.wait(interval)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
