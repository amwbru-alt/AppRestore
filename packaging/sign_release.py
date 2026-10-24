"""Sign an already-tested GUI archive. Runs only in the protected signing workflow."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def run(args):
    subprocess.run([str(a) for a in args],check=True)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    target=args.out/args.archive.name
    with tempfile.TemporaryDirectory(prefix='apprevive-sign-') as folder:
        root=Path(folder)
        if sys.platform=='darwin':
            for name in ('MAC_SIGN_IDENTITY','APPLE_API_KEY_FILE','APPLE_API_KEY_ID','APPLE_API_ISSUER'):
                if not os.environ.get(name):raise RuntimeError('Missing signing/notary credential: '+name)
            run(['ditto','-x','-k',args.archive,root]);app=root/'AppRevive.app'
            if not app.is_dir():raise RuntimeError('Expected AppRevive.app')
            magic={b'\xfe\xed\xfa\xce',b'\xfe\xed\xfa\xcf',b'\xce\xfa\xed\xfe',b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xbe\xba\xfe\xca',b'\xca\xfe\xba\xbf',b'\xbf\xba\xfe\xca'}
            identity=os.environ['MAC_SIGN_IDENTITY'];entitlements=ROOT/'packaging'/'macos-release.entitlements'
            def sign(path):run(['codesign','--force','--options','runtime','--timestamp','--entitlements',entitlements,'--sign',identity,path])
            for path in sorted(app.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if path.is_file() and not path.is_symlink():
                    with path.open('rb') as stream:header=stream.read(4)
                    if header in magic:sign(path)
            for path in sorted(app.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if path.is_dir() and not path.is_symlink() and path.suffix in ('.framework','.app','.bundle'):sign(path)
            sign(app);run(['codesign','--verify','--deep','--strict',app])
            submission=root/'notarize.zip';run(['ditto','-c','-k','--sequesterRsrc','--keepParent',app,submission])
            result=subprocess.run(['xcrun','notarytool','submit',str(submission),'--key',os.environ['APPLE_API_KEY_FILE'],'--key-id',os.environ['APPLE_API_KEY_ID'],'--issuer',os.environ['APPLE_API_ISSUER'],'--wait','--output-format','json'],capture_output=True,text=True,check=True)
            if json.loads(result.stdout).get('status')!='Accepted':raise RuntimeError('Notarization was not accepted. No release archive will be published.')
            run(['xcrun','stapler','staple',app]);run(['xcrun','stapler','validate',app]);run(['spctl','--assess','--type','execute',app]);run([app/'Contents'/'MacOS'/'AppRevive','--update-health-check'])
            run(['ditto','-c','-k','--sequesterRsrc','--keepParent',app,target])
        elif sys.platform=='win32':
            sys.path.insert(0,str(ROOT))
            from apprevive_gui.updater import extract_zip
            extract_zip(args.archive,root);app=root/'AppRevive';binary=app/'AppRevive.exe'
            tool=os.environ.get('SIGNTOOL') or shutil.which('signtool');thumb=os.environ.get('WIN_CERT_THUMBPRINT')
            if not tool or not thumb:raise RuntimeError('Signing tool and imported certificate are required')
            for executable in [binary,*app.rglob('ipatool.exe')]:
                run([tool,'sign','/sha1',thumb,'/fd','SHA256','/tr','http://timestamp.digicert.com','/td','SHA256',executable]);run([tool,'verify','/pa','/all',executable])
            run([binary,'--update-health-check'])
            with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
                for path in sorted(app.rglob('*')):archive.write(path,(Path(app.name)/path.relative_to(app)).as_posix())
        else:raise RuntimeError('Run signing on macOS or Windows')
    (args.out/(target.name+'.sha256')).write_text(f'{sha(target)}  {target.name}\n',encoding='utf-8')
    print('Signed archive ready:',target.name)

if __name__=='__main__':main()
