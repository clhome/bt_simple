import os
import re

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    count = 0
    for root, dirs, files in os.walk(base_dir):
        if '.git' in root or '__pycache__' in root:
            continue
        for file in files:
            if not file.endswith('.py'):
                continue
            if file == 'mw.py' or file == 'yf.py' or file == 'refactor_mw_to_yf.py':
                continue
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            original_content = content
            
            # Replace import core.yf as mw to import core.yf as yf
            content = re.sub(r'^(\s*)import core\.yf as mw\b', r'\1import core.yf as yf', content, flags=re.MULTILINE)
            
            # Replace import mw to import yf
            content = re.sub(r'^(\s*)import mw\b', r'\1import yf', content, flags=re.MULTILINE)
            content = re.sub(r'^(\s*)from mw import\b', r'\1from yf import', content, flags=re.MULTILINE)
            
            # Replace calls mw.xxx -> yf.xxx
            content = re.sub(r'\bmw\.', r'yf.', content)
            
            # Refactor panel_tools aliases
            if 'panel_tools.py' in filepath:
                content = re.sub(r'mw_input_cmd = yf_input_cmd\s*\n', '', content)
                content = re.sub(r'mwcli = yfcli\s*\n', '', content)
                content = re.sub(r'\bmw_input_cmd\b', 'yf_input_cmd', content)
                content = re.sub(r'\bmwcli\b', 'yfcli', content)
                content = re.sub(r'\bmw_input\b', 'yf_input', content)
                
            # Global specific replacements
            content = re.sub(r'\bmw_async\b', 'yf_async', content)

            if content != original_content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                count += 1
                print(f"Refactored: {filepath}")
    print(f"Total files refactored: {count}")

if __name__ == '__main__':
    main()
