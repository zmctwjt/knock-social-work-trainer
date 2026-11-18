import zipfile, os, sys
ZIP = "叩门·社工个案面谈 AI 陪练舱_471188.zip"
OUT = "src_extract"
def fix(name):
    try:
        return name.encode('cp437').decode('gbk')
    except Exception:
        return name
z = zipfile.ZipFile(ZIP)
count = 0
skipped = 0
for info in z.infolist():
    raw = info.filename
    name = fix(raw)
    low = name.lower()
    if '/node_modules/' in low or low.endswith('/node_modules'):
        skipped += 1; continue
    if '/dist/' in low:
        skipped += 1; continue
    if low.endswith('.mp4'):
        skipped += 1; continue
    target = os.path.join(OUT, name)
    if name.endswith('/'):
        os.makedirs(target, exist_ok=True); continue
    os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
    with z.open(info) as src, open(target, 'wb') as dst:
        dst.write(src.read())
    count += 1
print("extracted", count, "skipped", skipped)
