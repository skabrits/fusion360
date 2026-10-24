"""Run with GOST_TEST_BINARY=/absolute/path/to/gost python3 -m unittest discover -s tests."""
import base64, http.server, importlib.util, json, os, pathlib, socket, subprocess, tempfile, threading, time, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('proxyconfig',ROOT/'proxy/bin/fusion-proxy-config.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]

def wait(p,process):
    for _ in range(100):
        if process.poll() is not None:raise RuntimeError('GOST exited')
        try:
            with socket.create_connection(('127.0.0.1',p),.2):return
        except OSError:time.sleep(.05)
    raise RuntimeError('GOST startup timed out')

class ProxyTests(unittest.TestCase):
    def test_configuration(self):
        self.assertIsNone(m.configuration(''))
        for scheme in ('http','https','socks5'):
            c=m.configuration(scheme+'://user:p%40ss%3Aword@host:1234')
            self.assertEqual(c['chains'][0]['hops'][0]['nodes'][0]['connector']['auth']['password'],'p@ss:word')
            self.assertEqual(c['services'][0]['addr'],'127.0.0.1:8889')
        for url in ('ftp://user:secret@host:21','http://host','http://host:80/bad'):
            with self.assertRaises(ValueError) as e:m.configuration(url)
            self.assertNotIn('secret',str(e.exception))

    @unittest.skipUnless(os.environ.get('GOST_TEST_BINARY'),'Set GOST_TEST_BINARY for live forwarding test')
    def test_authenticated_http_and_connect(self):
        binary=os.environ['GOST_TEST_BINARY'];up=port();local=port()
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'fusion-proxy-test')
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        children=[]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                upstream={'services':[{'name':'auth','addr':f'127.0.0.1:{up}','handler':{'type':'http','auth':{'username':'user','password':'p@ss:word'}},'listener':{'type':'tcp'}}]}
                config=m.configuration(f'http://user:p%40ss%3Aword@127.0.0.1:{up}')
                config['services'][0]['addr']=f'127.0.0.1:{local}'
                for name,c,p in [('up',upstream,up),('local',config,local)]:
                    path=pathlib.Path(tmp)/(name+'.json');path.write_text(json.dumps(c))
                    proc=subprocess.Popen([binary,'-C',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    children.append(proc);wait(p,proc)
                url=f'http://127.0.0.1:{server.server_port}/'
                # An unauthenticated direct request to upstream must be rejected.
                r=subprocess.run(['curl','-s','--noproxy','','--proxy',f'http://127.0.0.1:{up}','--max-time','5','-o','/dev/null','-w','%{http_code}',url],capture_output=True,check=True)
                self.assertEqual(r.stdout,b'407')
                for tunnel in (False,True):
                    cmd=['curl','-fsS','--noproxy','','--proxy',f'http://127.0.0.1:{local}','--max-time','5']
                    if tunnel:cmd+=['--proxytunnel']
                    r=subprocess.run(cmd+[url],capture_output=True,check=True)
                    self.assertEqual(r.stdout,b'fusion-proxy-test')
        finally:
            for proc in children:proc.terminate()
            for proc in children:proc.wait(timeout=5)
            server.shutdown();server.server_close()
