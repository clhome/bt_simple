import re
s = "''$'\\344\\270\\213\\350\\275\\275'"
print("Original:", s)
res = re.sub(r"''\$'((?:\\[0-7]{3})+)'", lambda m: bytes(int(x, 8) for x in m.group(1).split('\\')[1:]).decode('utf-8', 'ignore'), s)
print("Decoded:", res)

s2 = "'$'\\344\\270\\213\\350\\275\\275'"
res2 = re.sub(r"'\$'((?:\\[0-7]{3})+)'", lambda m: bytes(int(x, 8) for x in m.group(1).split('\\')[1:]).decode('utf-8', 'ignore'), s2)
print("Decoded 2:", res2)

s3 = "$'\\344\\270\\213\\350\\275\\275'"
res3 = re.sub(r"\$'((?:\\[0-7]{3})+)'", lambda m: bytes(int(x, 8) for x in m.group(1).split('\\')[1:]).decode('utf-8', 'ignore'), s3)
print("Decoded 3:", res3)
