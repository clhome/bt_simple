#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import urllib.request
import ssl

# 禁用 SSL 验证，以防下载时因证书链问题失败
ssl._create_default_https_context = ssl._create_unverified_context

ASSETS_TO_DOWNLOAD = [
    # 1. jQuery 3.7.1
    {
        'url': 'https://cdn.staticfile.org/jquery/3.7.1/jquery.js',
        'dest': 'web/static/js/jquery-3.7.1.js'
    },
    {
        'url': 'https://cdn.staticfile.org/jquery/3.7.1/jquery.min.js',
        'dest': 'web/static/js/jquery-3.7.1.min.js'
    },
    # 2. jQuery Migrate 3.4.1
    {
        'url': 'https://cdn.jsdelivr.net/npm/jquery-migrate@3.4.1/dist/jquery-migrate.js',
        'dest': 'web/static/js/jquery-migrate-3.4.1.js'
    },
    {
        'url': 'https://cdn.jsdelivr.net/npm/jquery-migrate@3.4.1/dist/jquery-migrate.min.js',
        'dest': 'web/static/js/jquery-migrate-3.4.1.min.js'
    },
    # 3. Bootstrap 3.4.1 JS
    {
        'url': 'https://cdn.staticfile.org/twitter-bootstrap/3.4.1/js/bootstrap.min.js',
        'dest': 'web/static/js/bootstrap.min.js'
    },
    # 4. Bootstrap 3.4.1 CSS
    {
        'url': 'https://cdn.staticfile.org/twitter-bootstrap/3.4.1/css/bootstrap.min.css',
        'dest': 'web/static/bootstrap-3.4.1/css/bootstrap.min.css'
    },
    {
        'url': 'https://cdn.staticfile.org/twitter-bootstrap/3.4.1/css/bootstrap-theme.min.css',
        'dest': 'web/static/bootstrap-3.4.1/css/bootstrap-theme.min.css'
    },
    # 5. Bootstrap 3.4.1 Fonts
    {
        'url': 'https://cdn.staticfile.org/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.eot',
        'dest': 'web/static/bootstrap-3.4.1/fonts/glyphicons-halflings-regular.eot'
    },
    {
        'url': 'https://cdn.staticfile.org/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.svg',
        'dest': 'web/static/bootstrap-3.4.1/fonts/glyphicons-halflings-regular.svg'
    },
    {
        'url': 'https://cdn.staticfile.org/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.ttf',
        'dest': 'web/static/bootstrap-3.4.1/fonts/glyphicons-halflings-regular.ttf'
    },
    {
        'url': 'https://cdn.staticfile.org/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.woff',
        'dest': 'web/static/bootstrap-3.4.1/fonts/glyphicons-halflings-regular.woff'
    },
    {
        'url': 'https://cdn.staticfile.org/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.woff2',
        'dest': 'web/static/bootstrap-3.4.1/fonts/glyphicons-halflings-regular.woff2'
    }
]

# 备用下载源列表（如果主源失败，则使用备用源）
BACKUP_SOURCES = {
    'jquery.js': 'https://code.jquery.com/jquery-3.7.1.js',
    'jquery.min.js': 'https://code.jquery.com/jquery-3.7.1.min.js',
    'jquery-migrate.js': 'https://code.jquery.com/jquery-migrate-3.4.1.js',
    'jquery-migrate.min.js': 'https://code.jquery.com/jquery-migrate-3.4.1.min.js',
    'bootstrap.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/js/bootstrap.min.js',
    'bootstrap.min.css': 'https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css',
    'bootstrap-theme.min.css': 'https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap-theme.min.css',
    'glyphicons-halflings-regular.eot': 'https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.eot',
    'glyphicons-halflings-regular.svg': 'https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.svg',
    'glyphicons-halflings-regular.ttf': 'https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.ttf',
    'glyphicons-halflings-regular.woff': 'https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.woff',
    'glyphicons-halflings-regular.woff2': 'https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/fonts/glyphicons-halflings-regular.woff2',
}

def download_file(url, dest_path):
    """安全下载单个文件，并确保目录存在"""
    dest_dir = os.path.dirname(dest_path)
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
    
    print(f"[*] 正在下载: {url} -> {dest_path}")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response, open(dest_path, 'wb') as out_file:
            out_file.write(response.read())
        print(f"[+] 下载成功: {dest_path} ({os.path.getsize(dest_path)} 字节)")
        return True
    except Exception as e:
        print(f"[-] 下载失败: {url}, 错误: {e}")
        return False

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    success_count = 0
    fail_items = []
    
    for item in ASSETS_TO_DOWNLOAD:
        dest_abs = os.path.join(root_dir, item['dest'])
        url = item['url']
        
        # 尝试主源下载
        if download_file(url, dest_abs):
            success_count += 1
        else:
            # 尝试备用源下载
            filename = os.path.basename(url)
            backup_url = BACKUP_SOURCES.get(filename)
            if backup_url:
                print(f"[!] 尝试备用源: {backup_url}")
                if download_file(backup_url, dest_abs):
                    success_count += 1
                    continue
            
            fail_items.append(item['dest'])
            
    print("\n" + "="*50)
    print(f"[!] 下载结束。成功: {success_count}/{len(ASSETS_TO_DOWNLOAD)}")
    if fail_items:
        print(f"[-] 失败列表: {fail_items}")
        exit(1)
    else:
        print("[+] 所有资源下载就绪，阶段2准备完毕！")

if __name__ == '__main__':
    main()
