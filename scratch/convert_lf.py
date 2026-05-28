import os

def to_lf(path):
    with open(path, 'rb') as f:
        content = f.read()
    
    # 替换 CRLF (\r\n) 为 LF (\n)
    content_lf = content.replace(b'\r\n', b'\n')
    
    if content != content_lf:
        with open(path, 'wb') as f:
            f.write(content_lf)
        print(f"Successfully converted {path} to LF format")

def scan_and_convert(dir_path):
    valid_exts = ['.sh', '.tpl', '.pl']
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            name = file.lower()
            # 匹配 shell 脚本、模板和守护进程文件
            if any(name.endswith(ext) for ext in valid_exts) or 'init.d' in root:
                file_path = os.path.join(root, file)
                try:
                    to_lf(file_path)
                except Exception as e:
                    print(f"Error converting {file_path}: {e}")

# 递归扫描整个 plugins 目录
scan_and_convert(r"f:\git\gitea20250909\bt_simple\plugins")
scan_and_convert(r"f:\git\gitea20250909\bt_simple\scripts")
