"""
AScript MCP 连接测试脚本
"""
import json
import subprocess
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

proc = subprocess.Popen(
    ['python', '-m', 'ascript_mcp.local'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
    encoding='utf-8'
)

def send(method, params=None):
    msg = json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': method,
        'params': params or {}
    })
    proc.stdin.write(msg + '\n')
    proc.stdin.flush()

def recv():
    line = proc.stdout.readline()
    if line:
        return json.loads(line)
    return None

# Initialize
send('initialize', {
    'protocolVersion': '2024-11-05',
    'capabilities': {},
    'clientInfo': {'name': 'claude-test', 'version': '1.0'}
})
time.sleep(0.5)
resp = recv()
print('Initialize:', json.dumps(resp, indent=2, ensure_ascii=False)[:300])

# Initialized notification
send('notifications/initialized')
time.sleep(0.3)

# List tools
send('tools/list')
time.sleep(0.5)
resp = recv()
if resp and 'result' in resp:
    tools = resp['result'].get('tools', [])
    print(f'\nAvailable tools ({len(tools)}):')
    for t in tools:
        print(f'  - {t["name"]}: {t.get("description", "")[:80]}')

# Scan devices
print('\n--- Scanning for devices (port 9096) ---')
send('tools/call', {
    'name': 'scan_devices',
    'arguments': {'port': 9096}
})
time.sleep(5)

# Read all responses
proc.stdin.write('\n')
proc.stdin.flush()
time.sleep(1)
proc.terminate()

# Now read whatever output is available
out, err = proc.communicate(timeout=2)
print('\nRemaining stdout:', out[:2000] if out else 'none')
print('\nStderr:', err[:500] if err else 'none')
