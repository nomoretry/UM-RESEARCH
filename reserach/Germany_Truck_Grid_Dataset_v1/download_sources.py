from pathlib import Path
import urllib.request, json, hashlib, concurrent.futures, datetime, zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / 'raw').exists() else HERE / 'Germany_Truck_Grid_Dataset_v1'
COMMIT = '805c534c73ed4d247babd053f60468b486f92519'
SOURCES = [
 ('DT01','raw/dt_cargo/fleet.csv',f'https://raw.githubusercontent.com/TUMFTM/dt-cargo/{COMMIT}/input/public/fleet.csv','DT-CARGO vehicle register','observed_anonymized'),
 ('DT02','raw/dt_cargo/tracks.csv',f'https://raw.githubusercontent.com/TUMFTM/dt-cargo/{COMMIT}/input/public/tracks.csv','DT-CARGO track summaries','observed_anonymized'),
 ('DT03','raw/dt_cargo/README.md',f'https://raw.githubusercontent.com/TUMFTM/dt-cargo/{COMMIT}/README.md','DT-CARGO source codebook','documentation'),
 ('DT04','raw/dt_cargo/LICENSE',f'https://raw.githubusercontent.com/TUMFTM/dt-cargo/{COMMIT}/LICENSE','DT-CARGO licence','licence'),
 ('SB01','raw/simbench/1-MV-urban--0-sw.zip','https://daks.uni-kassel.de/bitstreams/6ad5e5f8-6b47-4275-906d-db780344b9ee/download','SimBench urban medium-voltage network scenario 0 with switches','benchmark'),
 ('SB02','raw/simbench/LICENSE','https://raw.githubusercontent.com/e2nIEE/simbench/c426a1a3fecbe986a868edc2beed56349c37baf7/LICENSE','SimBench repository licence','licence'),
 ('SB03','raw/simbench/format_information.py','https://raw.githubusercontent.com/e2nIEE/simbench/c426a1a3fecbe986a868edc2beed56349c37baf7/simbench/converter/format_information.py','SimBench official CSV format and unit conversions','documentation'),
]

def fetch(item):
 sid, rel, url, title, typ = item
 p=ROOT/rel;p.parent.mkdir(parents=True,exist_ok=True)
 downloaded = not p.exists()
 if downloaded:
  req=urllib.request.Request(url,headers={'User-Agent':'Academic-data-audit/1.0'})
  with urllib.request.urlopen(req,timeout=45) as resp:p.write_bytes(resp.read())
 raw=p.read_bytes()
 print(f'{sid}: {len(raw):,} bytes',flush=True)
 digest=hashlib.sha256(raw).hexdigest()
 old_path=ROOT/'source_manifest.json'
 old={r['path']:r for r in json.loads(old_path.read_text())} if old_path.exists() else {}
 if not downloaded and rel in old and old[rel]['sha256']!=digest:
  raise ValueError('Cached source hash differs from its manifest: '+rel)
 timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat() if downloaded else old.get(rel,{}).get('retrieved_utc','unknown_existing_file')
 return {'source_id':sid,'path':rel,'url':url,'title':title,'data_class':typ,'retrieved_utc':timestamp,'sha256':digest,'bytes':len(raw),'git_commit':COMMIT if sid.startswith('DT') else ('c426a1a3fecbe986a868edc2beed56349c37baf7' if sid in ('SB02','SB03') else '')}

if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex: records=list(ex.map(fetch,SOURCES))
 (ROOT/'source_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
 z=ROOT/'raw/simbench/1-MV-urban--0-sw.zip'
 with zipfile.ZipFile(z) as zz:
  print('Grid archive:',[(x.filename,x.file_size) for x in zz.infolist()],flush=True)
  target=ROOT/'raw/simbench/csv';target.mkdir(exist_ok=True)
  for i in zz.infolist():
   if not i.is_dir():
    (target/Path(i.filename).name).write_bytes(zz.read(i))
