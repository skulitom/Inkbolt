"""Local file-channel client for the B19 harness; no network or process targeting."""
import json
from pathlib import Path
import sys
import time
import uuid

MAX_MESSAGE=16*1024*1024


def exchange(channel,message,timeout=90):
    channel=Path(channel)
    if not channel.is_dir() or channel.is_symlink():raise ValueError('Missing or linked recovery control channel')
    raw=json.dumps(message,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>MAX_MESSAGE:raise ValueError('Recovery request exceeds its bound')
    name=uuid.uuid4().hex;temporary=channel/(name+'.writing');request=channel/(name+'.request');response=channel/(name+'.response')
    with temporary.open('xb') as stream:stream.write(raw)
    # Only this random, newly created channel entry is renamed; documents and
    # captured evidence are never destinations of this operation.
    temporary.rename(request)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if response.exists():
            if response.is_symlink() or not response.is_file() or response.stat().st_size>MAX_MESSAGE:
                raise ValueError('Invalid recovery response file')
            return json.loads(response.read_bytes())
        time.sleep(.01)
    raise TimeoutError('The recovery harness did not answer before the deadline')


def main():
    if len(sys.argv)!=2:raise ValueError('Pass the exact supplied control channel path')
    raw=sys.stdin.buffer.read(MAX_MESSAGE+1)
    if len(raw)>MAX_MESSAGE:raise ValueError('Recovery request exceeds its bound')
    response=exchange(sys.argv[1],json.loads(raw))
    sys.stdout.write(json.dumps(response,separators=(',',':'))+'\n')
    return 0 if response.get('ok') else 1


if __name__=='__main__':raise SystemExit(main())
