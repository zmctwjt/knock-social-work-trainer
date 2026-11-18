import re

docs = [
    "deliverables/docs/05_Python后端详细设计.md",
    "deliverables/docs/06_数据库设计与迁移.md",
    "deliverables/docs/附录A_API接口清单.md",
    "deliverables/docs/附录C_代码规范与目录结构.md",
]
total = 0
for path in docs:
    text = open(path, encoding="utf-8").read()
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    total += cjk
    print(path, "lines", len(text.splitlines()), "cjk", cjk, "chars", len(text))
print("total cjk", total)
