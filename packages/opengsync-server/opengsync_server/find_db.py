import os
import re

dir_path = "packages/opengsync-server/opengsync_server/"

r = re.compile(r'db\.([a-z_]+)\.get\((.*?)\)')
occurrences = []

for root, dirs, files in os.walk(dir_path):
    for f in files:
        if f.endswith('.py'):
            with open(os.path.join(root, f), 'r') as file:
                try:
                    content = file.read()
                    matches = r.findall(content)
                    for m in matches:
                        occurrences.append((f, m[0], m[1]))
                except Exception:
                    pass

for o in sorted(list(set(occurrences))):
    print(o)
