import zipfile, collections, sys
z = zipfile.ZipFile("叩门·社工个案面谈 AI 陪练舱_471188.zip")
names = z.namelist()
print("total entries:", len(names))
top = collections.Counter()
for n in names:
    parts = n.split('/')
    top['/'.join(parts[:2]) if len(parts)>1 else parts[0]] += 1
for k,v in sorted(top.items()):
    print(f"{v:6d}  {k}")
