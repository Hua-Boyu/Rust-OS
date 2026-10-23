"""Preserve extra01 nonverbose-log assumption failure; truthful reader continuation."""
from pathlib import Path
p=Path(__file__).with_name('extra_01.py');code=p.read_text();code=code.replace("(W/n).open('x'","(W/n.replace('_01','_02')).open('x'")
old="check(Counter(c+'.'+n for n,c in success)==Counter(declared) and len(declared)==89,'canonical89 AST membership');out['canonical_mock89_exact_AST_membership']=True"
new="""check(not success and len(declared)==89 and text.splitlines()[0]=='.'*89 and re.search(r'Ran 89 tests in 802\\.654s\\s+OK',text),'canonical89 nonverbose completion');isolated=(B/'mock_isolated_04/mock.log').read_text();verbose=re.findall(r'^(test_\\w+) \\(__main__\\.(\\w+)\\.\\1\\) \\.\\.\\. ok$',isolated,re.M);check(Counter(c+'.'+n for n,c in verbose)==Counter(declared),'isolated89 exact names');out['canonical_mock89_membership_qualification']={'canonical':'Frozen exact script,89 success dots, Ran89/OK, actual exit0; canonical log is nonverbose and does NOT enumerate names','source_AST_count':89,'isolated_verbose_exact_AST_names':True,'no_rerun':True,'extra01_failure':'Canonical exact verbose-name assertion failed because actual canonical log is nonverbose; preserved extra_01.py and transcript, not a guest or regression failure'}"""
if code.count(old)!=1:raise RuntimeError('exact continuation anchor')
code=code.replace(old,new)
exec(compile(code,str(p.with_name('extra_02_virtual.py')),'exec'),{'__file__':str(p.with_name('extra_02_virtual.py')),'__name__':'__main__'})
