# Gathers what a commit's Tiny Tapeout workflows produced into ./site, for makerchip.yaml to publish to GitHub Pages:
# TT's viewer files (as its `viewer` job publishes them), every run's artifacts and job logs (but not the tools'
# binary databases), a manifest.json describing them, and a summary.json of the results. The makerchip-tt-views
# README describes the layout. Run from the workflow's working directory, with the commit checked out in ./repo.
# Environment: REPO (owner/name), SHA, and GH_TOKEN (for the gh CLI).
import glob, hashlib, json, os, re, shutil, subprocess, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

repo, sha = os.environ['REPO'], os.environ['SHA']
site = 'site'
# Intermediate files that only EDA tools read (OpenROAD databases, layouts, parasitics, timing). They stay in the runs'
# artifact zips; the final layout is published as tinytapeout.{gds,oas}.
OMIT = ('.odb', '.gds', '.oas', '.mag', '.def', '.sdf', '.spef', '.lib')


def gh(*args):
    return subprocess.run(['gh', *args], check=True, capture_output=True, text=True).stdout


def api(path):
    return json.loads(gh('api', path))


def read(path):
    return open(path, encoding='utf-8', errors='replace').read() if os.path.exists(path) else None


os.makedirs(site, exist_ok=True)
open(f'{site}/.nojekyll', 'w').close()  # Serve every file as is.

# The latest run of each TT workflow for this commit: its artifacts (in runs/<workflow>/<artifact>/) and, once
# complete, its job logs (in runs/<workflow>/logs/).
runs = {}
for run in api(f'repos/{repo}/actions/runs?head_sha={sha}&per_page=100')['workflow_runs']:
    name = run['name']
    if name not in ('gds', 'test', 'docs') or name in runs:
        continue  # Newest first.
    out = f'{site}/runs/{name}'
    os.makedirs(out, exist_ok=True)
    arts = [a['name'] for a in api(f"repos/{repo}/actions/runs/{run['id']}/artifacts")['artifacts']
            if not a['expired'] and not a['name'].startswith('github-pages')]
    for a in arts:
        gh('run', 'download', str(run['id']), '-R', repo, '-n', a, '-D', f'{out}/{a}')
    logs = run['status'] == 'completed'
    if logs:
        zip_path = f'{out}/logs.zip'
        with open(zip_path, 'wb') as f:
            f.write(subprocess.run(['gh', 'api', f"repos/{repo}/actions/runs/{run['id']}/logs"],
                                   check=True, capture_output=True).stdout)
        zipfile.ZipFile(zip_path).extractall(f'{out}/logs')
        os.remove(zip_path)
    jobs = api(f"repos/{repo}/actions/runs/{run['id']}/jobs")['jobs']
    runs[name] = {
        'id': run['id'], 'url': run['html_url'], 'status': run['status'], 'conclusion': run['conclusion'],
        'jobs': [{'name': j['name'], 'status': j['status'], 'conclusion': j['conclusion'], 'url': j['html_url'],
                  'failed_steps': [s['name'] for s in j.get('steps', []) if s['conclusion'] == 'failure']}
                 for j in jobs],
        'artifacts': arts, 'logs': logs,
    }

# TT's viewer files, as its viewer job publishes them: the layout, its render, and an index.html that redirects to
# TT's 3D viewer (and names the PDK).
sub = f'{site}/runs/gds/tt_submission/tt_submission'  # (The artifact holds a tt_submission folder.)
pdk = json.load(open(f'{sub}/pdk.json')) if os.path.exists(f'{sub}/pdk.json') else None
for ext in ('gds', 'oas'):
    for f in glob.glob(f'{sub}/*.{ext}'):
        shutil.copy(f, f'{site}/tinytapeout.{ext}')
for f in glob.glob(f'{site}/runs/gds/gds_render/*.png'):
    shutil.copy(f, f'{site}/gds_render.png')
if pdk:
    open(f'{site}/index.html', 'w').write(
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Redirecting to 3D Viewer...</title>'
        '</head><body><script>location.href = "https://gds-viewer.tinytapeout.com/?pdk=' + pdk['PDK'] +
        '&model=" + encodeURIComponent(location.href + "/tinytapeout.oas");</script></body></html>\n')

# Omit the tools' binary and intermediate files (see OMIT), counting them by type.
omitted = {}
for d, _, fs in os.walk(f'{site}/runs'):
    for f in fs:
        ext = os.path.splitext(f)[1].lower()
        if ext in OMIT:
            path = os.path.join(d, f)
            count, size = omitted.get(ext, (0, 0))
            omitted[ext] = (count + 1, size + os.path.getsize(path))
            os.remove(path)

# Each generated .sv stamped with its .tlv's hash ("// makerchip-tt: tlv-sha256 <hash>", by the Makerchip
# extension's "Run TT Flow"): whether it was generated from the committed .tlv. Unstamped: unknown (null).
sv = []
for path in sorted(glob.glob('repo/src/*.sv')):
    text = read(path)
    tlv = path[:-3] + '.tlv'
    stamp = re.search(r'// makerchip-tt: tlv-sha256 ([0-9a-f]{64})', text)
    fresh = None
    if stamp and os.path.exists(tlv):
        fresh = stamp.group(1) == hashlib.sha256(open(tlv, 'rb').read().replace(b'\r\n', b'\n')).hexdigest()
    sv.append({'sv': path[5:], 'tlv': tlv[5:], 'fresh': fresh, 'vga': bool(re.search(r'// makerchip-tt: vga\b', text))})


# ---- summary.json: the results at a glance ----

def junit(path):
    """A JUnit results.xml as {tests, failures, errors, skipped, cases: [{name, status, message}]}, or None."""
    if not os.path.exists(path):
        return None
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    cases = []
    for case in root.iter('testcase'):
        bad = case.find('failure') if case.find('failure') is not None else case.find('error')
        status = 'skipped' if case.find('skipped') is not None else 'failed' if bad is not None else 'passed'
        message = ((bad.get('message') or bad.text or '').strip()[:500]) if bad is not None else None
        cases.append({'name': case.get('name'), 'status': status, 'message': message})
    return {'tests': len(cases), 'failed': sum(c['status'] == 'failed' for c in cases),
            'skipped': sum(c['status'] == 'skipped' for c in cases), 'cases': cases}


# Key metrics of the final layout (LibreLane's metrics.json), by their LibreLane names.
METRICS = ('design__instance__count__stdcell', 'design__instance__utilization', 'design__die__area',
           'timing__setup__ws', 'timing__hold__ws', 'route__wirelength', 'power__total',
           'antenna__violating__nets', 'design__lvs_error__count', 'magic__drc_error__count',
           'klayout__drc_error__count', 'route__drc_errors')
metrics = None
for path in glob.glob(f'{site}/runs/gds/GDS_logs/runs/*/final/metrics.json'):
    all_metrics = json.load(open(path))
    metrics = {k: all_metrics[k] for k in METRICS if k in all_metrics}
tiles = re.search(r'^\s*tiles:\s*"?([^"\s#]+)', read('repo/info.yaml') or '', re.M)


def log_excerpt(path):
    """A failed job's log: its error lines, and the lines leading up to the first error, without GitHub's
    timestamps, colors, grouping, or its echo of each step's script."""
    lines = []
    for line in (read(path) or '').splitlines():
        line = re.sub(r'^\d{4}-\d\d-\d\dT[\d:.]+Z ', '', line)
        if line.startswith(('\x1b[36;1m', '##[group]', '##[endgroup]')):  # (Script echo, grouping.)
            continue
        lines.append(re.sub(r'\x1b\[[\d;]*m', '', line))
    first = next((i for i, line in enumerate(lines) if line.startswith('##[error]')), len(lines))
    errors = [line for line in lines
              if line.startswith('##[error]') and 'Process completed with exit code' not in line
              or re.search(r'\bERROR\b|\bError\b|\berror:', line) and not re.match(r'^\s*[\w-]+:\s*error\s*$', line, re.I)]
    return {'errors': errors[-20:], 'context': lines[max(0, first - 20):first + 1]}


failures = []
for name, run in runs.items():
    for job in run['jobs']:
        if job['conclusion'] != 'failure':
            continue
        log = next(iter(glob.glob(f"{site}/runs/{name}/logs/*_{glob.escape(job['name'])}.txt")), None)
        failures.append({'run': name, 'job': job['name'], 'steps': job['failed_steps'], 'url': job['url'],
                         'log': os.path.relpath(log, site) if log else None, **(log_excerpt(log) if log else {})})

summary = {
    'sha': sha, 'pdk': pdk and pdk.get('PDK'), 'tiles': tiles and tiles.group(1),
    'runs': {name: {'conclusion': run['conclusion'], 'url': run['url']} for name, run in runs.items()},
    'metrics': metrics,
    'tests': {'rtl': junit(f'{site}/runs/test/test-results/results.xml'),
              'gl': junit(f'{site}/runs/gds/gatelevel_test_results/results.xml')},
    'precheck': junit(f'{site}/runs/gds/precheck_reports/results.xml'),
    'failures': failures,
    'sv': sv,
    'datasheet': 'runs/docs/PDF/datasheet.pdf' if os.path.exists(f'{site}/runs/docs/PDF/datasheet.pdf') else None,
}
json.dump(summary, open(f'{site}/summary.json', 'w'), indent=1)

files = sorted(os.path.relpath(os.path.join(d, f), site) for d, _, fs in os.walk(site) for f in fs)
manifest = {'sha': sha, 'published': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'pdk': pdk, 'runs': runs, 'sv': sv,
            'omitted': {ext: {'files': count, 'bytes': size} for ext, (count, size) in sorted(omitted.items())},
            'files': files + ['manifest.json']}
json.dump(manifest, open(f'{site}/manifest.json', 'w'), indent=1)
print(json.dumps({k: v for k, v in summary.items() if k not in ('tests', 'precheck')}, indent=1))
print('omitted:', manifest['omitted'])
