"""Sanitized AST fixtures, blocked sockets/imports, and stubbed Git only."""
import argparse
import ast
import builtins
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
BASH=Path('C:/Program Files/Git/bin/bash.exe')
DUMMY={'OPENAI_API_KEY':'fixture-ai','META_PAGE_TOKEN':'fixture-page','META_AD_ACCOUNT_ID':'fixture-account','META_ACCESS_TOKEN':'fixture-token'}
class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.imports=[]
        blocker=patch('socket.socket',side_effect=AssertionError('Network forbidden'))
        blocker.start(); self.addCleanup(blocker.stop)

    def module_scope(self,name,env=None):
        def no_import(module,*args,**kwargs):
            self.imports.append(module)
            if module=='httpx': raise ModuleNotFoundError('httpx unavailable offline')
            raise AssertionError('Unexpected import '+module)
        scope={'__builtins__':dict(vars(builtins),__import__=no_import),
               'os':SimpleNamespace(environ={} if env is None else env), 'argparse':argparse,'sys':sys,
               'date':SimpleNamespace(today=lambda:date(2026,10,5))}
        tree=ast.parse((HERE/'automation'/name).read_text(encoding='utf-8'))
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
        nodes += [n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('TIKTOK_SCRIPTS','FB_POSTS','BLOG_OUTLINES') for t in n.targets)]
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<sanitized-module>','exec'),scope)
        return scope

    def test_dummy_credentials_dry_run_zero_imports_and_network(self):
        scope=self.module_scope('meta_poster.py',DUMMY)
        self.assertEqual(scope['post_to_page']('fixture'),{'ok':True,'dry_run':True,'body':'fixture'})
        expected={'ok':True,'dry_run':True,'operations':['campaign','adset','creative','ad'],'status':'PAUSED','daily_budget':30000}
        self.assertEqual(scope['build_ad_campaign'](),expected)
        self.assertEqual(self.imports,[])
        with self.assertRaisesRegex(AssertionError,'Network forbidden'): socket.socket()

    def test_cli_default_preview_and_live_errors(self):
        for argv,env,expected in ((['meta','--post','fixture','--ads'],DUMMY,0),
                                  (['meta','--post','fixture','--live'],{},1),
                                  (['meta','--ads','--live'],{},1),
                                  (['meta','--ads','--live'],DUMMY,1)):
            with self.subTest(argv=argv):
                scope=self.module_scope('meta_poster.py',env)
                with patch.object(sys,'argv',argv),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                    self.assertEqual(scope['main'](),expected)

    def test_template_fixture_output_unchanged(self):
        scope=self.module_scope('content_generator.py')
        self.assertEqual(scope['gen_with_ai'](),scope['gen_templated']())
        self.assertEqual(len(scope['gen_with_ai']()['items']),8)
        self.assertEqual(self.imports,[])

    def pipeline(self,args=(),fail_stage=None,code=7):
        calls=[]
        def fake_run(command,**kwargs):
            calls.append(command)
            stage='post' if '--post' in command else ('ads' if '--ads' in command else 'generate')
            return SimpleNamespace(returncode=code if stage==fail_stage else 0,stdout='safe fixture',stderr='must not print dummy credentials')
        tree=ast.parse((HERE/'automation/run_daily.py').read_text(encoding='utf-8'))
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        with tempfile.TemporaryDirectory(prefix='graxia-hardening-') as temp:
            root=Path(temp); gen=root/'docs/content/generated';gen.mkdir(parents=True)
            (gen/'daily-fixture.json').write_text(json.dumps({'items':[{'channel':'facebook','status':'queue','body':'fixture'},{'channel':'tiktok','body':'fixture'}]}),encoding='utf-8')
            scope={'argparse':argparse,'sys':sys,'ROOT':root,'os':SimpleNamespace(environ=DUMMY),'json':json,'subprocess':SimpleNamespace(run=fake_run)}
            exec(compile(ast.Module(body=[main],type_ignores=[]),'<pipeline-fixture>','exec'),scope)
            output=io.StringIO()
            with patch.object(sys,'argv',['daily',*args]),redirect_stdout(output),redirect_stderr(output):
                status=scope['main']()
        return status,calls,output.getvalue()

    def test_default_pipeline_no_ai_or_post_with_dummy_credentials(self):
        status,calls,out=self.pipeline()
        self.assertEqual(status,0)
        self.assertEqual(len(calls),2)
        self.assertTrue(all('--ai' not in c and '--post' not in c and '--live' not in c for c in calls))
        self.assertIn('--ads',calls[-1])
        self.assertIn('SUMMARY: 1 FB items, 1 TikTok scripts queued',out)

    def test_failures_propagate_and_stop_later_stages(self):
        for stage,code,length in (('generate',6,1),('post',7,2),('ads',8,3),('ads',-9,3)):
            status,calls,out=self.pipeline(('--live',),stage,code)
            self.assertEqual(status,code if code>0 else 1)
            self.assertEqual(len(calls),length)
            self.assertNotIn('SUMMARY:',out)
            self.assertNotIn('must not print',out)
        status,calls,out=self.pipeline(('--ai','--live'))
        self.assertEqual(status,0)
        self.assertIn('--ai',calls[0]); self.assertIn('--live',calls[1])
        self.assertNotIn('--live',calls[2])

    def test_complete_default_cli_in_sanitized_network_blocked_fixture(self):
        with tempfile.TemporaryDirectory(prefix='graxia-cli-fixture-') as temp:
            root=Path(temp); automation=root/'automation';automation.mkdir()
            for name in ('content_generator.py','meta_poster.py','run_daily.py'):
                (automation/name).write_bytes((HERE/'automation'/name).read_bytes())
            guard=root/'guard';guard.mkdir()
            (guard/'sitecustomize.py').write_text(
                "import socket, sys, importlib.abc\n"
                "def forbidden(*args, **kwargs): raise AssertionError('Network forbidden')\n"
                "socket.socket = forbidden\n"
                "class DenyHTTP(importlib.abc.MetaPathFinder):\n"
                "    def find_spec(self, fullname, path=None, target=None):\n"
                "        if fullname.split('.')[0] in ('httpx','requests'): raise AssertionError('HTTP client forbidden')\n"
                "sys.meta_path.insert(0,DenyHTTP())\n",encoding='utf-8')
            env={'PATH':os.environ.get('PATH',''),'SYSTEMROOT':os.environ.get('SYSTEMROOT','C:/Windows'),
                 'PYTHONPATH':str(guard),'PYTHONDONTWRITEBYTECODE':'1', **DUMMY}
            result=subprocess.run([sys.executable,str(automation/'run_daily.py')],cwd=root,env=env,
                                  capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            files=list((root/'docs/content/generated').glob('daily-*.json'))
            self.assertEqual(len(files),1)
            data=json.loads(files[0].read_text(encoding='utf-8'))
            self.assertEqual(len(data['items']),8)
            self.assertIn('SUMMARY: 3 FB items, 3 TikTok scripts queued',result.stdout)
            self.assertIn('AUTO-POST: skipped',result.stdout)
            self.assertIn("'dry_run': True",result.stdout)
            self.assertTrue(all(value not in result.stdout+result.stderr for value in DUMMY.values()))

    @unittest.skipUnless(BASH.exists(),'Installed Git Bash required')
    def test_git_failures_are_truthful_without_push(self):
        workflow=(HERE/'.github/workflows/free-pipeline.yml').read_text(encoding='utf-8')
        block=workflow.split('        run: |\n',1)[1]
        script='\n'.join(line[10:] for line in block.splitlines())
        stub='''git() {
          case "$1" in
            diff) return "$DIFF_EXIT" ;;
            commit) echo STUB_COMMIT >&2; return "$COMMIT_EXIT" ;;
            push) echo STUB_PUSH >&2; return "$PUSH_EXIT" ;;
            config|add) return 0 ;;
            *) return 97 ;;
          esac
        }
'''
        for diff,commit,push,expected,pushed in ((0,0,0,0,False),(1,0,13,13,True),(1,9,0,9,False),(2,0,0,2,False),(1,0,0,0,True)):
            with self.subTest(diff=diff,commit=commit,push=push):
                env={'PATH':os.environ.get('PATH',''),'SYSTEMROOT':os.environ.get('SYSTEMROOT','C:/Windows'),'DIFF_EXIT':str(diff),'COMMIT_EXIT':str(commit),'PUSH_EXIT':str(push)}
                result=subprocess.run([str(BASH),'--noprofile','--norc','-c',stub+script],cwd=HERE,env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,expected,result.stderr)
                self.assertEqual('STUB_PUSH' in result.stderr,pushed)
        self.assertNotIn('permissions:',workflow)
        self.assertNotIn('push skipped',script)
        self.assertIn('run: python automation/run_daily.py',workflow)

if __name__=='__main__':unittest.main()
