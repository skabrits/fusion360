#!/usr/bin/env python3
import json, os, pathlib, pwd, sys
from urllib.parse import urlsplit, unquote

def configuration(url):
    if not url:
        return None
    try:
        u = urlsplit(url)
        if u.scheme not in ('http', 'https', 'socks5') or not u.hostname or not u.port or u.path not in ('','/') or u.query or u.fragment:
            raise ValueError()
        host = f'[{u.hostname}]' if ':' in u.hostname else u.hostname
        connector = {'type': 'socks5' if u.scheme == 'socks5' else 'http'}
        if u.username is not None:
            connector['auth'] = {'username':unquote(u.username), 'password':unquote(u.password or '')}
        dialer = {'type': 'tls' if u.scheme == 'https' else 'tcp'}
        if u.scheme == 'https':
            dialer['tls'] = {'serverName':u.hostname, 'secure':True}
        return {'services':[{'name':'fusion-local','addr':'127.0.0.1:8889','handler':{'type':'http','chain':'upstream'},'listener':{'type':'tcp'}}],
                'chains':[{'name':'upstream','hops':[{'name':'proxy','nodes':[{'name':'upstream','addr':f'{host}:{u.port}','connector':connector,'dialer':dialer}]}]}],
                'log':{'level':'error'}}
    except ValueError:
        raise ValueError('FUSION_PROXY_URL must be http[s]://[user:password@]host:port or socks5://[user:password@]host:port; percent-encode credentials') from None

def main():
    os.umask(0o077)
    config = configuration(os.environ.get('FUSION_PROXY_URL','').strip())
    runtime = pathlib.Path('/run/fusion-proxy')
    runtime.mkdir(mode=0o700, exist_ok=True)
    user = pwd.getpwnam('abc')
    os.chown(runtime,user.pw_uid,user.pw_gid)
    path=runtime/'gost.json'
    if config:
        path.write_text(json.dumps(config))
        path.chmod(0o600)
        os.chown(path,user.pw_uid,user.pw_gid)
    else:
        path.unlink(missing_ok=True)
    policy={'ProxySettings': {'ProxyMode':'fixed_servers','ProxyServer':'http://127.0.0.1:8889','ProxyBypassList':'localhost;127.0.0.1;[::1]'}} if config else {'ProxySettings':{'ProxyMode':'direct'}}
    for directory in ['/etc/chromium/policies/managed','/etc/chromium-browser/policies/managed','/etc/opt/chrome/policies/managed']:
        folder=pathlib.Path(directory)
        folder.mkdir(parents=True,exist_ok=True)
        # umask must not make policy directories inaccessible to browser users.
        folder.chmod(0o755)
        for parent in (folder.parent,folder.parent.parent):
            parent.chmod(0o755)
        p=folder/'fusion-proxy.json'
        p.write_text(json.dumps(policy));p.chmod(0o644)
    print('Fusion proxy: enabled on loopback' if config else 'Fusion proxy: disabled; direct connections')

if __name__=='__main__':
    try: main()
    except ValueError as e: sys.exit(str(e))
